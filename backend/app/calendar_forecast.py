"""Day-ahead road forecasts from past weekly patterns, never future generated rows."""
import json
import math
import time
from collections import defaultdict
from datetime import date,datetime,timedelta
from pathlib import Path
import numpy as np
from fastapi import APIRouter,Depends,HTTPException
from .db import get_db,now,stamp
from .history import LOCAL
from .forecast_data import CLASSES,split_indices

router=APIRouter()
_cache={};_models={}
LABELS={'FREE':'Thông thoáng','SLOW':'Đông xe','JAM':'Dễ ùn tắc'}


def hourly_slots(slots):
    result=[]
    for hour in range(24):
        rows=[r for r in slots if r['minute']//60==hour]
        if not rows:continue
        jam=sum(r['state']=='JAM' for r in rows)/len(rows)
        free=sum(r['state']=='FREE' for r in rows)/len(rows)
        result.append({'hour':hour,'slot_count':len(rows),'score':round(sum(r['score'] for r in rows)/len(rows),4),
            'count':round(sum(r['count'] for r in rows)/len(rows),2),'speed_kmh':round(sum(r['speed_kmh'] for r in rows)/len(rows),2),
            'jam_share':jam,'free_share':free,'state':'JAM' if jam>=.5 else 'FREE' if free>=.5 else 'SLOW'})
    return result


def vector(day,hour,sid,ids,profiles):
    # Every historical feature is at least seven days older than the target.
    past=[next((r for r in profiles.get(day-timedelta(days=lag),[]) if r['hour']==hour),None) for lag in (7,14,21,28)]
    valid=[row for row in past if row]
    if len(valid)<2:return None
    fallback={key:sum(row[key] for row in valid)/len(valid) for key in ('score','count','speed_kmh','jam_share')}
    calendar=[math.sin(hour*math.tau/24),math.cos(hour*math.tau/24),math.sin(day.weekday()*math.tau/7),
        math.cos(day.weekday()*math.tau/7),float(day.weekday()>=5),math.sin(day.timetuple().tm_yday*math.tau/365.25),
        math.cos(day.timetuple().tm_yday*math.tau/365.25),hour/23]
    history=[value for row in past for value in ((row or fallback)['score'],(row or fallback)['jam_share'],(row or fallback)['speed_kmh']/50)]
    return calendar+history+[fallback['score'],fallback['jam_share'],math.log1p(fallback['count'])]+[float(sid==i) for i in ids]


def train_calendar(folder,profiles,ids,estimators=72):
    from xgboost import XGBClassifier
    from .forecast_ml import metrics
    today=now().astimezone(LOCAL).date();x=[];y=[];times=[];baseline=[]
    for sid in ids:
        road=profiles[sid]
        for day in sorted(road):
            if day>=today:continue
            for row in road[day]:
                values=vector(day,row['hour'],sid,ids,road)
                if values is None:continue
                x.append(values);y.append(CLASSES['congestion'].index(row['state']))
                target=datetime.combine(day,datetime.min.time(),LOCAL)+timedelta(hours=row['hour'])
                times.append((target-timedelta(days=1)).timestamp())
                previous=next((r for r in road.get(day-timedelta(days=7),[]) if r['hour']==row['hour']),None)
                baseline.append(CLASSES['congestion'].index(previous['state'] if previous else 'FREE'))
    data={'x':np.asarray(x,dtype=np.float32),'y':np.asarray(y,dtype=np.int64),'times':np.asarray(times),'baseline':np.asarray(baseline)}
    train,val,test=split_indices(data,1440)
    model=XGBClassifier(n_estimators=estimators,max_depth=5,learning_rate=.08,subsample=.9,colsample_bytree=.9,
        objective='multi:softprob',num_class=3,tree_method='hist',n_jobs=1,random_state=42,eval_metric='mlogloss',early_stopping_rounds=12)
    model.fit(data['x'][train],data['y'][train],eval_set=[(data['x'][val],data['y'][val])],verbose=False)
    model.save_model(folder/'outlook.json')
    report={'model':'XGBoost','is_demo':True,'feature_lag_days':[7,14,21,28],'segment_ids':ids,'trained_before':today.isoformat(),
        'train_samples':len(train),'validation_samples':len(val),'test_samples':len(test),
        'validation':metrics(data['y'][val],model.predict(data['x'][val])),
        'test':metrics(data['y'][test],model.predict(data['x'][test])),
        'baseline':metrics(data['y'][test],data['baseline'][test]),
        'train_label_end':float((data['times'][train]+86400).max()),'validation_issue_start':float(data['times'][val].min()),
        'validation_label_end':float((data['times'][val]+86400).max()),'test_issue_start':float(data['times'][test].min())}
    (folder/'outlook-metadata.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    return report


def profiles_for(database,active,sid):
    # Do not use today's precomputed full-day summaries: some hours are still future.
    today=now().astimezone(LOCAL).date();key=(active['run_id'],sid,today.isoformat())
    cached=_cache.get(key)
    if cached and time.monotonic()-cached[0]<300:return cached[1]
    first=today-timedelta(days=365)
    query={'dataset_id':active['run_id'],'segment_id':sid,'date':{'$gte':first.isoformat(),'$lt':today.isoformat()}}
    result={date.fromisoformat(doc['date']):doc.get('hourly',[]) for doc in database.demo_profiles.find(query,{'date':1,'hourly':1})}
    if len(_cache)>40:_cache.pop(next(iter(_cache)))
    _cache[key]=(time.monotonic(),result)
    return result


def project_day(database,sid,target):
    from .demo_data import require_active,FOLDER
    active=require_active(database)
    if sid not in active['segment_ids']:raise HTTPException(404,'Tuyến đường chưa có đủ lịch sử.')
    folder=FOLDER/active['run_id']
    if not (folder/'outlook.json').is_file():raise HTTPException(409,'Đang chuẩn bị lịch sử để dự báo những ngày tới. Vui lòng thử lại sau.')
    cached=_models.get(active['run_id'])
    if cached is None:
        from xgboost import XGBClassifier
        model=XGBClassifier(n_jobs=1);model.load_model(folder/'outlook.json')
        cached=(model,json.loads((folder/'outlook-metadata.json').read_text(encoding='utf-8')))
        if len(_models)>2:_models.pop(next(iter(_models)))
        _models[active['run_id']]=cached
    profiles=profiles_for(database,active,sid)
    values=[vector(target,hour,sid,active['segment_ids'],profiles) for hour in range(24)]
    if any(value is None for value in values):raise HTTPException(409,'Cần thêm lịch sử các tuần trước để dự báo ngày này.')
    predictions=cached[0].predict(np.asarray(values,dtype=np.float32))
    result=[]
    for hour,prediction in enumerate(predictions):
        evidence=[r for day,rows in profiles.items() if day.weekday()==target.weekday() for r in rows if r['hour']==hour]
        jam_days=sum(r['state']=='JAM' for r in evidence)
        label=CLASSES['congestion'][int(prediction)]
        result.append({'hour':hour,'label':label,'text':LABELS[label],'similar_days':len(evidence),'jam_days':jam_days,
            'jam_frequency':round(jam_days/len(evidence),4) if evidence else None})
    return result,profiles,active


def outlook(database,sid,target,hour):
    today=now().astimezone(LOCAL).date()
    if not today<=target<=today+timedelta(days=7):raise HTTPException(422,'Chọn ngày từ hôm nay đến 7 ngày tới.')
    if not 0<=hour<=23:raise HTTPException(422,'Chọn giờ từ 0 đến 23.')
    if target==today and hour<now().astimezone(LOCAL).hour:raise HTTPException(422,'Chọn giờ chưa qua hoặc một ngày sắp tới.')
    hourly,profiles,active=project_day(database,sid,target);selected=hourly[hour]
    windows=[]
    for row in hourly:
        if row['label']!='JAM':continue
        if windows and windows[-1]['end_hour']==row['hour']:windows[-1]['end_hour']+=1
        else:windows.append({'start_hour':row['hour'],'end_hour':row['hour']+1})
    severity={'FREE':0,'SLOW':1,'JAM':2}
    alternatives=sorted((row for row in hourly if severity[row['label']]<severity[selected['label']]
        and (target!=today or row['hour']>now().astimezone(LOCAL).hour)),key=lambda row:(abs(row['hour']-hour),severity[row['label']],row['hour']))[:3]
    road=database.segments.find_one({'_id':sid}) or {}
    explanation=f"Trong {selected['similar_days']} ngày cùng thứ đã qua, có {selected['jam_days']} ngày dễ ùn tắc ở khung giờ này."
    return {'state':'ready','is_demo':True,'source':'history','segment_id':sid,'segment_name':road.get('name','Tuyến đường'),
        'date':target.isoformat(),'hour':hour,'selected':selected,'hourly':hourly,'avoid_windows':windows,'alternatives':alternatives,
        'explanation':explanation,'advice':f"Nên cân nhắc đi vào giờ khác để tránh {hour:02d}:00–{hour+1:02d}:00." if selected['label']=='JAM' else 'Có thể cân nhắc khởi hành vào giờ đã chọn; kiểm tra lại tình hình trước khi đi.',
        'history_start':min(profiles).isoformat() if profiles else None,'history_end':max(profiles).isoformat() if profiles else None,
        'history_days':len(profiles),'generated_at':stamp(),'notice':'Ước tính từ lịch sử minh họa, không phải tình trạng giao thông thực tế.'}


def aggregate(records):
    count=sum(r['slot_count'] for day,r in records);days=len({day for day,r in records})
    return {'slot_count':count,'observed_minutes':count*5,'observed_days':days,'evidence_days':days,'sufficient':days>=3 and count>=12,
        'average_score':sum(r['score']*r['slot_count'] for day,r in records)/count if count else None,
        'average_count':sum(r['count']*r['slot_count'] for day,r in records)/count if count else None,
        'high_share':sum(r['jam_share']*r['slot_count'] for day,r in records)/count if count else None,
        'low_share':sum(r['free_share']*r['slot_count'] for day,r in records)/count if count else None}


def annual_report(database,active,sid):
    profiles=profiles_for(database,active,sid);records=[(day,row) for day,rows in profiles.items() for row in rows]
    hourly=[{'hour':h,**aggregate([(d,r) for d,r in records if r['hour']==h])} for h in range(24)]
    by_month=defaultdict(list)
    for day,row in records:by_month[day.strftime('%Y-%m')].append((day,row))
    monthly=[{'month':month,**aggregate(rows)} for month,rows in sorted(by_month.items())]
    weekdays=[{'weekday':w,'hour':h,**aggregate([(d,r) for d,r in records if d.weekday()==w and r['hour']==h])} for w in range(7) for h in range(24)]
    road=database.segments.find_one({'_id':sid}) or {};stats=aggregate(records)
    return {'segment_id':sid,'segment_name':road.get('name','Tuyến đường'),'is_demo':True,'period':'year','value':'past-year',
        'generated_at':stamp(),'timezone':'UTC+7','history_start':min(profiles).isoformat() if profiles else None,
        'history_end':max(profiles).isoformat() if profiles else None,'summary':{**stats,'raw_samples':stats['slot_count'],
        'coverage_percent':round(min(100,len(profiles)/365*100),1)},'hourly':hourly,'monthly':monthly,'weekdays':weekdays,
        'daily':[],'heatmap':[],'peak_hours':sorted((r for r in hourly if (r['high_share'] or 0)>=.25),key=lambda r:r['high_share'],reverse=True)[:4],
        'method':'Lịch sử minh họa trong một năm gần nhất. Ngày chưa có quan sát không được coi là thông thoáng.','pattern_requirement':'Dùng các ngày đã qua để nhận biết khung giờ thường đông xe.'}


@router.get('/api/traffic/outlook')
def road_outlook(segment_id:int,date:date,hour:int=17,db=Depends(get_db)):
    return outlook(db.database,segment_id,date,hour)
