"""Observed-data reports and redacted, read-only operational audit views."""
import csv
import io
import re
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from .db import get_db, now, stamp
from .security import admin, permit
from .models import Audit
from .business_models import DataSource, RoadReading
from .business_common import period, road, require_global_scope, serialize, clean_csv, utc
from .history import LOCAL

router=APIRouter()
OPERATION_EVENT={'$or':[
    {'action':{'$regex':r'^(incident_|warning_|rule_|source_|forecast_|traffic_label|camera_|segment_|video_)'}},
    {'action':{'$in':['manual_observation','report_export','hourly_report_export']}},
]}


def report(db,segment_id,direction,start,end,user):
    road(db,segment_id,direction,user)
    dates=period(start,end)
    if not {'$gte','$lte'}<=dates.keys():raise HTTPException(422,'Chọn đầy đủ thời gian bắt đầu và kết thúc.')
    if utc(dates['$lte'])>now():raise HTTPException(422,'Khoảng thống kê không được ở tương lai.')
    query={'segment_id':segment_id,'direction':direction,'observed_at':dates}
    if db.database.road_readings.count_documents(query,limit=50001)>50000:raise HTTPException(413,'Khoảng tra cứu quá lớn, vui lòng thu hẹp thời gian.')
    grouped=defaultdict(lambda:{'FREE':0,'SLOW':0,'JAM':0,'unknown':0,'samples':0})
    for row in db.find(RoadReading,query,sort=[('observed_at',1)],limit=50000):
        try:hour=utc(row.observed_at).astimezone(LOCAL).strftime('%Y-%m-%d %H:00')
        except HTTPException:continue
        state=row.metrics.get('state');grouped[hour]['samples']+=1
        grouped[hour][state if state in ('FREE','SLOW','JAM') else 'unknown']+=1
    hours=[{'hour':hour,**values} for hour,values in sorted(grouped.items())]
    return {'segment_id':segment_id,'direction':direction,'start':dates['$gte'],'end':dates['$lte'],'timezone':'UTC+7',
            'source':'observed','generated_at':stamp(),'hours':hours,'samples':sum(h['samples'] for h in hours),
            'valid_samples':sum(h['samples']-h['unknown'] for h in hours),'unknown_samples':sum(h['unknown'] for h in hours)}


@router.get('/api/management/traffic-report')
@router.get('/api/admin/traffic-report',include_in_schema=False)
def statistics(segment_id:int,direction:str,start:str,end:str,user=Depends(permit('analytics.view')),db=Depends(get_db)):
    if direction not in ('forward','reverse'):raise HTTPException(422,'Chiều đường không hợp lệ.')
    return report(db,segment_id,direction,start,end,user)


@router.get('/api/management/traffic-report/export')
@router.get('/api/admin/traffic-report/export',include_in_schema=False)
def export(segment_id:int,direction:str,start:str,end:str,format:str='csv',user=Depends(permit('analytics.export')),db=Depends(get_db)):
    if format!='csv' or direction not in ('forward','reverse'):raise HTTPException(422,'Khoảng thời gian hoặc định dạng tệp chưa hợp lệ.')
    value=report(db,segment_id,direction,start,end,user);out=io.StringIO();out.write('\ufeff');writer=csv.writer(out)
    for key in ('segment_id','direction','start','end','timezone','source','generated_at','valid_samples','unknown_samples'):
        writer.writerow([key,clean_csv(value[key])])
    writer.writerow(['Ghi chú','Chỉ gồm dữ liệu quan trắc; khoảng không có mẫu không được coi là thông thoáng.'])
    writer.writerow(['hour','FREE','SLOW','JAM','unknown','samples'])
    for row in value['hours']:writer.writerow([row[k] for k in ('hour','FREE','SLOW','JAM','unknown','samples')])
    from .business_common import log_event
    log_event(db,user.id,'hourly_report_export',f'{segment_id}:{direction}')
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="smarteye-hourly-report.csv"'})


