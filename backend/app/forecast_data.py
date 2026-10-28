"""Five-minute supervised windows. Features never read beyond their issue time."""
import math
from collections import Counter, defaultdict
from datetime import timedelta
import numpy as np
from .history import road_slots, parse_timestamp, LOCAL
from .db import now

STEP = timedelta(minutes=5)
LOOKBACK = 12
HORIZONS = (15, 30)
MIN_DAYS = 7
MIN_WINDOWS = 180
MAX_RAW = 300_000
CLASSES = {'density':['LOW','NORMAL','HIGH'], 'congestion':['FREE','SLOW','JAM']}


class DataNotReady(ValueError):
    pass


def load_series(database, segment_ids, start, end):
    query={'segment_id':{'$in':segment_ids},'observed_at':{'$gte':start.isoformat(),'$lt':end.isoformat()}}
    if database.traffic_samples.count_documents(query,limit=MAX_RAW+1)+database.observations.count_documents(query,limit=MAX_RAW+1)>MAX_RAW:
        raise DataNotReady('Khoảng dữ liệu quá lớn. Chọn ít tuyến hoặc khoảng thời gian ngắn hơn (tối đa 300.000 mẫu).')
    slots,raw=road_slots(database,segment_ids,start,end)
    series=defaultdict(dict)
    for row in slots:
        # Require observations in at least three separate minutes, not one frame.
        at=row['at'].astimezone(start.tzinfo)+STEP
        if row['sample_minutes']>=3 and at<=min(end,now()):
            series[row['segment_id']][at]=row
    labels={(r['segment_id'],parse_timestamp(r['observed_at'])):r['state']
            for r in database.traffic_labels.find({'segment_id':{'$in':segment_ids},
                'observed_at':{'$gte':start.isoformat(),'$lte':end.isoformat()}})}
    return series,labels,raw,len(slots)


def features(rows, vocabulary, segment_id):
    values=[]
    for row in rows:
        at=row['at'].astimezone(LOCAL)
        hour=(at.hour+at.minute/60)*2*math.pi/24
        week=at.weekday()*2*math.pi/7
        values.append([row['score'],math.log1p(row['count']),row['high_share'],row['low_share'],
            math.sin(hour),math.cos(hour),math.sin(week),math.cos(week),
            *[float(sid==segment_id) for sid in vocabulary]])
    return np.asarray(values,dtype=np.float32)


def examples(series,labels,vocabulary,target,horizon):
    x=[];y=[];baseline=[];times=[];roads=[]
    names=CLASSES[target]
    for sid in vocabulary:
        samples=series.get(sid,{})
        for issue in sorted(samples):
            history=[samples.get(issue-STEP*i) for i in reversed(range(LOOKBACK))]
            if any(row is None for row in history): continue
            future=issue+timedelta(minutes=horizon)
            if target=='density':
                next_row=samples.get(future)
                if next_row is None: continue
                label=names[next_row['severity']];current=names[samples[issue]['severity']]
            else:
                label=labels.get((sid,future));current=labels.get((sid,issue))
                if label not in names or current not in names: continue
            x.append(features(history,vocabulary,sid));y.append(names.index(label))
            baseline.append(names.index(current));times.append(issue.timestamp());roads.append(sid)
    order=np.argsort(times,kind='stable')
    shape=(0,LOOKBACK,8+len(vocabulary))
    return {'x':np.asarray(x,dtype=np.float32)[order] if x else np.empty(shape,dtype=np.float32),
            'y':np.asarray(y,dtype=np.int64)[order], 'baseline':np.asarray(baseline,dtype=np.int64)[order],
            'times':np.asarray(times)[order], 'roads':np.asarray(roads,dtype=np.int64)[order]}


def split_indices(data,horizon):
    times=np.unique(data['times'])
    if len(times)<10: raise DataNotReady('Chưa đủ cửa sổ thời gian để chia train/validation/test.')
    a,b=times[int(len(times)*.6)],times[int(len(times)*.8)]
    # A training/validation label must be earlier than the next split's issue time.
    end=data['times']+horizon*60
    masks=[end<a,(data['times']>=a)&(end<b),data['times']>=b]
    indices=[np.flatnonzero(mask) for mask in masks]
    if any(len(idx)<25 for idx in indices):
        raise DataNotReady('Mỗi phần train/validation/test cần tối thiểu 25 cửa sổ sau khi chừa khoảng cách dự báo.')
    if any(np.sum(data['y'][indices[0]]==label)<10 for label in range(3)):
        raise DataNotReady('Tập huấn luyện cần ít nhất 10 ví dụ cho mỗi trạng thái.')
    return indices


def prepare(database,segment_ids,start,end,target):
    series,labels,raw,slots=load_series(database,segment_ids,start,end)
    days={at.astimezone(LOCAL).date() for samples in series.values() for at in samples}
    result={'raw_samples':raw,'observed_slots':slots,'usable_slots':sum(map(len,series.values())),
        'observed_days':len(days),'label_count':len(labels),'horizons':{},'ready':True,
        'requirements':'Ít nhất 7 ngày, 180 cửa sổ/mốc; lịch sử liên tục 60 phút, mỗi ô có mẫu ở ít nhất 3 phút; đủ 3 lớp trong train.'}
    datasets={}
    for horizon in HORIZONS:
        data=examples(series,labels,segment_ids,target,horizon)
        reason=None
        try:
            if len(days)<MIN_DAYS: raise DataNotReady('Cần dữ liệu ít nhất 7 ngày khác nhau.')
            if len(data['y'])<MIN_WINDOWS: raise DataNotReady('Cần ít nhất 180 cửa sổ có lịch sử liên tục và nhãn tương lai.')
            indices=split_indices(data,horizon)
            data['indices']=indices
        except DataNotReady as exc:
            reason=str(exc);result['ready']=False
        result['horizons'][str(horizon)]={'windows':len(data['y']),
            'class_counts':{name:int(np.sum(data['y']==i)) for i,name in enumerate(CLASSES[target])},
            'ready':reason is None,'reason':reason}
        datasets[horizon]=data
    return result,datasets
