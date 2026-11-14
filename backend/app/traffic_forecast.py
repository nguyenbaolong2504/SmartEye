"""Physical traffic extension of the existing ForecastRun / registry workflow."""
import json
from collections import Counter,defaultdict
from datetime import timedelta
import numpy as np
from .db import now,stamp
from .history import parse_timestamp,LOCAL
from .forecast_data import STEP,LOOKBACK,DataNotReady
from .traffic_windows import load
from .traffic_learning import STATES,FIELDS,sequence_features,partition,fit_models
from .traffic_metrics import quantities

HORIZONS=(15,30,60)
_cache={}


def dataset(database,ids,start,end,direction='forward'):
    docs=load(database,ids,start,end,direction)
    if len(docs)>100000:raise DataNotReady('Tối đa 100.000 ô; hãy chọn ít đường hoặc rút ngắn thời gian.')
    series=defaultdict(dict)
    for doc in docs:
        if not doc.get('usable'):continue
        at=parse_timestamp(doc['window_end'])
        series[doc['segment_id']][at]={**doc,'at':at}
    return series,len(docs)


def examples(series,ids,horizon):
    values=[];labels=[];times=[];roads=[];baseline=[];historical=[];speeds=[];free=[];current=[]
    for sid,samples in series.items():
      for issue,row in sorted(samples.items()):
        rows=[samples.get(issue-STEP*i) for i in reversed(range(LOOKBACK))]
        future=samples.get(issue+timedelta(minutes=horizon))
        if any(value is None for value in rows) or not future:continue
        label=future.get('verified_state');present=row.get('verified_state')
        if label not in STATES or present not in STATES:continue
        vfree=row['free_flow_speed_kmh']
        history=[samples.get(issue+timedelta(minutes=horizon)-timedelta(days=day),{}).get('verified_state') for day in (7,14,21,28)]
        votes=[state for state in history if state in STATES]
        previous=Counter(votes).most_common(1)[0][0] if votes else present
        features=sequence_features(rows,ids,sid)
        # Historical frequencies use only earlier matching weekdays, not the
        # future observation being predicted or the entire dataset's label mix.
        values.append(np.concatenate([features,[sum(v=='JAM' for v in votes)/len(votes) if votes else 0.,len(votes)/4]]));labels.append(STATES.index(label))
        times.append(issue.timestamp());roads.append(sid);baseline.append(STATES.index(present));historical.append(STATES.index(previous))
        speeds.append(future['metrics']['avg_speed_kmh']/vfree);free.append(vfree);current.append(row['metrics']['avg_speed_kmh'])
    order=np.argsort(times,kind='stable')
    return {key:np.asarray(value,dtype=np.float32 if key in ('x','speed_ratio','free_speed','current_speed') else np.int64 if key not in ('times',) else float)[order]
        for key,value in dict(x=values,y=labels,times=times,roads=roads,baseline=baseline,historical=historical,
                              speed_ratio=speeds,free_speed=free,current_speed=current).items()}


def prepare(database,ids,start,end,direction='forward'):
    series,raw=dataset(database,ids,start,end,direction)
    days={at.astimezone(LOCAL).date() for rows in series.values() for at in rows}
    labels=sum(row.get('verified_state') in STATES for rows in series.values() for row in rows.values())
    report={'ready':True,'raw_samples':raw,'usable_slots':sum(len(rows) for rows in series.values()),
        'observed_days':len(days),'label_count':labels,'horizons':{},
        'requirements':'Ít nhất 7 ngày; mỗi ô 5 phút có ≥240 giây quan trắc, chiều đường riêng, tốc độ/kích thước đã đo và quyền huấn luyện. Cần 60 phút liên tiếp và nhãn thực tế độc lập. Bốn phần thời gian train/validation/calibration/test có khoảng cách bằng mốc dự báo.'}
    datasets={}
    for horizon in HORIZONS:
        data=examples(series,ids,horizon);reason=None
        try:
            if len(days)<7 or len(data['y'])<180:raise DataNotReady('Cần ít nhất 7 ngày và 180 cửa sổ có nhãn thực tế, tốc độ đã hiệu chuẩn.')
            partition(data,horizon)
        except DataNotReady as exc:reason=str(exc);report['ready']=False
        report['horizons'][str(horizon)]={'windows':len(data['y']),'ready':reason is None,'reason':reason,
            'class_counts':{name:int(np.sum(data['y']==i)) for i,name in enumerate(STATES)}}
        datasets[horizon]=data
    return report,datasets


