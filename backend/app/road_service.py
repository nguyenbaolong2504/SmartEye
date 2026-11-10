"""Scoped current conditions and forecasts with explicit age and provenance."""
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from .db import get_db, now, stamp
from .models import Segment, Camera
from .business_models import DataSource, RoadReading, Warning
from .business_common import road, period, utc
from .security import can, permit

router=APIRouter()
STATE_TEXT={'FREE':'Thông thoáng','SLOW':'Bình thường','JAM':'Ùn tắc',None:'Chưa xác định'}


def current(db,segment_id,direction='forward',data_mode='observed'):
    segment=road(db,segment_id,direction)
    result={'segment_id':segment_id,'segment_name':segment.name,'direction':direction,
            'start_node':segment.start_node if direction=='forward' else segment.end_node,
            'end_node':segment.end_node if direction=='forward' else segment.start_node,
            'geometry':segment.geometry if direction=='forward' else list(reversed(segment.geometry)),
            'generated_at':stamp(),'is_demo':data_mode=='demo','state':None,'text':'Chưa xác định',
            'fresh':False,'metrics':{},'observed_at':None,'source_name':None,'reason':'Chưa có dữ liệu giao thông.'}
    if data_mode=='demo':
        from .demo_data import current_states
        if direction!='forward':result['reason']='Lịch sử minh họa chưa có dữ liệu cho chiều này.';return result
        sample=current_states(db.database).get(segment_id)
        if not sample:return result
        result.update(state=sample['congestion'],text=STATE_TEXT[sample['congestion']],fresh=True,
                      observed_at=sample['observed_at'],source_name='Lịch sử minh họa',reason='Dữ liệu minh họa, không phải quan trắc ngoài thực tế.')
        result['metrics']={key:{'value':sample[key],'unit':unit,'observed_at':sample['observed_at'],'source':'Lịch sử minh họa'}
                           for key,unit in (('speed_kmh','km/h'),('count','xe tại thời điểm'),('score','chỉ số 0–1'))}
        return result
    rows=db.find(RoadReading,{'segment_id':segment_id,'direction':direction,'observed_at':{'$lte':stamp()}},sort=[('observed_at',-1)],limit=100)
    sources={s.id:s for s in db.find(DataSource,{'segment_id':segment_id,'direction':direction})}
    for sample in rows:
        source=sources.get(sample.source_id)
        if not source:continue
        if result['observed_at'] is None:result.update(observed_at=sample.observed_at,source_name=source.name,reason='Dữ liệu đã cũ, chưa được kiểm tra hoặc nguồn đang tắt.')
        if not source.active or not source.tested or sample.source_version!=source.version or now()-utc(sample.observed_at)>timedelta(minutes=source.stale_minutes):continue
        if not result['fresh']:
            result.update(fresh=True,observed_at=sample.observed_at,source_name=source.name)
        if result['state'] is None and sample.metrics.get('state') in ('FREE','SLOW','JAM'):
            result.update(state=sample.metrics.get('state'),text=STATE_TEXT.get(sample.metrics.get('state'),'Chưa xác định'),observed_at=sample.observed_at,source_name=source.name,reason='')
        for field,unit in (('speed_kmh','km/h'),('count','xe tại thời điểm'),('flow_per_minute','xe/phút'),('score','chỉ số 0–1')):
            if field not in result['metrics'] and field in sample.metrics:
                if field=='count' and sample.metrics.get('count_kind')=='crossings':
                    interval=sample.metrics.get('interval_seconds')
                    unit=f'xe/{interval:g} giây' if interval else 'xe qua điểm đếm'
                result['metrics'][field]={'value':sample.metrics[field],'unit':unit,'observed_at':sample.observed_at,'source':source.name}
    if direction=='forward':
        from .config import TTL_MINUTES
        from .traffic import latest_observations
        if not result['metrics']:
            legacy=latest_observations(db).get(segment_id)
            if legacy:
                result.update(fresh=True,observed_at=legacy.observed_at,source_name='Quan sát đã ghi nhận')
                result['metrics']={field:{'value':getattr(legacy,field),'unit':unit,'observed_at':legacy.observed_at,'source':'Quan sát đã ghi nhận'}
                                   for field,unit in (('count','xe tại thời điểm'),('score','chỉ số 0–1'))}
        if result['state'] is None:
            label=db.database.traffic_labels.find_one({'segment_id':segment_id,'observed_at':{'$gte':(now()-timedelta(minutes=TTL_MINUTES)).isoformat(),'$lte':stamp()}},sort=[('observed_at',-1)])
            if label and label['state'] in ('FREE','SLOW','JAM'):
                result.update(state=label['state'],text=STATE_TEXT[label['state']],fresh=True,observed_at=label['observed_at'],source_name='Quan sát đã xác nhận',reason='')
    if result['state'] is None and result['fresh']:result['reason']='Có một phần chỉ số. Chưa đủ căn cứ xác định tình trạng ùn tắc.'
    return result


@router.get('/api/traffic/road',dependencies=[Depends(permit('traffic.view'))])
def road_current(segment_id:int,direction:Literal['forward','reverse']='forward',data_mode:Literal['demo','observed']='observed',db=Depends(get_db)):
    return current(db,segment_id,direction,data_mode)


@router.get('/api/traffic/readings',dependencies=[Depends(permit('traffic.view'))])
def recorded_history(segment_id:int,start:str,end:str,direction:Literal['forward','reverse']='forward',db=Depends(get_db)):
    road(db,segment_id,direction)
    dates=period(start,end,max_days=31)
    if utc(end)>now():raise HTTPException(422,'Khoảng tra cứu cần nằm trong thời gian đã qua.')
    query={'segment_id':segment_id,'direction':direction,'observed_at':dates}
    if db.database.road_readings.count_documents(query,limit=1001)>1000:raise HTTPException(413,'Có nhiều bản ghi. Vui lòng thu hẹp thời gian tra cứu.')
    return [{'at':row.observed_at,'metrics':row.metrics} for row in db.find(RoadReading,query,sort=[('observed_at',-1)],limit=1000)]


