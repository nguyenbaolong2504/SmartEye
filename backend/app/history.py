"""Evidence-based, UTC+7 traffic summaries. Missing time remains missing.

Average each camera within five-minute slots, then retain the highest calibrated
density per road/slot. This prevents frame rate or camera count inflating coverage.
Recurring hours require >=3 days with >=3 observed slots each, >=12 slots total.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from fastapi import HTTPException
from .db import now

LOCAL = timezone(timedelta(hours=7))
SLOT_MINUTES = 5


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp requires a timezone')
    return parsed.astimezone(timezone.utc)


def window(period, value):
    try:
        if period == 'day':
            selected = date.fromisoformat(value)
            first = datetime.combine(selected,time(),LOCAL)
            last = first + timedelta(days=1)
        elif period == 'month' and len(value) == 7:
            selected = date.fromisoformat(value+'-01')
            first = datetime.combine(selected,time(),LOCAL)
            last = first.replace(year=first.year+1,month=1) if first.month==12 else first.replace(month=first.month+1)
        elif period == 'year':
            selected=date.fromisoformat(value)
            if selected>now().astimezone(LOCAL).date():raise ValueError()
            last=datetime.combine(selected,time(),LOCAL)
            first=last-timedelta(days=365)
        else:
            raise ValueError()
        if first > now():
            raise ValueError()
        return first,last
    except ValueError:
        raise HTTPException(422,'Chọn ngày YYYY-MM-DD hoặc tháng YYYY-MM hợp lệ, không ở tương lai.') from None


def road_slots(database, segment_ids, start, end):
    """Read indexed samples, with old observations as a backwards-compatible fallback."""
    start = start.astimezone(timezone.utc)
    end = min(end.astimezone(timezone.utc),now())
    query = {'segment_id':{'$in':list(segment_ids)},'observed_at':{'$gte':start.isoformat(),'$lt':end.isoformat()}}
    grouped = {}
    linked = set()
    sample_count = 0
    def collect(row,at):
        slot=at.replace(minute=at.minute//5*5,second=0,microsecond=0)
        key=(row['segment_id'],slot,row.get('camera_id'))
        group=grouped.setdefault(key,{'n':0,'score':0.,'count':0.,'high':0,'low':0,'minutes':set()})
        group['n']+=1;group['score']+=row['score'];group['count']+=row.get('count',0)
        group['high']+=row['density']=='HIGH';group['low']+=row['density']=='LOW'
        group['minutes'].add(at.minute)
    projection = {'segment_id':1,'camera_id':1,'observed_at':1,'score':1,'count':1,'density':1,'observation_id':1}
    for row in database.traffic_samples.find(query,projection):
        if row.get('observation_id') is not None: linked.add(row['observation_id'])
        try: at = parse_timestamp(row['observed_at'])
        except (ValueError,TypeError): continue
        if not start <= at < end: continue
        collect(row,at)
        sample_count += 1
    for row in database.observations.find(query,projection):
        if row['_id'] in linked: continue
        try: at = parse_timestamp(row['observed_at'])
        except (ValueError,TypeError): continue
        if not start <= at < end: continue
        collect(row,at)
        sample_count += 1
    by_road = {}
    for (segment_id,slot,camera_id),group in grouped.items():
        high = group['high']/group['n']>=.5
        low = not high and group['low']/group['n']>=.5
        row = {'segment_id':segment_id,'at':slot.astimezone(LOCAL),
               'score':group['score']/group['n'],'count':group['count']/group['n'],
               'high_share':int(high),'low_share':int(low),'severity':2 if high else 0 if low else 1,
               'sample_minutes':len(group['minutes']),
               'camera_id':camera_id}
        key = (segment_id,slot)
        if key not in by_road or (by_road[key]['severity'],by_road[key]['score']) < (row['severity'],row['score']): by_road[key] = row
    return list(by_road.values()),sample_count


def summary(rows):
    days = defaultdict(int)
    for row in rows: days[row['at'].date().isoformat()] += 1
    evidence_days = sum(slots>=3 for slots in days.values())
    return {'slot_count':len(rows),'observed_minutes':sum(r['sample_minutes'] for r in rows),
            'observed_days':len(days),'evidence_days':evidence_days,
            'sufficient':evidence_days>=3 and len(rows)>=12,
            'average_score':round(mean(r['score'] for r in rows),4) if rows else None,
            'average_count':round(mean(r['count'] for r in rows),1) if rows else None,
            'high_share':round(mean(r['high_share'] for r in rows),4) if rows else None,
            'low_share':round(mean(r['low_share'] for r in rows),4) if rows else None}


def history_report(database, segment, period, value):
    first,last = window(period,value)
    rows,total = road_slots(database,[segment.id],first,last)
    hourly = [{**summary([r for r in rows if r['at'].hour==hour]),'hour':hour} for hour in range(24)]
    daily = []
    heatmap = []
    grouped=defaultdict(list)
    for row in rows:grouped[row['at'].date()].append(row)
    day = first
    while day < last:
        day_rows = grouped.get(day.date(),[])
        daily.append({'date':day.date().isoformat(),**summary(day_rows)})
        for hour in range(24) if period!='year' else ():
            heatmap.append({'date':day.date().isoformat(),'hour':hour,
                            **summary([r for r in day_rows if r['at'].hour==hour])})
        day += timedelta(days=1)
    elapsed = max(0,(min(last,now().astimezone(LOCAL))-first).total_seconds()/60)
    expected = max(1,int((elapsed+4.999)//5))
    peaks = sorted((h for h in hourly if h['sufficient'] and h['high_share']>=.5),
                   key=lambda h:(-h['high_share'],-h['average_score'],h['hour']))[:5]
    monthly=defaultdict(list);weekly=defaultdict(list)
    if period=='year':
        for row in rows:
            monthly[row['at'].strftime('%Y-%m')].append(row)
            weekly[(row['at'].weekday(),row['at'].hour)].append(row)
    return {'segment_id':segment.id,'segment_name':segment.name,'is_demo':segment.is_demo,
            'monthly':[{'month':month,**summary(items)} for month,items in sorted(monthly.items())],
            'weekdays':[{'weekday':w,'hour':h,**summary(weekly.get((w,h),[]))} for w in range(7) for h in range(24)] if period=='year' else [],
            'period':period,'value':value,'timezone':'Asia/Ho_Chi_Minh','generated_at':now().isoformat(),
            'summary':{**summary(rows),'raw_samples':total,'coverage_percent':round(min(100,len(rows)/expected*100),3)},
            'hourly':hourly,'daily':daily,'heatmap':heatmap,'peak_hours':peaks,
            'method':'Gộp mỗi camera theo ô 5 phút; chọn mức mật độ cao nhất của các camera cho từng ô đường. Tỷ lệ cao chỉ tính trên các ô có mẫu, độ phủ là tỷ lệ ô có mẫu trong thời gian đã qua.',
            'pattern_requirement':'Mỗi giờ cần ít nhất 3 ngày có từ 3 ô quan sát, tổng ít nhất 12 ô. Mật độ cao là chỉ báo rủi ro, cần kiểm chứng tình trạng ùn tắc.'}


def historical_evidence(database, segment_ids, departure):
    """Use only past data, matching local weekday and hour; never future leakage."""
    target = departure.astimezone(LOCAL)
    end = min(now(),departure)
    rows,_ = road_slots(database,segment_ids,end-timedelta(days=28),end)
    grouped = defaultdict(list)
    for row in rows:
        if row['at'].hour==target.hour and row['at'].weekday()==target.weekday():
            grouped[row['segment_id']].append(row)
    result = {}
    for sid,evidence in grouped.items():
        stats = summary(evidence)
        if not stats['sufficient']: continue
        score = stats['average_score']
        # Use observed density votes to respect per-camera calibrated thresholds.
        high = stats['high_share']>=.5
        density = 'HIGH' if high else ('LOW' if stats['low_share']>=.5 else 'NORMAL')
        result[sid] = {'density':density,'score':score,'source':'historical',
                       'evidence_days':stats['observed_days'],'high_share':stats['high_share']}
    return result
