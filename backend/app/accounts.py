"""Administrative account lifecycle with serialized last-admin protection."""
import re
import uuid
from contextlib import contextmanager
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from .business_common import Input, NoteAction, log_event
from .db import get_db, now, stamp
from .models import User
from .security import admin, public_user
from .passwords import hash_password
from .schemas import Register
from .permissions import choices

router=APIRouter()


class AccountCreate(Register):
    role: str = Field(default='user',pattern=r'^(user|analyst|admin)$')
    managed_segment_ids: list[int] | None = None


class AccountEdit(Input):
    revision: int = Field(ge=1)
    name: str = Field(min_length=2,max_length=100)
    email: str
    phone: str | None = None
    active: bool
    _email=field_validator('email')(Register.email_valid.__func__)
    _phone=field_validator('phone')(Register.phone_valid.__func__)
    _name=field_validator('name')(Register.name_valid.__func__)


class RoleEdit(Input):
    revision: int = Field(ge=1)
    role: str = Field(pattern=r'^(user|analyst|admin)$')
    managed_segment_ids: list[int] | None = None
    confirmed: bool
    permissions: list[str] | None = Field(default=None,max_length=64)


@router.get('/api/admin/permission-options')
def permission_options(user=Depends(admin)):
    return {role: choices(role) for role in ('user', 'analyst')}


@contextmanager
def account_lock(db,actor):
    token=str(uuid.uuid4());collection=db.database.business_locks
    try:
        locked=collection.find_one_and_update({'_id':'admin_accounts','$or':[{'token':None},{'expires_at':{'$lte':stamp()}}]},
            {'$set':{'token':token,'expires_at':(now()+timedelta(seconds=20)).isoformat()}},upsert=True,return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:raise HTTPException(409,'Đang có thay đổi tài khoản khác. Vui lòng thử lại.') from None
    if not locked:raise HTTPException(409,'Đang có thay đổi tài khoản khác. Vui lòng thử lại.')
    try:
        current=db.get(User,actor.id)
        if not current or not current.active or current.role!='admin':raise HTTPException(403,'Quyền quản trị đã thay đổi. Vui lòng đăng nhập lại.')
        yield
    finally:collection.update_one({'_id':'admin_accounts','token':token},{'$set':{'token':None,'expires_at':stamp()}})


def apply_account(db,actor,ident,updates,revision=None,reason=''):
    with account_lock(db,actor):
        current=db.get(User,ident)
        if not current:raise HTTPException(404,'Tài khoản không còn tồn tại.')
        if revision is not None and revision!=current.profile_version:raise HTTPException(409,'Tài khoản đã thay đổi. Vui lòng tải lại.')
        losing_admin=current.active and current.role=='admin' and (not updates.get('active',current.active) or updates.get('role',current.role)!='admin')
        if (not updates.get('active',current.active) and current.protected) or losing_admin and db.count(User,{'active':True,'role':'admin'})<=1:
            raise HTTPException(422,'Không được vô hiệu hóa tài khoản được bảo vệ hoặc làm mất quản trị viên cuối cùng.')
        query={'_id':ident,'$or':[{'profile_version':current.profile_version},{'profile_version':{'$exists':False}}]}
        version=current.profile_version+1
        history={'at':stamp(),'actor_id':actor.id,'action':'account_updated','fields':sorted(updates),'reason':reason}
        result=db.database.users.find_one_and_update(query,{'$set':{**updates,'profile_version':version},
            '$inc':{'auth_version':1},'$push':{'account_history':history}},return_document=ReturnDocument.AFTER)
        if result is None:raise HTTPException(409,'Tài khoản đã thay đổi. Vui lòng tải lại.')
        # auth_version invalidates every old session immediately, even if the
        # optional token cleanup fails; history is atomic in the user record.
        try:db.database.sessions.delete_many({'user_id':ident})
        except Exception:pass
        log_event(db,actor.id,'account_updated',str(ident))
        return public_user(User.from_mongo(result))


def validate_scope(db,ids):
    from .models import Segment
    if ids is not None and (len(ids)>200 or any(db.get(Segment,ident) is None for ident in ids)):
        raise HTTPException(422,'Phạm vi tuyến đường không hợp lệ.')


@router.get('/api/admin/accounts')
def accounts(q:str=Query(default='',max_length=100),role:str|None=None,active:bool|None=None,user=Depends(admin),db=Depends(get_db)):
    filters={}
    if q:filters['$or']=[{key:{'$regex':re.escape(q),'$options':'i'}} for key in ('name','email','username')]
    if role:
        if role not in ('user','analyst','admin'):raise HTTPException(422,'Vai trò không hợp lệ.')
        filters['role']=role
    if active is not None:filters['active']=active
    return [public_user(u) for u in db.find(User,filters,sort=[('id',1)],limit=200)]


@router.post('/api/admin/accounts',status_code=201)
def create_account(body:AccountCreate,user=Depends(admin),db=Depends(get_db)):
    validate_scope(db,body.managed_segment_ids)
    fields=body.model_dump(exclude={'password','password_confirmation'})
    row=User(**fields,password=hash_password(body.password))
    with account_lock(db,user):db.add(row);db.commit()
    log_event(db,user.id,'account_created',str(row.id))
    return public_user(row)


@router.patch('/api/admin/accounts/{ident}')
def edit_account(ident:int,body:AccountEdit,user=Depends(admin),db=Depends(get_db)):
    return apply_account(db,user,ident,body.model_dump(exclude={'revision'}),body.revision)


@router.post('/api/admin/accounts/{ident}/role')
def edit_role(ident:int,body:RoleEdit,user=Depends(admin),db=Depends(get_db)):
    if not body.confirmed:raise HTTPException(422,'Cần xác nhận thay đổi quyền.')
    validate_scope(db,body.managed_segment_ids)
    if body.permissions is not None and (body.role=='admin' or set(body.permissions)-choices(body.role).keys()):
        raise HTTPException(422,'Có quyền không thuộc vai trò đã chọn.')
    updates={'role':body.role,'managed_segment_ids':body.managed_segment_ids}
    target=db.get(User,ident)
    if 'permissions' in body.model_fields_set or target and target.role!=body.role:
        updates['permissions']=None if body.permissions is None else sorted(set(body.permissions))
    return apply_account(db,user,ident,updates,body.revision)


@router.post('/api/admin/accounts/{ident}/disable')
def disable_account(ident:int,body:NoteAction,user=Depends(admin),db=Depends(get_db)):
    return apply_account(db,user,ident,{'active':False},body.revision,body.note)
