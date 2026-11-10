"""Verified, versioned public warnings and recoverable in-app deliveries."""
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from .db import get_db, now, stamp
from .business_models import Warning, Incident
from .business_schemas import WarningInput, WarningEdit
from .models import User
from .business_common import (manager, road, allowed_query, get_record, changed, event, log_event, serialize,
                              period, position_on_road, NoteAction, Verification, Revision)
from .security import traffic_viewer

router=APIRouter()
STATES=('pending_verification','pending_publication','published','ended','cancelled')
FIELDS=('segment_id','direction','kind','position','severity','content','start_at','end_at')
CONTACT=re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+|(?<!\w)(?:\+84|0)(?:[ .-]?\d){9,10}(?!\d)')


def snapshot(db,item):
    value={key:getattr(item,key) for key in FIELDS}
    if item.incident_id:
        incident=db.get(Incident,item.incident_id)
        reporter=db.get(User,incident.user_id) if incident else None
        if reporter and reporter.name.strip():
            value['content']=re.sub(rf'(?<!\w){re.escape(reporter.name.strip())}(?!\w)','[đã ẩn]',value['content'],flags=re.IGNORECASE)
    value['content']=CONTACT.sub('[đã ẩn]',value['content'])
    return value


def public_data(item):
    value=item.public_snapshot
    if value is None or item.status in ('ended','cancelled') or value.get('end_at') and value['end_at']<=stamp():
        return None
    # No incident identifiers, reporters, verification evidence or draft fields.
    return {'id':item.id,**{k:value[k] for k in (*FIELDS,'version','published_at')},
            'upcoming':value['start_at']>stamp()}


@router.get('/api/warnings',dependencies=[Depends(traffic_viewer)])
def public_warnings(segment_id:int|None=None,direction:str|None=None,db=Depends(get_db)):
    if direction and direction not in ('forward','reverse'):raise HTTPException(422,'Chiều đường không hợp lệ.')
    query={'public_snapshot':{'$ne':None},'status':{'$nin':['ended','cancelled']}}
    if segment_id:query['segment_id']=segment_id
    if direction:query['direction']=direction
    return [value for item in db.find(Warning,query,sort=[('id',-1)],limit=200) if (value:=public_data(item))]


@router.get('/api/warnings/{ident}',dependencies=[Depends(traffic_viewer)])
def public_detail(ident:int,db=Depends(get_db)):
    item=get_record(db,Warning,ident);value=public_data(item)
    if value is None:raise HTTPException(404,'Cảnh báo không tồn tại, chưa được công bố hoặc đã hết hiệu lực.')
    return value


def managed(db,ident,user):
    item=get_record(db,Warning,ident);road(db,item.segment_id,item.direction,user)
    return item


@router.get('/api/management/warnings')
def warning_list(q:str=Query(default='',max_length=100),status:str|None=None,start:str|None=None,end:str|None=None,
                 segment_id:int|None=None,user=Depends(manager),db=Depends(get_db)):
    query=allowed_query(user)
    if segment_id:road(db,segment_id,user=user);query['segment_id']=segment_id
    if status:
        if status not in STATES:raise HTTPException(422,'Trạng thái cảnh báo không hợp lệ.')
        query['status']=status
    if q:query['content']={'$regex':re.escape(q),'$options':'i'}
    dates=period(start,end)
    if dates:query['created_at']=dates
    return [serialize(row) for row in db.find(Warning,query,sort=[('id',-1)],limit=200)]


@router.get('/api/management/warnings/{ident}')
def warning_detail(ident:int,user=Depends(manager),db=Depends(get_db)):
    return serialize(managed(db,ident,user))


def validate_content(db,body,user):
    segment=road(db,body.segment_id,body.direction,user);position_on_road(body.position,segment)
    if body.end_at and body.end_at<=now():raise HTTPException(422,'Thời gian áp dụng cảnh báo đã hết.')
    if body.incident_id:
        incident=get_record(db,Incident,body.incident_id)
        if incident.segment_id!=body.segment_id or incident.direction!=body.direction or incident.verification!='valid':
            raise HTTPException(409,'Phản ánh liên quan phải cùng tuyến, cùng chiều và đã xác minh hợp lệ.')
    return {**body.model_dump(include=set(FIELDS)), 'start_at':body.start_at.isoformat(),
            'end_at':body.end_at.isoformat() if body.end_at else None}


@router.post('/api/management/warnings',status_code=201)
def create_warning(body:WarningInput,user=Depends(manager),db=Depends(get_db)):
    fields=validate_content(db,body,user)
    similar=db.find_one(Warning,{'segment_id':body.segment_id,'direction':body.direction,'kind':body.kind,
                                'status':{'$nin':['ended','cancelled']}})
    if similar and len(body.duplicate_reason.strip())<5:
        raise HTTPException(409,{'message':'Đang có cảnh báo tương tự. Xem cảnh báo cũ hoặc ghi lý do tiếp tục tạo.', 'similar_id':similar.id})
    row=Warning(**fields,created_by=user.id,incident_id=body.incident_id,
                history=[event(user,'warning_created',body.duplicate_reason)],versions=[{'version':1,**fields}])
    db.add(row);db.commit()
    log_event(db,user.id,'warning_created',f'traffic_warnings:{row.id}',row.history[0]['event_id'])
    return serialize(row)


