import hashlib
import secrets
import uuid
from contextvars import ContextVar
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from .db import get_db, stamp, now
from .models import User, LoginSession, Audit
from .passwords import hash_password, verify_password
from .permissions import PUBLIC, allows, granted
request_id = ContextVar('smarteye_request_id',default='')

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def create_session(db, user):
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, auth_version=user.auth_version, expires_at=(now() + timedelta(days=7)).isoformat()))
    db.commit()
    return token

def optional_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get('smarteye_session', '')
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session or session.expires_at <= stamp():
        return None
    user = db.get(User, session.user_id)
    return user if user and user.active and session.auth_version == user.auth_version else None

def require_user(user=Depends(optional_user)):
    if not user:
        raise HTTPException(401, 'Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.')
    return user

def traffic_viewer(user=Depends(optional_user)):
    if user and user.role not in ('user','analyst'):
        raise HTTPException(403, 'Chức năng này dành cho Người dùng và Quản lý.')
    return user

def traffic_member(user=Depends(require_user)):
    return traffic_viewer(user)

def can(user, key):
    return allows(user.role, user.permissions, key) if user else key in PUBLIC

def check_permission(user, key):
    if not user and key not in PUBLIC:
        require_user(user)
    if not can(user, key):
        raise HTTPException(403, 'Tài khoản chưa được cấp quyền thực hiện thao tác này.')
    return user

def permit(key):
    def check(user=Depends(optional_user)):
        return check_permission(user, key)
    return check

def operator(user=Depends(require_user)):
    if user.role not in ('admin', 'analyst'):
        raise HTTPException(403, 'Chức năng này dành cho nhà phân tích và quản trị viên.')
    return user

def admin(user=Depends(require_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Bạn không có quyền quản trị.')
    return user

def audit(db, user_id, action, detail=''):
    db.add(Audit(user_id=user_id, action=action, detail=detail[:300],event_id=str(uuid.uuid4()),request_id=request_id.get()))

def public_user(user):
    data = {key: getattr(user, key) for key in ('id', 'email', 'name', 'username', 'phone', 'role', 'active',
            'notifications_enabled','managed_segment_ids','protected','profile_version','created_at')}
    return {**data, 'permissions': granted(user.role, user.permissions), 'uses_role_permissions': user.permissions is None}
