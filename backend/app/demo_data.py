"""Explicit synthetic traffic sandbox. Never writes observations/real ML registry."""
import csv
import hashlib
import io
import json
import logging
import math
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from .config import DATA, PRODUCTION
from .db import get_db, get_database, now, stamp, MongoSession
from .models import Segment
from .history import LOCAL, window, summary
from .forecast_data import features, examples, split_indices, CLASSES, STEP
from .security import admin

router=APIRouter(prefix='/api/demo',tags=['Synthetic traffic'])
FOLDER=DATA/'demo-forecasts'
_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='demo-data')
_job_lock=threading.Lock()
_schedule_lock=threading.Lock()
_pending=None
_models={};_reports={}
LABELS={'FREE':'Thông thoáng','SLOW':'Đông xe','JAM':'Ùn tắc'}
NOTICE='Dữ liệu mô phỏng để học và chạy thử; không phản ánh giao thông thực tế.'


def enabled(): return os.getenv('DEMO_DATA_ENABLED','false' if PRODUCTION else 'true').lower()=='true'


@lru_cache(maxsize=128)
def day_rows(segment_id,day,seed=42):
    """Deterministic rush hours, weekends, road variation and occasional incidents."""
    digest=hashlib.sha256(f'{seed}:{segment_id}:{day.isoformat()}'.encode()).digest()
    rng=np.random.default_rng(int.from_bytes(digest[:8],'little'))
    capacity=32+segment_id%5*7;free_speed=32+segment_id%4*3
    shift=(segment_id%5-2)*.16;weekend=.63 if day.weekday()>=5 else 1.
    incident=rng.random()<.12;hour=np.arange(288)/12
    noise=rng.normal(0,.035,288)
    for slot in range(1,288):noise[slot]+=.84*noise[slot-1]
    morning=np.exp(-((hour-7.7-shift)/1.05)**2);evening=np.exp(-((hour-17.3-shift)/1.3)**2)
    season=1+.09*math.cos(day.timetuple().tm_yday*math.tau/365.25)
    extra=.33*np.exp(-((hour-13.3)/.6)**2) if incident else 0.
    pressure=np.clip(.12+.06*(segment_id%3)+weekend*season*(.55*morning+.64*evening)+extra+noise,0,1)
    ratio=np.clip(1.-1.05*pressure-.11*(morning+evening)+rng.normal(0,.025,288),.06,1.)
    counts=np.maximum(0,np.rint(pressure*capacity+rng.normal(0,2,288))).astype(int)
    return [{'minute':slot*5,'score':round(float(pressure[slot]),4),'count':int(counts[slot]),
             'speed_kmh':round(float(free_speed*ratio[slot]),1),'state':'JAM' if ratio[slot]<.3 else 'SLOW' if ratio[slot]<.65 else 'FREE'} for slot in range(288)]


def feature_row(day,row):
    at=datetime.combine(day,datetime.min.time(),LOCAL)+timedelta(minutes=row['minute'])
    return {'at':at,'score':row['score'],'count':row['count'],'high_share':int(row['state']=='JAM'),
            'low_share':int(row['state']=='FREE'),'severity':CLASSES['congestion'].index(row['state']),'sample_minutes':5,
            'speed_kmh':row['speed_kmh']}


def _active(database): return database.demo_registry.find_one({'_id':'active'})

def artifacts_ready(active):
    if not active:return False
    try:folder=FOLDER/str(uuid.UUID(active['run_id']))
    except (ValueError,KeyError):return False
    names=['metadata.json','xgb-15.json','xgb-30.json']
    if active.get('generator_version',1)>=2 and active.get('history_days',0)>=60:names+=['outlook.json','outlook-metadata.json']
    return all((folder/name).is_file() for name in names)


def status(database):
    active=_active(database);job=database.demo_registry.find_one({'_id':'job'}) or {}
    return {'enabled':enabled(),'ready':artifacts_ready(active),'running':bool(job.get('running')),'message':job.get('message','Chưa tạo bộ dữ liệu mẫu.'),
            'planning_ready':bool(active and active.get('generator_version',1)>=2 and active.get('history_days',0)>=60 and artifacts_ready(active)),
            'segment_ids':active['segment_ids'] if active else [],'generated_at':active.get('created_at') if active else None,
            'model':'XGBoost','history_days':active.get('history_days') if active else None,'notice':NOTICE,'is_demo':True}