def train(database,run,folder,check):
    readiness,datasets=prepare(database,run['segment_ids'],parse_timestamp(run['start_at']),parse_timestamp(run['end_at']),run.get('direction','forward'))
    if not readiness['ready']:raise DataNotReady('; '.join(value['reason'] for value in readiness['horizons'].values() if value['reason']))
    folder.mkdir(parents=True,exist_ok=True)
    report={'version':1,'feature_set':'physical_5min_v1','target':'traffic','classes':list(STATES),
        'direction':run.get('direction','forward'),'fields':list(FIELDS),'is_demo':False,'horizons':{},'data':readiness,
        'quality_policy':'Nhãn độc lập, bốn phần theo thời gian và purge. XGBoost phải vượt cả giữ nguyên trạng thái và lịch sử cùng giờ trên validation và test; Recall ùn tắc ≥50%, đủ lớp trên từng đường, ECE ≤0,1 và Brier <2/3. Tốc độ cần MAE tốt hơn giữ nguyên tốc độ trên validation và test từng đường. Không cam kết độ chính xác 80–90%.'}
    import hashlib
    for horizon,data in datasets.items():
        check(f'Đang huấn luyện tình trạng và tốc độ sau {horizon} phút')
        np.savez_compressed(folder/f'dataset-{horizon}.npz',**data)
        report['horizons'][str(horizon)]=fit_models(data,folder,horizon)
        report['horizons'][str(horizon)]['dataset_sha256']=hashlib.sha256((folder/f'dataset-{horizon}.npz').read_bytes()).hexdigest()
    (folder/'metadata.pending').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    (folder/'metadata.pending').replace(folder/'metadata.json')
    return report


