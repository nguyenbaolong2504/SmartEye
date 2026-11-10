"""User reports and the verified incident lifecycle in chapter IV."""
import io
import json
import uuid
from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError
from pymongo.errors import DuplicateKeyError
from .business_common import (manager, road, allowed_query, get_record, changed, event, log_event,
                              serialize, period, position_on_road, NoteAction, Verification)
from .business_models import Incident
from .business_schemas import IncidentInput, IncidentEdit
from .config import DATA
from .db import get_db, now, stamp
from .security import traffic_member

router=APIRouter()
IMAGES=DATA/'incident-images'


def accessible(db,ident,user,manage=False):
    item=get_record(db,Incident,ident)
    if manage or item.user_id!=user.id:
        if user.role!='analyst':raise HTTPException(403,'Bạn không có quyền xem phản ánh này.')
        road(db,item.segment_id,item.direction,user)
    return item


def incident_data(item,user):
    data=serialize(item)
    data['code']=f'PA-{item.id:06d}'
    data['attachments']=[{'id':a['id'],'url':f'/api/incidents/{item.id}/images/{a["id"]}'} for a in item.attachments]
    if item.user_id==user.id and user.role!='analyst':data.pop('assignee_id',None)
    return data


def create(db,body,user,attachment=None):
    segment=road(db,body.segment_id,body.direction)
    position_on_road(body.position,segment)
    # A request retry returns its own earlier submission, never another user's.
    prior=db.find_one(Incident,{'user_id':user.id,'submission_key':body.submission_key})
    if prior:
        if attachment:(IMAGES/attachment['file']).unlink(missing_ok=True)
        return incident_data(prior,user)
    fields=body.model_dump(exclude={'occurred_at'})
    item=Incident(**fields,occurred_at=body.occurred_at.isoformat(),user_id=user.id,
                  history=[event(user,'incident_submitted')],attachments=[attachment] if attachment else [])
    try:db.add(item);db.commit()
    except DuplicateKeyError:
        db.rollback()
        if attachment:(IMAGES/attachment['file']).unlink(missing_ok=True)
        prior=db.find_one(Incident,{'user_id':user.id,'submission_key':body.submission_key})
        if prior:return incident_data(prior,user)
        raise
    except Exception:
        if attachment:(IMAGES/attachment['file']).unlink(missing_ok=True)
        raise
    log_event(db,user.id,'incident_submitted',f'incidents:{item.id}',item.history[0]['event_id'])
    return incident_data(item,user)


@router.post('/api/incidents',status_code=201)
def submit(body:IncidentInput,user=Depends(traffic_member),db=Depends(get_db)):
    return create(db,body,user)


@router.post('/api/incidents/with-image',status_code=201)
async def submit_image(payload:str=Form(...),image:UploadFile=File(...),user=Depends(traffic_member),db=Depends(get_db)):
    try:body=IncidentInput.model_validate_json(payload)
    except ValidationError as exc:raise RequestValidationError(exc.errors()) from None
    raw=await image.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise HTTPException(413,'Ảnh đính kèm không đúng định dạng hoặc quá dung lượng (tối đa 5 MB).')
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in ('JPEG','PNG','WEBP') or picture.width*picture.height>20_000_000:raise ValueError()
            picture.load();clean=ImageOps.exif_transpose(picture).convert('RGB');output=io.BytesIO();clean.save(output,format='JPEG',quality=88)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(422,'Ảnh đính kèm không đúng định dạng hoặc quá dung lượng.') from None
    ident=str(uuid.uuid4());IMAGES.mkdir(parents=True,exist_ok=True)
    target=IMAGES/f'{ident}.jpg';target.write_bytes(output.getvalue())
    try:return create(db,body,user,{'id':ident,'file':target.name})
    except HTTPException:
        target.unlink(missing_ok=True)
        raise


@router.get('/api/incidents')
def own_reports(user=Depends(traffic_member),db=Depends(get_db),status:str|None=None):
    query={'user_id':user.id}
    if status:
        if status not in ('pending','verifying','processing','resolved','rejected'):raise HTTPException(422,'Trạng thái phản ánh không hợp lệ.')
        query['status']=status
    return [incident_data(row,user) for row in db.find(Incident,query,sort=[('id',-1)],limit=200)]


