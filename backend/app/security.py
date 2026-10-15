import hashlib
import secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db, stamp, now
from .models import User, LoginSession, Audit
from .passwords import hash_password, verify_password

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def create_session(db, user):
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=(now() + timedelta(days=7)).isoformat()))
    db.commit()
    return token

def optional_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get('smarteye_session', '')
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session or session.expires_at <= stamp():
        return None
    user = db.get(User, session.user_id)
    return user if user and user.active else None

def require_user(user=Depends(optional_user)):
    if not user:
        raise HTTPException(401, 'Vui lòng đăng nhập để tiếp tục.')
    return user

def operator(user=Depends(require_user)):
    if user.role not in ('admin', 'analyst'):
        raise HTTPException(403, 'Chức năng này dành cho nhà phân tích và quản trị viên.')
    return user

def admin(user=Depends(require_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Bạn không có quyền quản trị.')
    return user

def audit(db, user_id, action, detail=''):
    db.add(Audit(user_id=user_id, action=action, detail=detail[:300]))

def public_user(user):
    return {key: getattr(user, key) for key in ('id', 'email', 'name', 'role', 'active', 'created_at')}