@router.get('/api/traffic/forecast-options',dependencies=[Depends(permit('forecast.view'))])
def forecast_options(segment_id:int,direction:Literal['forward','reverse']='forward',data_mode:Literal['demo','observed']='demo',db=Depends(get_db)):
    road(db,segment_id,direction)
    if direction!='forward':return {'ready':False,'horizons':[],'message':'Chưa có mô hình cho chiều đường đã chọn.'}
    if data_mode=='demo':
        from .demo_data import require_active,FOLDER
        active=require_active(db.database)
        return {'ready':segment_id in active['segment_ids'] and (FOLDER/active['run_id']/'outlook.json').is_file(),
                'max_days':7,'resolution_minutes':60,'hours':list(range(24)),'model':'XGBoost','model_version':active['run_id'],'is_demo':True}
    registry=db.database.forecast_registry.find_one({'_id':'congestion'})
    run=db.database.forecast_runs.find_one({'_id':registry['run_id'],'status':'completed'}) if registry else None
    horizons=sorted(int(h) for h,info in (run or {}).get('report',{}).get('horizons',{}).items()
                    if info.get('deployable') and segment_id in info.get('supported_segment_ids',[]))
    return {'ready':bool(horizons),'horizons':horizons,'model_version':(run or {}).get('_id'),
            'message':'Chưa có mốc dự báo được hỗ trợ.' if not horizons else '', 'is_demo':False}


@router.get('/api/traffic/forecast',dependencies=[Depends(permit('forecast.view'))])
def real_forecast(segment_id:int,horizon:int,direction:Literal['forward','reverse']='forward',db=Depends(get_db)):
    options=forecast_options(segment_id,direction,'observed',db)
    if horizon not in options['horizons']:raise HTTPException(422,'Mốc hoặc chiều dự báo chưa được mô hình hỗ trợ.')
    from .forecast_ml import forecast
    try:result=forecast(db.database,segment_id,'congestion')
    except Exception:raise HTTPException(503,'Không thể lấy kết quả dự báo. Vui lòng thử lại.') from None
    if result['state']!='ready':return {**result,'direction':direction,'comparison':None,'model_version':options['model_version']}
    predictions=result.get('predictions',[])
    chosen=next((p for p in predictions if p['horizon_minutes']==horizon),None)
    if not chosen:raise HTTPException(404,'Chưa có dự báo tại mốc đã chọn.')
    actual=current(db,segment_id,direction)
    comparison={'current':actual,'forecast':chosen} if actual['state'] and actual['fresh'] else None
    return {**result,'direction':direction,'selected':chosen,'predictions':sorted(predictions,key=lambda p:p['predicted_at']),
            'comparison':comparison,'comparison_message':None if comparison else 'Chưa có dữ liệu hiện tại đủ mới để so sánh.',
            'model_version':options['model_version'],'generated_at':stamp(),'is_demo':False}


@router.get('/api/management/monitor')
def monitor(segment_id:int,direction:Literal['forward','reverse']='forward',user=Depends(permit('monitor.view')),db=Depends(get_db)):
    road(db,segment_id,direction,user)
    errors={}
    try:actual=current(db,segment_id,direction)
    except Exception:actual=None;errors['current']='Chưa tải được dữ liệu giao thông.'
    from .sources import source_state
    try:sources=[{'id':s.id,'name':s.name,'kind':s.kind,'active':s.active,'state':source_state(s),'last_received_at':s.last_received_at,'checked_at':s.checked_at}
                 for s in db.find(DataSource,{'segment_id':segment_id,'direction':direction})]
    except Exception:sources=[];errors['sources']='Chưa tải được trạng thái nguồn.'
    try:
        from .warnings import public_data
        warnings=[v for w in db.find(Warning,{'segment_id':segment_id,'direction':direction},limit=100) if (v:=public_data(w))] if can(user,'warnings.view') else []
    except Exception:warnings=[];errors['warnings']='Chưa tải được cảnh báo.'
    try:
        from .forecast_ml import forecast
        predictions=forecast(db.database,segment_id,'congestion') if direction=='forward' and can(user,'forecast.view') else {'state':'unavailable','predictions':[],'message':'Chưa có mô hình cho chiều này.'}
    except Exception:predictions={'state':'unavailable','predictions':[]};errors['forecast']='Chưa tải được dự báo.'
    camera_sources=db.find(DataSource,{'segment_id':segment_id,'direction':direction,'kind':'camera','active':True,'tested':True}) if can(user,'monitor.camera') else []
    # Browser media requests are direct, public HTTPS only, without secrets.
    cameras=[{'id':s.id,'name':s.name,'url':f'/api/management/cameras/{s.id}/preview','format':s.format,
              'checked_at':s.checked_at,'state':source_state(s),'message':'Nguồn chưa cung cấp thời điểm quay; không khẳng định hình ảnh trực tiếp.'} for s in camera_sources]
    readings=db.find(RoadReading,{'segment_id':segment_id,'direction':direction,'observed_at':{'$gte':(now()-timedelta(hours=1)).isoformat(),'$lte':stamp()}},sort=[('observed_at',1)],limit=500)
    return {'current':actual,'forecast':predictions,'warnings':warnings,'sources':sources,'cameras':cameras,
            'series':[{'at':r.observed_at,'metrics':r.metrics} for r in readings],'errors':errors,'checked_at':stamp()}