def prepare_demo(database,days=365,estimators=96):
    if not enabled(): raise ValueError('Dữ liệu mô phỏng đang tắt.')
    if not _job_lock.acquire(blocking=False): return False
    run_id=str(uuid.uuid4());folder=FOLDER/run_id
    try:
        database.demo_profiles.create_index([('dataset_id',1),('segment_id',1),('date',1)],unique=True)
        database.demo_registry.update_one({'_id':'job'},{'$set':{'running':True,'message':'Đang tổng hợp lịch sử giao thông…','updated_at':stamp()}},upsert=True)
        # Append one clearly marked sample road; never rename/overwrite existing roads.
        if not database.segments.find_one({'name':'Hoàng Quốc Việt'}):
            with MongoSession(database) as db:
                db.add(Segment(name='Hoàng Quốc Việt',start_node='hqv_west',end_node='hqv_east',distance_km=2.2,
                               geometry=[[21.0467,105.7865],[21.0469,105.8073]],is_demo=True));db.commit()
        roads=list(database.segments.find({'active':True}).sort('_id',1))[:20]
        if not roads: raise ValueError('Cần ít nhất một tuyến đường để mô phỏng.')
        ids=[r['_id'] for r in roads];today=now().astimezone(LOCAL).date();days=max(9,min(365,days))
        from .calendar_forecast import hourly_slots,train_calendar
        docs=[];series={sid:{} for sid in ids};labels={};profiles={sid:{} for sid in ids}
        for offset in range(days,-1,-1):
            day=today-timedelta(days=offset)
            for sid in ids:
                rows=day_rows(sid,day)
                hours=hourly_slots(rows);profiles[sid][day]=hours
                docs.append({'dataset_id':run_id,'segment_id':sid,'date':day.isoformat(),'source':'synthetic','slots':rows,'hourly':hours})
                if today-timedelta(days=8)<=day<today:
                    for row in rows:
                        item=feature_row(day,row);at=item['at'];series[sid][at]=item;labels[(sid,at)]=row['state']
                if len(docs)>=28:
                    database.demo_profiles.insert_many(docs,ordered=False);docs=[]
            if offset%30==0:database.demo_registry.update_one({'_id':'job'},{'$set':{'message':f'Đang chuẩn bị lịch sử: {days-offset}/{days} ngày…'}})
        if docs:database.demo_profiles.insert_many(docs,ordered=False)
        folder.mkdir(parents=True,exist_ok=True)
        from xgboost import XGBClassifier
        from .forecast_ml import metrics
        report={'is_demo':True,'notice':NOTICE,'seed':42,'model':'XGBoost','segment_ids':ids,
                'history_days':days,'created_at':stamp(),'horizons':{},'training_end':datetime.combine(today,datetime.min.time(),LOCAL).isoformat()}
        for horizon in (15,30):
            database.demo_registry.update_one({'_id':'job'},{'$set':{'message':'Đang cập nhật dự tính giao thông…'}})
            data=examples(series,labels,ids,'congestion',horizon);train,val,test=split_indices(data,horizon)
            raw=data['x'].reshape(len(data['x']),-1)
            mean=raw[train].mean(0);std=np.maximum(raw[train].std(0),.001)
            x=((raw-mean)/std).astype(np.float32);y=data['y']
            model=XGBClassifier(n_estimators=estimators,max_depth=4,learning_rate=.09,subsample=.9,colsample_bytree=.9,
                                objective='multi:softprob',num_class=3,tree_method='hist',n_jobs=1,random_state=42,
                                eval_metric='mlogloss',early_stopping_rounds=12)
            model.fit(x[train],y[train],eval_set=[(x[val],y[val])],verbose=False)
            model.save_model(folder/f'xgb-{horizon}.json')
            report['horizons'][str(horizon)]={'mean':mean.tolist(),'std':std.tolist(),
                'validation':metrics(y[val],model.predict(x[val])), 'test':metrics(y[test],model.predict(x[test])),
                'baseline':metrics(y[test],data['baseline'][test]),
                'train_label_end':float((data['times'][train]+horizon*60).max()),'validation_issue_start':float(data['times'][val].min()),
                'validation_label_end':float((data['times'][val]+horizon*60).max()),'test_issue_start':float(data['times'][test].min())}
        (folder/'metadata.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        if days>=60:
            database.demo_registry.update_one({'_id':'job'},{'$set':{'message':'Đang chuẩn bị dự báo cho những ngày tới…'}})
            train_calendar(folder,profiles,ids,estimators=min(72,estimators))
        previous=_active(database)
        database.demo_registry.replace_one({'_id':'active'},{'_id':'active','run_id':run_id,'segment_ids':ids,'created_at':stamp(),'history_days':days,'generator_version':2},upsert=True)
        database.demo_registry.update_one({'_id':'job'},{'$set':{'running':False,'message':'Lịch sử và dự báo đã sẵn sàng.','updated_at':stamp()}})
        _reports.clear()
        # Only obsolete synthetic datasets in this dedicated collection are removed.
        keep=[run_id]+([previous['run_id']] if previous else [])
        database.demo_profiles.delete_many({'source':'synthetic','dataset_id':{'$nin':keep}})
        return True
    except Exception:
        logging.getLogger('smarteye.demo').exception('Synthetic dataset preparation failed')
        database.demo_registry.update_one({'_id':'job'},{'$set':{'running':False,'message':'Chưa chuẩn bị được lịch sử. Vui lòng thử lại hoặc liên hệ người quản lý.','updated_at':stamp()}},upsert=True)
        raise
    finally: _job_lock.release()


def start_demo(database=None,force=False):
    global _pending
    database=database if database is not None else get_database()
    active=_active(database);wanted=max(9,min(365,int(os.getenv('DEMO_HISTORY_DAYS','365'))))
    if not enabled() or not force and artifacts_ready(active) and active.get('generator_version',1)>=2 and active.get('history_days',0)>=wanted:return
    def work():
        try: prepare_demo(database,days=wanted,estimators=int(os.getenv('DEMO_ESTIMATORS','96')))
        except Exception: pass
    with _schedule_lock:
        if _job_lock.locked() or _pending is not None and not _pending.done(): return
        _pending=_executor.submit(work)


def require_active(database):
    if not enabled(): raise HTTPException(503,'Dữ liệu mẫu đang tắt.')
    active=_active(database)
    if not artifacts_ready(active): raise HTTPException(409,'Dữ liệu mẫu đang được chuẩn bị. Vui lòng chờ một lát.')
    return active


def rows_for(database,active,sid,first,last):
    # Extend replay on a new day without retraining or using real observations.
    today=now().astimezone(LOCAL).date()
    output=[]
    query={'dataset_id':active['run_id'],'segment_id':sid,'date':{'$gte':first.astimezone(LOCAL).date().isoformat(),'$lte':last.astimezone(LOCAL).date().isoformat()}}
    documents={doc['date']:doc for doc in database.demo_profiles.find(query)}
    day=max(first.astimezone(LOCAL).date(),today-timedelta(days=active.get('history_days',365)))
    while day<=min(last.astimezone(LOCAL).date(),today):
        if day.isoformat() not in documents:
            from .calendar_forecast import hourly_slots
            slots=day_rows(sid,day)
            doc={'source':'synthetic','slots':slots,'hourly':hourly_slots(slots),'date':day.isoformat()}
            database.demo_profiles.update_one({'dataset_id':active['run_id'],'segment_id':sid,'date':day.isoformat()},
                {'$setOnInsert':{'source':'synthetic','slots':doc['slots'],'hourly':doc['hourly']}},upsert=True)
            documents[day.isoformat()]=doc
        day+=timedelta(days=1)
    for doc in documents.values():
        day=datetime.fromisoformat(doc['date']).date()
        for row in doc['slots']:
            item=feature_row(day,row)
            if first<=item['at']<=last: output.append(item)
    return sorted(output,key=lambda row:row['at'])


def predict_demo(database,sid,issue=None):
    active=require_active(database)
    if sid not in active['segment_ids']: raise HTTPException(404,'Tuyến này chưa có trong bộ mô phỏng.')
    issue=issue or now().astimezone(LOCAL);issue=issue.replace(minute=issue.minute//5*5,second=0,microsecond=0)
    rows=rows_for(database,active,sid,issue-timedelta(hours=2),issue)
    if len(rows)<12: raise HTTPException(409,'Chưa đủ lịch sử mẫu cho thời điểm này.')
    rows=rows[-12:]
    if any(rows[i]['at']-rows[i-1]['at']!=STEP for i in range(1,12)): raise HTTPException(409,'Chuỗi dữ liệu mẫu bị thiếu mốc.')
    folder=FOLDER/str(uuid.UUID(active['run_id']))
    if active['run_id'] not in _models:
        from xgboost import XGBClassifier
        metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'));models={}
        for horizon in (15,30):
            model=XGBClassifier(n_jobs=1);model.load_model(folder/f'xgb-{horizon}.json');models[horizon]=model
        # Keep the old immutable entry while concurrent requests finish.
        _models[active['run_id']]=(metadata,models)
    metadata,models=_models[active['run_id']];raw=features(rows,active['segment_ids'],sid).reshape(1,-1)
    predictions=[]
    for horizon in (15,30):
        info=metadata['horizons'][str(horizon)];x=((raw-np.asarray(info['mean']))/np.asarray(info['std'])).astype(np.float32)
        label=CLASSES['congestion'][int(models[horizon].predict(x)[0])]
        predictions.append({'horizon_minutes':horizon,'predicted_at':(issue+timedelta(minutes=horizon)).isoformat(),'label':label,'model':'XGBoost'})
    current=rows[-1];state=CLASSES['congestion'][current['severity']]
    return {'is_demo':True,'state':'ready','target':'congestion','segment_id':sid,'issue_at':issue.isoformat(),'run_id':active['run_id'],
            'message':NOTICE,'current':{'label':state,'speed_kmh':current['speed_kmh'],'count':current['count']},'predictions':predictions}


def current_states(database):
    active=require_active(database);result={};issue=now().astimezone(LOCAL);issue=issue.replace(minute=issue.minute//5*5,second=0,microsecond=0)
    for sid in active['segment_ids']:
        rows=rows_for(database,active,sid,issue-timedelta(minutes=10),issue)
        if rows:
            row=rows[-1];label=CLASSES['congestion'][row['severity']]
            result[sid]={'id':-sid,'segment_id':sid,'density':{'FREE':'LOW','SLOW':'NORMAL','JAM':'HIGH'}[label],
                         'congestion':label,'speed_kmh':row['speed_kmh'],'score':row['score'],'count':row['count'],
                         'source':'simulation','observed_at':row['at'].isoformat(),'is_demo':True}
    return result


@router.get('/status')
def demo_status(db=Depends(get_db)): return status(db.database)


@router.post('/prepare',status_code=202)
def demo_prepare(user=Depends(admin),db=Depends(get_db)):
    if not enabled(): raise HTTPException(503,'Dữ liệu mẫu đang tắt.')
    start_demo(db.database,force=True)
    return {'message':'Đang tạo lại dữ liệu mô phỏng ở vùng riêng; dữ liệu thực được giữ nguyên.','is_demo':True}


@router.get('/predict')
def prediction(segment_id:int,issue_at:datetime|None=None,db=Depends(get_db)):
    if issue_at and (not issue_at.tzinfo or not now()-timedelta(days=30)<=issue_at<=now()):
        raise HTTPException(422,'Mốc chạy thử cần múi giờ và nằm trong 30 ngày đã qua.')
    return predict_demo(db.database,segment_id,issue_at.astimezone(LOCAL) if issue_at else None)


@router.get('/history')
def history(segment_id:int,period:str='day',value:str|None=None,db=Depends(get_db)):
    active=require_active(db.database)
    if segment_id not in active['segment_ids']: raise HTTPException(404,'Tuyến chưa có dữ liệu mẫu.')
    if period=='year':
        from .calendar_forecast import annual_report
        return annual_report(db.database,active,segment_id)
    value=value or now().astimezone(LOCAL).date().isoformat()[:7 if period=='month' else 10]
    first,last=window(period,value);key=(active['run_id'],segment_id,period,value,int(now().timestamp()//300))
    if key in _reports:return _reports[key]
    rows=rows_for(db.database,active,segment_id,first,min(last-timedelta(microseconds=1),now()))
    hourly=[{**summary([r for r in rows if r['at'].hour==hour]),'hour':hour} for hour in range(24)]
    daily=[];heatmap=[];day=first
    while day<last:
        local=[r for r in rows if r['at'].date()==day.date()]
        daily.append({'date':day.date().isoformat(),**summary(local)})
        heatmap.extend({'date':day.date().isoformat(),'hour':h,**summary([r for r in local if r['at'].hour==h])} for h in range(24))
        day+=timedelta(days=1)
    road=db.database.segments.find_one({'_id':segment_id}) or {}
    report={'is_demo':True,'segment_id':segment_id,'segment_name':road.get('name','Tuyến mẫu'),'period':period,'value':value,'timezone':'UTC+7',
            'generated_at':stamp(),'summary':{**summary(rows),'raw_samples':len(rows),'coverage_percent':round(len(rows)/max(1,(min(last,now())-first).total_seconds()/300)*100,1)},
            'hourly':hourly,'daily':daily,'heatmap':heatmap,'peak_hours':sorted((r for r in hourly if (r['high_share'] or 0)>=.25),key=lambda r:r['high_share'],reverse=True)[:4],
            'method':NOTICE,'pattern_requirement':'Khung giờ tính từ lịch sử mô phỏng; không phải kết luận về tuyến đường thực.'}
    if len(_reports)>64:_reports.clear()
    _reports[key]=report
    return report


@router.get('/export.csv')
def export(segment_id:int,days:int=Query(default=365,ge=1,le=365),db=Depends(get_db)):
    active=require_active(db.database)
    if segment_id not in active['segment_ids']:raise HTTPException(404,'Tuyến chưa có dữ liệu mẫu.')
    rows=rows_for(db.database,active,segment_id,now()-timedelta(days=days),now())
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['segment_id','observed_at','score','count','speed_kmh','state','source'])
    for row in rows:writer.writerow([segment_id,row['at'].isoformat(),row['score'],row['count'],row['speed_kmh'],CLASSES['congestion'][row['severity']],'synthetic'])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=traffic-SYNTHETIC.csv'})
