from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db import SessionLocal
from backend.app.models import VideoJob

def register(client,email='user@test.vn'):
    return client.post('/api/auth/register',json={'name':'Người kiểm thử','email':email,'password':'valid-test-password'})

def test_register_role_cookie_and_private_endpoints(client):
    assert client.get('/api/videos').status_code==401
    response=register(client)
    assert response.status_code==201 and response.json()['role']=='user'
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert client.get('/api/admin/users').status_code==403
    assert client.get('/api/reports').status_code==403
    assert register(client).status_code==409

def test_logout_revokes_session(client):
    register(client); token=client.cookies.get('smarteye_session')
    assert client.post('/api/auth/logout').status_code==200
    client.cookies.set('smarteye_session',token)
    assert client.get('/api/auth/me').json() is None

def test_password_change_revokes_old_session(client):
    register(client); old=client.cookies.get('smarteye_session')
    assert client.post('/api/auth/password',json={'current_password':'valid-test-password','new_password':'new-valid-test-password'}).status_code==200
    client.cookies.clear();client.cookies.set('smarteye_session',old)
    assert client.get('/api/videos').status_code==401

def test_cross_origin_post_is_rejected(client):
    assert client.post('/api/auth/login',json={'email':'admin@test.vn','password':'test-password-only'},headers={'Origin':'https://attacker.example'}).status_code==403

def test_video_owner_isolation(client):
    first=register(client).json()
    with SessionLocal() as db:
        db.add(VideoJob(id='private',user_id=first['id'],camera_id=1,filename='private.mp4',camera_config={}));db.commit()
    client.post('/api/auth/logout');register(client,'other@test.vn')
    assert client.get('/api/videos/private').status_code==403
    assert client.get('/api/videos/private/frames/0').status_code==403
    assert client.get('/api/videos').json()==[]

def test_favorite_input_only_and_ownership(client,route_request):
    register(client)
    response=client.post('/api/favorites',json={'name':'Hành trình sáng','request':route_request})
    assert response.status_code==201
    favorite=response.json(); assert 'geometry' not in favorite['request']
    client.post('/api/auth/logout');register(client,'second@test.vn')
    assert client.delete(f'/api/favorites/{favorite["id"]}').status_code==403

def test_admin_cannot_lock_self(admin_client):
    assert admin_client.patch('/api/admin/users/1',json={'active':False,'role':'admin'}).status_code==422

def test_role_change_and_lock_revoke_sessions(client):
    user=register(client).json(); token=client.cookies.get('smarteye_session');client.post('/api/auth/logout')
    client.post('/api/auth/login',json={'email':'admin@test.vn','password':'test-password-only'})
    assert client.patch(f'/api/admin/users/{user["id"]}',json={'role':'analyst','active':False}).status_code==200
    client.cookies.clear();client.cookies.set('smarteye_session',token)
    assert client.get('/api/videos').status_code==401

def test_upload_requires_valid_camera_and_video(client,monkeypatch):
    register(client)
    assert client.post('/api/videos',data={'camera_id':'999'},files={'file':('x.mp4',b'foo','video/mp4')}).status_code==404

def test_rate_limit(client):
    for _ in range(20): client.post('/api/auth/login',json={'email':'none@test.vn','password':'wrong'})
    assert client.post('/api/auth/login',json={'email':'none@test.vn','password':'wrong'}).status_code==429
