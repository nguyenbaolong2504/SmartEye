"""Hourly labels and comparable-day evidence from completed historical slots."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .history import LOCAL

LOOKBACK_DAYS = 100
MIN_COMPARABLE_DAYS = 5
STATES = ('JAM', 'SLOW', 'FREE')
TEXT = {'JAM': 'Dễ ùn tắc', 'SLOW': 'Đông xe', 'FREE': 'Thông thoáng'}


def majority(counts):
    return max(STATES, key=lambda state: counts[state])


def observed_profiles(database, segment_id, direction, start, stop):
    first = datetime.combine(start, datetime.min.time(), LOCAL).astimezone(timezone.utc)
    last = datetime.combine(stop, datetime.min.time(), LOCAL).astimezone(timezone.utc)
    window = {'$gte': first.isoformat(), '$lt': last.isoformat()}
    readings = database.road_readings.find({'segment_id':segment_id, 'direction':direction,
        'observed_at':window, 'metrics.state':{'$in':list(STATES)}}, {'observed_at':1,'metrics.state':1})
    slots = {}
    for row in readings:
        at = datetime.fromisoformat(row['observed_at']).astimezone(LOCAL)
        key = at.replace(minute=at.minute//5*5, second=0, microsecond=0)
        if key not in slots or at > slots[key][0]:
            slots[key] = (at, row['metrics']['state'])

    if direction == 'forward':
        # Reviewed labels are stored at the end of the five-minute slot.
        labels = database.traffic_labels.find({'segment_id':segment_id,'observed_at':{
            '$gt':first.isoformat(), '$lte':last.isoformat()}, 'state':{'$in':list(STATES)}})
        for row in labels:
            end = datetime.fromisoformat(row['observed_at']).astimezone(LOCAL)
            slots[end-timedelta(minutes=5)] = (end, row['state'])

    grouped = defaultdict(dict)
    for at, (_, state) in slots.items():
        grouped[(at.date(), at.hour)][at.minute] = state
    profiles = defaultdict(list)
    for (day, hour), minutes in grouped.items():
        if sum(m < 30 for m in minutes) >= 3 and sum(m >= 30 for m in minutes) >= 3:
            profiles[day].append({'hour':hour, 'state':majority(Counter(minutes.values()))})
    return profiles


def evidence_by_hour(profiles, target, stop):
    first = stop - timedelta(days=LOOKBACK_DAYS)
    counts = [Counter() for _ in range(24)]
    covered = set()
    for day, rows in profiles.items():
        if not first <= day < stop:
            continue
        covered.add(day)
        if (day.weekday() < 5) != (target.weekday() < 5):
            continue
        for row in rows:
            counts[row['hour']][row['state']] += 1
    result = []
    for hour, states in enumerate(counts):
        total = sum(states.values())
        label = majority(states) if total >= MIN_COMPARABLE_DAYS else None
        result.append({'hour':hour, 'label':label, 'text':TEXT[label] if label else 'Chưa đủ dữ liệu',
                       'similar_days':total, 'jam_days':states['JAM'], 'free_days':states['FREE'],
                       'slow_days':states['SLOW'], 'jam_frequency':states['JAM']/total if total else None})
    return result, len(covered)


def backtest(database, segment_id, direction, stop, days=28):
    import numpy as np
    from .forecast_data import CLASSES
    from .forecast_ml import metrics

    start = stop - timedelta(days=days)
    profiles = observed_profiles(database,segment_id,direction,start-timedelta(days=LOOKBACK_DAYS),stop)
    classes = CLASSES['congestion']
    actual, predicted, baseline = [], [], []
    eligible = 0
    for day in sorted(d for d in profiles if start <= d < stop):
        hourly,_ = evidence_by_hour(profiles,day,day)
        eligible += len(profiles[day])
        comparable = sorted((d for d in profiles if day-timedelta(days=LOOKBACK_DAYS)<=d<day
                             and (d.weekday()<5)==(day.weekday()<5)),reverse=True)
        latest = {}
        for past in comparable:
            for row in profiles[past]:
                latest.setdefault(row['hour'],row['state'])
        for row in profiles[day]:
            hour = row['hour']
            if label:=hourly[hour]['label']:
                actual.append(classes.index(row['state']))
                predicted.append(classes.index(label))
                baseline.append(classes.index(latest[hour]))
    return {'start':start.isoformat(),'end':(stop-timedelta(days=1)).isoformat(),
            'labeled_hours':eligible,'scored_hours':len(actual),
            'model':metrics(np.asarray(actual),np.asarray(predicted)) if actual else None,
            'baseline':metrics(np.asarray(actual),np.asarray(baseline)) if actual else None}