@router.get('/api/incidents/{ident}')
def detail(ident:int,user=Depends(traffic_member),db=Depends(get_db)):
    return incident_data(accessible(db,ident,user),user)


@router.get('/api/incidents/{ident}/images/{image_id}')
def image(ident:int,image_id:uuid.UUID,user=Depends(traffic_member),db=Depends(get_db)):
    item=accessible(db,ident,user)
    attachment=next((a for a in item.attachments if a['id']==str(image_id)),None)
    if not attachment or not (IMAGES/attachment['file']).is_file():raise HTTPException(404,'Ảnh đính kèm không còn tồn tại.')
    return FileResponse(IMAGES/attachment['file'],media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})


@router.get('/api/management/incidents')
def management_reports(q:str=Query(default='',max_length=100),status:str|None=None,start:str|None=None,end:str|None=None,
                       segment_id:int|None=None,user=Depends(manager),db=Depends(get_db)):
    import re
    query=allowed_query(user)
    if segment_id:road(db,segment_id,user=user);query['segment_id']=segment_id
    if status:
        if status not in ('pending','verifying','processing','resolved','rejected'):raise HTTPException(422,'Trạng thái phản ánh không hợp lệ.')
        query['status']=status
    dates=period(start,end)
    if dates:query['created_at']=dates
    if q:query['content']={'$regex':re.escape(q),'$options':'i'}
    return [incident_data(row,user) for row in db.find(Incident,query,sort=[('id',-1)],limit=200)]


def editable(db,ident,user,revision,statuses):
    item=accessible(db,ident,user,manage=True)
    if item.revision!=revision or item.status not in statuses:
        raise HTTPException(409,'Phản ánh không còn ở trạng thái cho phép. Vui lòng tải lại.')
    if item.assignee_id!=user.id:raise HTTPException(403,'Phản ánh đang do Quản lý khác phụ trách.')
    return item


@router.post('/api/management/incidents/{ident}/accept')
def accept(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=accessible(db,ident,user,manage=True)
    if item.status!='pending':raise HTTPException(409,'Phản ánh không còn ở trạng thái chờ tiếp nhận.')
    result=changed(db,Incident,item,body.revision,{'status':'verifying','assignee_id':user.id},event(user,'incident_accepted',body.note))
    return incident_data(result,user)


@router.post('/api/management/incidents/{ident}/verify')
def verify(ident:int,body:Verification,user=Depends(manager),db=Depends(get_db)):
    item=editable(db,ident,user,body.revision,('verifying',))
    result=changed(db,Incident,item,body.revision,{'verification':body.conclusion,'status':'processing' if body.conclusion=='valid' else 'verifying'},
                   event(user,'incident_verified',body.note,conclusion=body.conclusion))
    return incident_data(result,user)


@router.patch('/api/management/incidents/{ident}')
def update(ident:int,body:IncidentEdit,user=Depends(manager),db=Depends(get_db)):
    item=editable(db,ident,user,body.revision,('verifying','processing'))
    position_on_road(body.position,road(db,item.segment_id,item.direction,user))
    updates=body.model_dump(exclude={'revision','occurred_at'});updates['occurred_at']=body.occurred_at.isoformat()
    return incident_data(changed(db,Incident,item,body.revision,updates,event(user,'incident_updated',snapshot=updates)),user)


@router.post('/api/management/incidents/{ident}/progress')
def progress(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=editable(db,ident,user,body.revision,('processing',))
    return incident_data(changed(db,Incident,item,body.revision,{},event(user,'incident_progress',body.note)),user)


@router.post('/api/management/incidents/{ident}/reject')
def reject(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=editable(db,ident,user,body.revision,('verifying',))
    if item.verification!='invalid':raise HTTPException(409,'Cần lưu kết luận không hợp lệ trước khi từ chối phản ánh.')
    return incident_data(changed(db,Incident,item,body.revision,{'status':'rejected'},event(user,'incident_rejected',body.note)),user)


@router.post('/api/management/incidents/{ident}/resolve')
def resolve(ident:int,body:NoteAction,user=Depends(manager),db=Depends(get_db)):
    item=editable(db,ident,user,body.revision,('processing',))
    # Closing an incident deliberately leaves any related published warning alone.
    return incident_data(changed(db,Incident,item,body.revision,{'status':'resolved'},event(user,'incident_resolved',body.note)),user)