@router.patch('/api/management/warnings/{ident}')
def edit_warning(ident:int,body:WarningEdit,user=Depends(manager),db=Depends(get_db)):
    item=managed(db,ident,user)
    if item.status in ('ended','cancelled'):raise HTTPException(409,'Cảnh báo đã kết thúc hoặc đã hủy, không được sửa.')
    fields=validate_content(db,body,user)
    # Keep scope fixed for public-version continuity and private incident access.
    if body.segment_id!=item.segment_id or body.direction!=item.direction:
        raise HTTPException(422,'Cần tạo cảnh báo mới khi thay đổi tuyến hoặc chiều đường.')
    version=item.content_version+1
    updates={**fields,'incident_id':body.incident_id,'status':'pending_verification','verification':None,
             'content_version':version,'versions':[*item.versions,{'version':version,**fields}]}
    return serialize(changed(db,Warning,item,body.revision,updates,event(user,'warning_revised',version=version)))


@router.post('/api/management/warnings/{ident}/verify')
def verify_warning(ident:int,body:Verification,user=Depends(manager),db=Depends(get_db)):
    item=managed(db,ident,user)
    if item.status!='pending_verification':raise HTTPException(409,'Cảnh báo không còn ở trạng thái chờ xác minh.')
    updates={'verification':body.conclusion,'status':'pending_publication' if body.conclusion=='valid' else 'pending_verification'}
    return serialize(changed(db,Warning,item,body.revision,updates,
                             event(user,'warning_verified',body.note,conclusion=body.conclusion,version=item.content_version)))


def deliver_publications(database,limit=20):
    """Idempotent inbox writes; failed deliveries remain pending for retry."""
    for warning in database.traffic_warnings.find({'notification_queue.state':'pending'}).limit(limit):
        for job in warning.get('notification_queue',[]):
            if job['state']!='pending':continue
            if warning['status'] in ('ended','cancelled'):
                database.traffic_warnings.update_one({'_id':warning['_id'],'notification_queue.version':job['version']},
                    {'$set':{'notification_queue.$.state':'withdrawn'}})
                continue
            try:
                for user in database.users.find({'active':True,'notifications_enabled':True,'role':{'$in':['user','analyst']}}):
                    key=f'warning:{warning["_id"]}:{job["version"]}:{user["_id"]}'
                    counter=database.counters.find_one_and_update({'_id':'notifications'},{'$inc':{'seq':1}},upsert=True,return_document=ReturnDocument.AFTER)
                    database.notifications.update_one({'delivery_key':key},{'$setOnInsert':{
                        '_id':counter['seq'],'delivery_key':key,'user_id':user['_id'],'read':False,
                        'warning_id':warning['_id'],'warning_version':job['version'],'created_at':stamp(),
                        'message':f'Cảnh báo giao thông mới: {job["content"][:160]}'}},upsert=True)
                database.traffic_warnings.update_one({'_id':warning['_id'],'notification_queue.version':job['version']},
                    {'$set':{'notification_queue.$.state':'sent','notification_state':'sent'}})
            except Exception:
                # Publishing has already committed; do not revert or expose errors.
                try:database.traffic_warnings.update_one({'_id':warning['_id']},{'$set':{'notification_state':'retry_pending'}})
                except Exception:pass


@router.post('/api/management/warnings/{ident}/publish')
def publish_warning(ident:int,body:Revision,user=Depends(manager),db=Depends(get_db)):
    item=managed(db,ident,user)
    if item.status!='pending_publication' or item.verification!='valid':
        raise HTTPException(409,'Cảnh báo chưa được xác minh hợp lệ hoặc đã được phát hành.')
    road(db,item.segment_id,item.direction,user)
    if item.end_at and item.end_at<=stamp():raise HTTPException(409,'Cảnh báo đã hết hiệu lực.')
    public={**snapshot(db,item),'version':item.content_version,'published_at':stamp()}
    queue=[*item.notification_queue,{'version':item.content_version,'content':public['content'],'state':'pending'}]
    changed_item=changed(db,Warning,item,body.revision,{'status':'published','public_snapshot':public,
        'notification_queue':queue,'notification_state':'pending'},event(user,'warning_published',version=item.content_version))
    try:
        deliver_publications(db.database)
        return serialize(get_record(db,Warning,changed_item.id))
    except PyMongoError:
        return serialize(changed_item)


@router.post('/api/management/warnings/{ident}/end')
def end_warning(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=managed(db,ident,user)
    if item.status in ('ended','cancelled') or item.public_snapshot is None:
        raise HTTPException(409,'Cảnh báo chưa được phát hành hoặc đã kết thúc.')
    return serialize(changed(db,Warning,item,body.revision,{'status':'ended'},event(user,'warning_ended',body.note)))


@router.post('/api/management/warnings/{ident}/cancel')
def cancel_warning(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=managed(db,ident,user)
    if item.status in ('ended','cancelled'):raise HTTPException(409,'Cảnh báo đã kết thúc hoặc đã hủy.')
    return serialize(changed(db,Warning,item,body.revision,{'status':'cancelled'},event(user,'warning_cancelled',body.note)))


@router.post('/api/management/warnings/retry-deliveries')
def retry_deliveries(user=Depends(manager),db=Depends(get_db)):
    deliver_publications(db.database)
    return {'message':'Đã thử gửi lại những thông báo đang chờ.'}