def redact(value):
    value=re.sub(r'(?i)(?:mongodb(?:\+srv)?|postgres(?:ql)?|redis)://\S+','[đã ẩn kết nối]',value)
    value=re.sub(r'(?i)(password|token|secret|api[_-]?key|authorization|credential)\s*[:=]\s*[^\s,;]+',r'\1=[đã ẩn]',value)
    value=re.sub(r'https?://[^\s/@]+:[^\s/@]+@[^\s]+','[đã ẩn địa chỉ có thông tin xác thực]',value)
    return value[:2000]


@router.get('/api/management/events')
@router.get('/api/admin/events',dependencies=[Depends(admin)],include_in_schema=False)
def events(q:str=Query(default='',max_length=100),start:str|None=None,end:str|None=None,level:str|None=None,service:str|None=None,
           user=Depends(permit('diagnostics.view')),db=Depends(get_db)):
    require_global_scope(user)
    query={};conditions=[] if user.role=='admin' else [OPERATION_EVENT]
    if q:conditions.append({'$or':[{field:{'$regex':re.escape(q),'$options':'i'}} for field in ('event_id','request_id','action','detail')]})
    if level:
        if level not in ('info','warning','error'):raise HTTPException(422,'Mức nhật ký không hợp lệ.')
        conditions.append({'$or':[{'level':'info'},{'level':{'$exists':False}}]} if level=='info' else {'level':level})
    if service:
        if service not in ('application','workflow','ingestion','forecast'):raise HTTPException(422,'Dịch vụ không hợp lệ.')
        conditions.append({'$or':[{'service':'application'},{'service':{'$exists':False}}]} if service=='application' else {'service':service})
    dates=period(start,end)
    if dates:query['created_at']=dates
    if conditions:query['$and']=conditions
    return [{**serialize(row),'detail':redact(row.detail)} for row in db.find(Audit,query,sort=[('id',-1)],limit=300)]


@router.get('/api/management/events/{ident}')
@router.get('/api/admin/events/{ident}',dependencies=[Depends(admin)],include_in_schema=False)
def event_detail(ident:int,user=Depends(permit('diagnostics.view')),db=Depends(get_db)):
    require_global_scope(user)
    query={'id':ident}
    if user.role!='admin':query.update(OPERATION_EVENT)
    item=db.find_one(Audit,query)
    if not item:raise HTTPException(404,'Không có quyền xem hoặc bản ghi đã không còn tồn tại.')
    return {**serialize(item),'detail':redact(item.detail)}


@router.get('/api/management/operations')
@router.get('/api/admin/operations',dependencies=[Depends(admin)],include_in_schema=False)
def operations(user=Depends(permit('diagnostics.view')),db=Depends(get_db)):
    require_global_scope(user)
    from .sources import source_state
    checked=stamp()
    try:db.database.command('ping');database_state='healthy'
    except Exception:database_state='unavailable'
    sources=db.find(DataSource,limit=200)
    states={key:0 for key in ('fresh','stale','unknown','error','disabled')}
    for source in sources:states[source_state(source)]+=1
    from .demo_data import artifacts_ready,_active
    demo_ready=artifacts_ready(_active(db.database))
    return {'checked_at':checked,'services':[
        {'name':'Ứng dụng','state':'healthy','checked_at':checked},
        {'name':'Cơ sở dữ liệu','state':database_state,'checked_at':checked},
        {'name':'Dự báo theo lịch sử minh họa','state':'configured' if demo_ready else 'unknown','checked_at':checked},
        {'name':'Mô hình quan sát thực','state':'configured' if db.database.forecast_registry.count_documents({}) else 'unknown','checked_at':checked}],
        'ingestion':{'total':len(sources),**states,'last_received_at':max((s.last_received_at for s in sources if s.last_received_at),default=None)},
        'sources':[{'id':s.id,'name':s.name,'state':source_state(s),'last_received_at':s.last_received_at,'last_error':s.last_error} for s in sources]}
