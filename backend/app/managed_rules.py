"""Rules propose warnings; human verification and publication are mandatory."""
import re
import operator
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import DuplicateKeyError
from .db import get_db, stamp, now
from .history import LOCAL
from .business_common import (manager, road, allowed_query, get_record, changed, event, serialize,
                              fingerprint, Revision, NoteAction, utc)
from .business_models import ManagedRule, DataSource, RoadReading, Warning
from .business_schemas import RuleInput, RuleEdit, Toggle

router=APIRouter()
OPS={'gt':operator.gt,'gte':operator.ge,'lt':operator.lt,'lte':operator.le}


def signature(body):
    return fingerprint(body.model_dump(exclude={'name','severity','revision'}))


def record(db,ident,user):
    item=get_record(db,ManagedRule,ident)
    if item.deleted:raise HTTPException(404,'Quy tắc đã được xóa.')
    road(db,item.segment_id,item.direction,user)
    return item


@router.get('/api/management/rules')
def rules(q:str=Query(default='',max_length=100),active:bool|None=None,metric:str|None=None,user=Depends(manager),db=Depends(get_db)):
    query={**allowed_query(user),'deleted':False}
    if q:query['name']={'$regex':re.escape(q),'$options':'i'}
    if active is not None:query['active']=active
    if metric:
        if metric not in ('score','speed_kmh','flow_per_minute'):raise HTTPException(422,'Chỉ số không hợp lệ.')
        query['metric']=metric
    return [serialize(row) for row in db.find(ManagedRule,query,sort=[('id',-1)],limit=200)]


@router.post('/api/management/rules',status_code=201)
def create_rule(body:RuleInput,user=Depends(manager),db=Depends(get_db)):
    road(db,body.segment_id,body.direction,user)
    fields=body.model_dump()
    value=ManagedRule(**fields,signature=signature(body),name_key=body.name.casefold(),created_by=user.id,
                      versions=[{'version':1,**fields}],history=[event(user,'rule_created')])
    db.add(value);db.commit();return serialize(value)


@router.patch('/api/management/rules/{ident}')
def edit_rule(ident:int,body:RuleEdit,user=Depends(manager),db=Depends(get_db)):
    item=record(db,ident,user);road(db,body.segment_id,body.direction,user)
    fields=body.model_dump(exclude={'revision'});version=item.content_version+1
    return serialize(changed(db,ManagedRule,item,body.revision,{**fields,'active':False,'tested':False,
        'signature':signature(body),'name_key':body.name.casefold(),'content_version':version,
        'versions':[*item.versions,{'version':version,**fields}]},event(user,'rule_updated',version=version)))


def evaluation(db,rule,at=None):
    at=at or now()
    sources=db.find(DataSource,{'active':True,'tested':True,'segment_id':rule.segment_id,'direction':rule.direction})
    eligible=[]
    for source in sources:
        field='count' if rule.metric=='flow_per_minute' else rule.metric
        if field not in source.mapping:continue
        if rule.metric=='speed_kmh' and not source.speed_verified:continue
        if rule.metric=='flow_per_minute' and (source.count_method!='crossings' or 'interval_seconds' not in source.mapping):continue
        if source.last_received_at and now()-utc(source.last_received_at)<=timedelta(minutes=source.stale_minutes):eligible.append(source)
    if not eligible:return {'ready':False,'matches':False,'samples':0,'message':'Chưa có nguồn chỉ số còn mới, được kiểm tra và đang bật.'}
    start=at-timedelta(minutes=rule.window_minutes)
    rows=db.find(RoadReading,{'$or':[{'source_id':s.id,'source_version':s.version} for s in eligible],
                             'observed_at':{'$gte':start.isoformat(),'$lte':at.isoformat()},
                             f'metrics.{rule.metric}':{'$exists':True}},sort=[('observed_at',1)],limit=5000)
    # Require complete coverage, without bridging a missing interval with zero.
    slack=max(s.interval_seconds for s in eligible)*1.5
    times=[utc(r.observed_at) for r in rows]
    complete=bool(times and (times[0]-start).total_seconds()<=slack and (at-times[-1]).total_seconds()<=slack
                  and all((b-a).total_seconds()<=slack for a,b in zip(times,times[1:])))
    hour=at.astimezone(LOCAL).hour
    value=sum(float(r.metrics[rule.metric]) for r in rows)/len(rows) if rows else None
    return {'ready':complete,'matches':bool(complete and rule.start_hour<=hour<rule.end_hour and OPS[rule.operator](value,rule.threshold)),
            'samples':len(rows),'value':value,'unit':rule.unit,'evaluated_at':at.isoformat(),
            'message':'Đủ dữ liệu để đánh giá.' if complete else 'Chưa đủ dữ liệu liên tục trong khoảng đánh giá.'}


@router.post('/api/management/rules/{ident}/test')
def test_rule(ident:int,body:Revision,user=Depends(manager),db=Depends(get_db)):
    item=record(db,ident,user);result=evaluation(db,item)
    if not result['ready']:raise HTTPException(409,result['message'])
    value=changed(db,ManagedRule,item,body.revision,{'tested':True},event(user,'rule_tested',samples=result['samples']))
    return {**serialize(value),'evaluation':result}


@router.post('/api/management/rules/{ident}/toggle')
def toggle_rule(ident:int,body:Toggle,user=Depends(manager),db=Depends(get_db)):
    item=record(db,ident,user)
    if body.active and (not item.tested or not evaluation(db,item)['ready']):
        raise HTTPException(409,'Quy tắc chưa đủ điều kiện kích hoạt. Kiểm tra nguồn và số liệu trước.')
    return serialize(changed(db,ManagedRule,item,body.revision,{'active':body.active},event(user,'rule_enabled' if body.active else 'rule_disabled')))


@router.post('/api/management/rules/{ident}/delete')
def delete_rule(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=record(db,ident,user)
    return serialize(changed(db,ManagedRule,item,body.revision,{'active':False,'deleted':True},event(user,'rule_deleted',body.note)))


def evaluate_rules(db,reading):
    source=db.get(DataSource,reading.source_id)
    if not source or now()-utc(reading.observed_at)>timedelta(minutes=source.stale_minutes):return
    for rule in db.find(ManagedRule,{'active':True,'tested':True,'deleted':False,'segment_id':reading.segment_id,'direction':reading.direction}):
        if reading.created_at<rule.updated_at:continue
        result=evaluation(db,rule,utc(reading.observed_at))
        if not result['matches']:continue
        if db.find_one(Warning,{'rule_id':rule.id,'rule_version':rule.content_version,'status':{'$nin':['ended','cancelled']}}):continue
        segment=road(db,rule.segment_id,rule.direction)
        key=f'rule:{rule.id}:{rule.content_version}:{int(utc(reading.observed_at).timestamp())//(rule.window_minutes*60)}'
        content=f'{segment.name}: chỉ số {rule.metric} đạt {result["value"]:.2f} {rule.unit} theo quy tắc {rule.name}. Cần xác minh tình hình thực tế.'
        fields={'segment_id':rule.segment_id,'direction':rule.direction,'kind':'congestion','position':segment.geometry[len(segment.geometry)//2],
                'severity':rule.severity,'content':content,'start_at':stamp(),'end_at':None}
        value=Warning(**fields,created_by=rule.created_by,origin='rule',origin_key=key,rule_id=rule.id,rule_version=rule.content_version,
                      versions=[{'version':1,**fields}],history=[event(None,'warning_proposed',rule_id=rule.id,rule_version=rule.content_version)])
        try:db.add(value);db.commit()
        except DuplicateKeyError:db.rollback()
