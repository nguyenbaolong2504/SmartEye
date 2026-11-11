from datetime import timedelta
from backend.app import sources
from backend.app.business_models import DataSource
from backend.app.db import SessionLocal, now, stamp
from backend.app.models import User
from backend.app.passwords import hash_password


def add_camera(**overrides):
    values={'name':'Camera giao lộ công khai','kind':'camera','format':'image','segment_id':1,
            'direction':'forward','created_by':1,'url':'https://camera.example.org/frame.jpg',
            'authorized':True,'public_preview':True,'tested':True,'active':True,
            'connection_state':'ready','checked_at':stamp(),'signature':'public-camera-test',
            'location_name':'Giao lộ thử nghiệm','position':[21.03,105.84]}
    values.update(overrides)
    with SessionLocal() as db:
        item=DataSource(**values);db.add(item);db.commit()
        return item


def test_camera_directory_never_reveals_private_sources_or_credentials(client):
    published=add_camera(credential_env='TRAFFIC_SOURCE_PRIVATE_CAMERA')
    add_camera(name='Nguồn camera riêng',public_preview=False,signature='private-camera-test')
    result=client.get('/api/traffic/cameras')
    assert result.status_code==200
    assert 'Nguồn camera riêng' not in result.text and 'TRAFFIC_SOURCE_PRIVATE_CAMERA' not in result.text
    item=next(row for row in result.json()['cameras'] if row['id']==f'source-{published.id}')
    assert item['source_url'] is None and item['video_url'] is None
    assert item['position']==[21.03,105.84] and item['position_exact']
    assert item['location_name']=='Giao lộ thử nghiệm' and item['area']=='Hà Nội'
    assert item['captured_at'] is None and item['state']=='ready'


def test_cached_public_image_is_blocked_immediately_when_sharing_is_revoked(client,monkeypatch):
    item=add_camera()
    calls=[]
    async def image(source,head=False):
        calls.append(source.id)
        return b'camera-image','image/jpeg'
    monkeypatch.setattr(sources,'source_request',image)
    path=f'/api/traffic/cameras/sources/{item.id}/frame'
    first=client.get(path)
    assert first.status_code==200 and first.content==b'camera-image'
    assert first.headers['x-camera-received-at']
    assert client.get(path).content==first.content and calls==[item.id]
    with SessionLocal() as db:db.update(DataSource,item.id,{'public_preview':False});db.commit()
    assert client.get(path).status_code==404


def test_image_failure_and_recovery_update_connection_without_fabricating_capture_time(client,monkeypatch):
    item=add_camera()
    async def invalid(source,head=False):return b'not-a-camera','text/html'
    monkeypatch.setattr(sources,'source_request',invalid)
    path=f'/api/traffic/cameras/sources/{item.id}/frame'
    assert client.get(path).status_code==502
    state=next(row for row in client.get('/api/traffic/cameras').json()['cameras'] if row['id']==f'source-{item.id}')
    assert state['state']=='error' and state['captured_at'] is None
    async def recovered(source,head=False):return b'recovered-image','image/png'
    monkeypatch.setattr(sources,'source_request',recovered)
    assert client.get(path).status_code==200
    with SessionLocal() as db:
        current=db.get(DataSource,item.id)
        assert current.connection_state=='ready' and current.last_received_at


def test_private_camera_and_camera_disabled_during_fetch_are_not_published(client,monkeypatch):
    item=add_camera(public_preview=False)
    path=f'/api/traffic/cameras/sources/{item.id}/frame'
    assert client.get(path).status_code==404
    with SessionLocal() as db:db.update(DataSource,item.id,{'public_preview':True});db.commit()
    async def revoke(source,head=False):
        with SessionLocal() as db:db.update(DataSource,source.id,{'active':False});db.commit()
        return b'disabled-during-fetch','image/jpeg'
    monkeypatch.setattr(sources,'source_request',revoke)
    assert client.get(path).status_code==404


def test_camera_permission_is_independent_of_statistics_and_forecasting(client):
    with SessionLocal() as db:
        db.add(User(email='camera-only@test.vn',name='Camera viewer',role='user',
            password=hash_password('camera-test-password'),permissions=['cameras.view']))
        db.commit()
    assert client.post('/api/auth/login',json={'email':'camera-only@test.vn','password':'camera-test-password'}).status_code==200
    assert client.get('/api/traffic/cameras').status_code==200
    assert client.get('/api/traffic/history?segment_id=1&period=day&value=2026-11-01').status_code==403
    assert client.get('/api/forecast/predict?segment_id=1').status_code==403
    with SessionLocal() as db:
        person=db.find_one(User,{'email':'camera-only@test.vn'});person.permissions=[];db.commit()
    assert client.get('/api/traffic/cameras').status_code==403


def test_source_publication_fields_validate_and_preserve_old_sources(admin_client):
    base={'name':'Camera mới để chia sẻ','kind':'camera','format':'image','segment_id':1,
        'url':'https://camera.example.org/frame.jpg','authorized':True,'public_preview':True}
    assert admin_client.post('/api/management/sources',json={**base,'position':[100,105]}).status_code==422
    assert admin_client.post('/api/management/sources',json={**base,'format':'video','credential_env':'TRAFFIC_SOURCE_SECRET'}).status_code==422
    created=admin_client.post('/api/management/sources',json=base)
    assert created.status_code==201 and created.json()['public_preview']
    assert created.json()['position'] is None
    row=created.json()
    edited=admin_client.patch(f'/api/management/sources/{row["id"]}',json={**base,'revision':row['revision'],
        'location_name':'Vị trí vừa bổ sung','position':[21.05,105.79]})
    assert edited.status_code==200 and edited.json()['position']==[21.05,105.79]
    assert not edited.json()['active'] and not edited.json()['tested']


def test_video_directory_uses_shared_stream_and_records_stale_checks(client):
    item=add_camera(format='video',url='https://camera.example.org/stream.mp4',
                    checked_at=(now()-timedelta(hours=1)).isoformat())
    row=next(row for row in client.get('/api/traffic/cameras').json()['cameras'] if row['id']==f'source-{item.id}')
    assert row['state']=='stale' and row['video_url']=='https://camera.example.org/stream.mp4'
    assert row['image_url'] is None
    with SessionLocal() as db:db.update(DataSource,item.id,{'active':False});db.commit()
    row=next(row for row in client.get('/api/traffic/cameras').json()['cameras'] if row['id']==f'source-{item.id}')
    assert row['state']=='inactive' and row['segment_active'] and row['video_url'] is None
