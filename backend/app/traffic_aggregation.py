"""Aggregate declared interval averages, never fabricate coverage from point samples."""
from collections import defaultdict,Counter
from datetime import timedelta,timezone
from .db import now
from .history import parse_timestamp
from .traffic_windows import WindowInput,save_windows,key


def aggregate_sources(database):
    end=now().replace(minute=now().minute//5*5,second=0,microsecond=0)
    start=end-timedelta(hours=2)
    sources=list(database.data_sources.find({'active':True,'authorized':True,'speed_verified':True,
        'traffic_profile.interval_averages':True,'traffic_profile.length_verified':True}))
    by_direction=Counter((s['segment_id'],s['direction']) for s in sources)
    count=0
    for source in sources:
        # Multiple sources need an explicit authoritative-source choice. Do not
        # sum overlapping cameras or silently choose the most congested one.
        if by_direction[(source['segment_id'],source['direction'])]!=1:continue
        road=database.segments.find_one({'_id':source['segment_id'],'active':True,'is_demo':False})
        if not road:continue
        groups=defaultdict(list)
        for row in database.road_readings.find({'source_id':source['_id'],'source_version':source['version'],
                'observed_at':{'$gt':start.isoformat(),'$lte':end.isoformat()}}):
            metrics=row['metrics'];interval=metrics.get('interval_seconds')
            if not interval or not 0<interval<=300 or metrics.get('speed_kmh') is None or metrics.get('present_count') is None:continue
            at=parse_timestamp(row['observed_at']);first=at-timedelta(seconds=interval)
            boundary=first.replace(minute=first.minute//5*5,second=0,microsecond=0)+timedelta(minutes=5)
            if at>boundary:continue  # Cannot split a supplied interval without raw measurements.
            groups[boundary].append((first,at,metrics))
        for boundary,rows in groups.items():
            rows.sort(key=lambda row:row[0]);seconds=sum((last-first).total_seconds() for first,last,_ in rows)
            if seconds<240 or seconds>300 or any(rows[i][0]<rows[i-1][1] for i in range(1,len(rows))):continue
            def average(field):
                if any(m.get(field) is None for _,_,m in rows):return None
                return sum(m[field]*(last-first).total_seconds() for first,last,m in rows)/seconds
            states=[(m.get('state'),(last-first).total_seconds()) for first,last,m in rows]
            valid=all(state in ('FREE','SLOW','JAM') for state,_ in states)
            votes=Counter()
            for state,duration in states:votes[state]+=duration
            state=votes.most_common(1)[0][0] if valid and source.get('state_verified') else None
            profile=source['traffic_profile']
            body=WindowInput(segment_id=source['segment_id'],direction=source['direction'],window_end=boundary,
                present_count=average('present_count'),crossing_count=int(sum(m['crossing_count'] for _,_,m in rows)) if all(m.get('crossing_count') is not None for _,_,m in rows) else None,
                avg_speed_kmh=average('speed_kmh'),free_flow_speed_kmh=profile['free_flow_speed_kmh'],
                observed_length_m=profile['observed_length_m'],lanes=profile['lanes'],coverage_seconds=seconds,
                speed_calibrated=True,length_verified=True,training_allowed=profile.get('training_allowed',False),
                verified_state=state,verification_note=f"Nhãn độc lập từ nguồn đã xác nhận {source['_id']} phiên bản {source['version']}" if state else '',
                source=f"source:{source['_id']}:v{source['version']}",rain_mm=average('rain_mm'),visibility_km=average('visibility_km'))
            doc=body.document(source['created_by']);doc.update(source_id=source['_id'],source_version=source['version'])
            existing=database.traffic_windows.find_one({'_id':key(doc)})
            if existing and existing.get('source_id')!=source['_id']:continue  # Preserve reviewed imports.
            save_windows(database,[doc]);count+=1
    return count