def predict(database,sid,direction='forward'):
    empty=lambda state,message:{'state':state,'message':message,'segment_id':sid,'direction':direction,'target':'traffic','predictions':[]}
    registry=database.forecast_registry.find_one({'_id':f'traffic:{direction}'})
    run=database.forecast_runs.find_one({'_id':registry['run_id'],'status':'completed'}) if registry else None
    if not run:return empty('no_model','Chưa có mô hình giao thông được đưa vào sử dụng.')
    if run.get('direction','forward')!=direction or sid not in run['segment_ids']:return empty('unsupported','Mô hình chưa hỗ trợ chiều đường này.')
    if now()-parse_timestamp(run['end_at'])>timedelta(days=45):return empty('model_stale','Cần đánh giá và huấn luyện lại mô hình đã quá 45 ngày.')
    series,_=dataset(database,[sid],now()-timedelta(hours=3),now(),direction);samples=series.get(sid,{})
    if not samples:return empty('no_data','Chưa có ô quan trắc giao thông đã đo cho chiều đường này.')
    issue=max(samples)
    if now()-issue>timedelta(minutes=10):return empty('stale','Quan trắc đã quá cũ để dự báo.')
    rows=[samples.get(issue-STEP*i) for i in reversed(range(LOOKBACK))]
    if any(row is None for row in rows):return empty('insufficient','Cần đủ 60 phút quan trắc liên tiếp đã đạt chất lượng.')
    from .forecast_ml import artifact_folder
    from .camera_forecast import probabilities
    from xgboost import XGBClassifier,XGBRegressor
    past_times=[(issue+timedelta(minutes=h)-timedelta(days=day)).isoformat() for h in HORIZONS for day in (7,14,21,28)]
    past={row['window_end']:row['verified_state'] for row in database.traffic_windows.find({'segment_id':sid,'direction':direction,
        'window_end':{'$in':past_times},'usable':True,'is_demo':False,'verified_state':{'$in':list(STATES)}},{'window_end':1,'verified_state':1})}
    folder=artifact_folder(run['_id']);report=run['report']
    features=sequence_features(rows,run['segment_ids'],sid)
    predictions=[]
    for horizon in HORIZONS:
        info=report.get('horizons',{}).get(str(horizon),{})
        if not info.get('deployable') or sid not in info.get('supported_segment_ids',[]):continue
        votes=[past.get((issue+timedelta(minutes=horizon)-timedelta(days=day)).isoformat()) for day in (7,14,21,28)]
        votes=[state for state in votes if state in STATES]
        x=np.concatenate([features,[sum(v=='JAM' for v in votes)/len(votes) if votes else 0.,len(votes)/4]])[None]
        cache_key=(run['_id'],horizon)
        if cache_key not in _cache:
            model=XGBClassifier(n_jobs=1);model.load_model(folder/f'traffic-{horizon}.json')
            reg=XGBRegressor(n_jobs=1);reg.load_model(folder/f'speed-{horizon}.json')
            if len(_cache)>=9:_cache.pop(next(iter(_cache)))
            _cache[cache_key]=(model,reg)
        model,reg=_cache[cache_key];p=probabilities(model.predict_proba(x),info['temperature'])[0]
        predicted_at=(issue+timedelta(minutes=horizon)).isoformat()
        value={'horizon_minutes':horizon,'predicted_at':predicted_at,'label':STATES[int(p.argmax())],'model':'XGBoost',
            'probabilities':dict(zip(STATES,map(float,p))),'jam_probability':float(p[2]),'probability_calibrated':True,
            'history':{'matching_days':len(votes),'jam_days':votes.count('JAM'),'lookback_days':28,'same_weekday':True},
            'test_macro_f1':info['test']['XGBoost']['macro_f1']}
        if info.get('speed_deployable') and sid in info.get('speed_supported_segment_ids',[]):
            speed=float(min(160,np.clip(reg.predict(x)[0],0,2)*rows[-1]['free_flow_speed_kmh']))
            metrics=quantities(speed_kmh=speed,speed_verified=True,free_flow_speed_kmh=rows[-1]['free_flow_speed_kmh'])
            value.update(predicted_speed_kmh=speed,predicted_congestion_index=metrics['congestion_index'],predicted_travel_time_index=metrics['travel_time_index'])
        predictions.append(value)
        ident=f"{run['_id']}:{sid}:{direction}:{issue.isoformat()}:{horizon}"
        database.traffic_forecast_outcomes.update_one({'_id':ident},{'$setOnInsert':{**value,'segment_id':sid,
            'direction':direction,'run_id':run['_id'],'issue_at':issue.isoformat(),'evaluated':False,'created_at':stamp()}},upsert=True)
    return {'state':'ready' if predictions else 'unsupported','segment_id':sid,'direction':direction,'target':'traffic',
        'issue_at':issue.isoformat(),'run_id':run['_id'],'model_version':'physical_5min_v1','is_demo':False,
        'current':rows[-1]['metrics'],'predictions':predictions,'message':'Dự báo từ quan trắc đã đạt chất lượng; chỉ phục vụ các mốc vượt kiểm tra độc lập.'}


def refresh_active(database):
    for direction in ('forward','reverse'):
        registry=database.forecast_registry.find_one({'_id':f'traffic:{direction}'})
        run=database.forecast_runs.find_one({'_id':registry['run_id'],'status':'completed'}) if registry else None
        if run:
            for sid in run['segment_ids'][:20]:predict(database,sid,direction)


def route_values(database,request,segments):
    """Use real, direction-specific predictions only near their stated timestamp."""
    if getattr(request,'traffic_mode','observed')!='observed':return {}
    departure=request.departure_at or now();result={}
    for direction in ('forward','reverse'):
      registry=database.forecast_registry.find_one({'_id':f'traffic:{direction}'})
      run=database.forecast_runs.find_one({'_id':registry['run_id'],'status':'completed'}) if registry else None
      if not run:continue
      for road in segments:
        if road.id not in run['segment_ids'] or road.is_demo:continue
        output=predict(database,road.id,direction)
        matches=[p for p in output.get('predictions',[]) if p.get('predicted_speed_kmh',0)>0 and
                 abs((departure-parse_timestamp(p['predicted_at'])).total_seconds())<=150]
        if matches:
            row=min(matches,key=lambda p:abs((departure-parse_timestamp(p['predicted_at'])).total_seconds()))
            result[(road.id,direction)]={'speed':row['predicted_speed_kmh'],'risk':row['jam_probability'],'source':'forecast_speed',
                'predicted_at':row['predicted_at'],'run_id':output['run_id']}
    return result
