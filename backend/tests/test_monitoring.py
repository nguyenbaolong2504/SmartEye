from datetime import datetime, timedelta, timezone
import uuid
import pytest
from backend.app.db import SessionLocal, get_database, now
from backend.app.models import AlertRule, Camera, Observation, Segment, TrafficSample, User, VideoJob
from backend.app import history, monitoring, main


def sample(segment_id,at,score=.9,camera_id=1,**extra):
    row=TrafficSample(sample_key=uuid.uuid4().hex,segment_id=segment_id,camera_id=camera_id,
        observed_at=at.astimezone(timezone.utc).isoformat(),score=score,
        density='HIGH' if score>=.6 else 'LOW' if score<.25 else 'NORMAL',count=9,source='yolo',**extra)
    with SessionLocal() as db: db.add(row);db.commit()
    return row


def completed_job(at,media=False,frames=False,owner=1):
    job_id=str(uuid.uuid4())
    items=[{'second':s,'count':10,'score':.9,'density':'HIGH','occupancy':.3,
            'boxes':[{'label':'car'},{'label':'motorcycle'}]} for s in (0,60,120,180)]
    with SessionLocal() as db:
        job=VideoJob(id=job_id,user_id=owner,camera_id=1,filename='road.mp4',retain_video=media,
            status='completed',progress=100,observed_at=at.isoformat(),camera_config={'segment_id':1},
            result={'density':'HIGH','score':.9,'average_count':10,'model':'test-detector','samples':items})
        db.add(job);db.commit()
    if frames: (monitoring.UPLOADS/f'{job_id}-0.jpg').write_bytes(b'test-jpeg-bytes')
    if media: (monitoring.UPLOADS/f'{job_id}.retained').write_bytes(b'0123456789abcdefghij')
    return job


@pytest.fixture
def media_paths(monkeypatch,tmp_path):
    uploads=tmp_path/'uploads';uploads.mkdir()
    monkeypatch.setattr(monitoring,'UPLOADS',uploads)
    monkeypatch.setattr(main,'UPLOADS',uploads)
    monkeypatch.setattr(monitoring,'PREVIEWS',tmp_path/'previews')


def report(client,period='day',value='2026-01-15',segment_id=1):
    response=client.get('/api/traffic/history',params={'segment_id':segment_id,'period':period,'value':value})
    assert response.status_code==200,response.text
    return response.json()


def test_empty_history_keeps_unknown_and_24_hours(client):
    data=report(client)
    assert data['summary']['raw_samples']==0
    assert len(data['hourly'])==24 and len(data['heatmap'])==24
    assert all(h['average_score'] is None and h['high_share'] is None for h in data['hourly'])
    assert not data['peak_hours']


def test_vietnam_day_and_month_boundaries(client):
    sample(1,datetime(2026,1,14,16,59,tzinfo=timezone.utc)) # 23:59 previous day
    sample(1,datetime(2026,1,14,17,0,tzinfo=timezone.utc))  # 00:00 selected day
    sample(1,datetime(2026,1,15,16,59,tzinfo=timezone.utc)) # 23:59 selected day
    sample(1,datetime(2026,1,15,17,0,tzinfo=timezone.utc))  # next day
    data=report(client)
    assert data['summary']['raw_samples']==2
    assert data['hourly'][0]['slot_count']==data['hourly'][23]['slot_count']==1
    assert report(client,'month','2024-02')['daily'][-1]['date']=='2024-02-29'


@pytest.mark.parametrize('period,value',[('year','2026'),('day','bad'),('month','2026-13'),('month','2026-01-01'),('day','2999-01-01')])
def test_invalid_history_ranges(client,period,value):
    assert client.get('/api/traffic/history',params={'segment_id':1,'period':period,'value':value}).status_code==422


def test_slot_normalization_does_not_weight_frame_rate_or_camera_count(client):
    start=datetime(2026,1,15,7,tzinfo=history.LOCAL)
    for second in range(90): sample(1,start+timedelta(seconds=second),.9)
    for minute in (5,10,15): sample(1,start+timedelta(minutes=minute),.1)
    sample(1,start,.8,camera_id=2)
    data=report(client)
    assert data['summary']['raw_samples']==94
    assert data['summary']['slot_count']==4
    assert data['hourly'][7]['high_share']==.25
    assert not data['hourly'][7]['sufficient']


def test_recurring_hour_needs_multiple_observed_days(client):
    for day in (5,12,19):
        for minute in (0,10,20,30): sample(1,datetime(2026,1,day,7,minute,tzinfo=history.LOCAL))
    data=report(client,'month','2026-01')
    assert len(data['heatmap'])==31*24
    assert data['peak_hours'][0]['hour']==7 and data['peak_hours'][0]['observed_days']==3
    assert data['peak_hours'][0]['high_share']==1
    assert data['summary']['coverage_percent']<1
    assert not data['hourly'][8]['sufficient']


def test_archive_old_video_saves_series_without_current_status(admin_client,media_paths):
    job=completed_job(now()-timedelta(days=10))
    assert admin_client.post(f'/api/videos/{job.id}/publish').status_code==422
    response=admin_client.post(f'/api/videos/{job.id}/archive',json={'share_preview':False})
    assert response.status_code==200
    assert get_database().traffic_samples.count_documents({'job_id':job.id})==4
    assert admin_client.get('/api/segments').json()[0]['observation'] is None
    board=admin_client.get('/api/monitor/cameras').json()['cameras'][0]
    assert board['state']=='stale' and board['density'] is None and board['last_density']=='HIGH'
    assert board['image_url'] is None
    assert admin_client.post(f'/api/videos/{job.id}/archive',json={}).status_code==409
    assert get_database().traffic_samples.count_documents({'job_id':job.id})==4


def test_sharing_opt_in_range_requests_hide_and_delete(admin_client,media_paths):
    job=completed_job(now()-timedelta(minutes=10),media=True,frames=True)
    assert admin_client.post(f'/api/videos/{job.id}/publish',json={}).status_code==200
    assert admin_client.get('/api/monitor/cameras/1/frame').status_code==404
    assert admin_client.post(f'/api/videos/{job.id}/share-preview',json={'share_preview':True}).status_code==200
    assert admin_client.get(f'/api/videos/{job.id}').json()['preview_shared'] is True
    assert admin_client.get('/api/monitor/cameras/1/frame').content==b'test-jpeg-bytes'
    response=admin_client.get('/api/monitor/cameras/1/video',headers={'Range':'bytes=0-4'})
    assert response.status_code==206 and response.content==b'01234'
    assert admin_client.post(f'/api/videos/{job.id}/share-preview',json={'share_preview':False}).status_code==200
    assert admin_client.get(f'/api/videos/{job.id}').json()['preview_shared'] is False
    assert admin_client.get('/api/monitor/cameras/1/video').status_code==404
    assert admin_client.delete(f'/api/videos/{job.id}').status_code==200
    assert not (monitoring.UPLOADS/f'{job.id}.retained').exists()
    assert get_database().traffic_samples.count_documents({'job_id':job.id})==4
    assert get_database().observations.count_documents({'job_id':job.id})==1


def test_user_cannot_publish_and_private_retained_video_remains_private(client,media_paths):
    job=completed_job(now()-timedelta(minutes=10),media=True,frames=True)
    assert client.get(f'/api/videos/{job.id}/source').status_code==401
    client.post('/api/auth/register',json={'name':'Viewer','email':'viewer@example.invalid','password':'test-viewer-password'})
    assert client.get(f'/api/videos/{job.id}/source').status_code==403
    assert client.post(f'/api/videos/{job.id}/archive',json={}).status_code==403
    assert client.get('/api/monitor/cameras/1/frame').status_code==404


def test_moving_camera_revokes_old_preview(admin_client,media_paths):
    job=completed_job(now()-timedelta(minutes=10),frames=True)
    assert admin_client.post(f'/api/videos/{job.id}/publish',json={'share_preview':True}).status_code==200
    camera=admin_client.get('/api/cameras').json()[0]
    camera['segment_id']=2
    assert admin_client.put('/api/cameras/1',json=camera).status_code==200
    assert admin_client.get('/api/monitor/cameras/1/frame').status_code==404
    row=admin_client.get('/api/monitor/cameras').json()['cameras'][0]
    assert row['density'] is None and row['image_url'] is None


def test_legacy_manual_observations_are_counted_and_linked_samples_not_duplicated(client):
    at=datetime(2026,1,15,7,tzinfo=history.LOCAL)
    with SessionLocal() as db:
        ob=Observation(segment_id=1,user_id=1,density='HIGH',score=.9,count=10,observed_at=at.astimezone(timezone.utc).isoformat())
        db.add(ob);db.commit()
    assert report(client)['summary']['raw_samples']==1
    sample(1,at,observation_id=ob.id)
    assert report(client)['summary']['raw_samples']==1


def test_future_route_uses_only_qualified_history_not_current_camera(admin_client,route_request,monkeypatch):
    clock=datetime(2026,1,26,12,tzinfo=timezone.utc)
    monkeypatch.setattr(history,'now',lambda:clock)
    from backend.app import routing
    monkeypatch.setattr(routing,'now',lambda:clock)
    # Tuesday 07:00 local, three earlier Tuesdays with four slots per day.
    for day in (6,13,20):
        for minute in (0,10,20,30): sample(1,datetime(2026,1,day,7,minute,tzinfo=history.LOCAL))
    from backend.app.schemas import RouteRequest
    req=RouteRequest.model_construct(**route_request)
    req.departure_at=datetime(2026,1,27,7,tzinfo=history.LOCAL)
    with SessionLocal() as db:
        evidence=routing.route_evidence(db,req,db.find(Segment))
    assert evidence[1].source=='historical' and evidence[1].density=='HIGH'
    assert evidence[1].evidence_days==3 and 2 not in evidence


def test_future_samples_are_excluded(client,monkeypatch):
    clock=datetime(2026,1,15,7,tzinfo=history.LOCAL)
    monkeypatch.setattr(history,'now',lambda:clock)
    sample(1,clock+timedelta(hours=1))
    assert report(client)['summary']['raw_samples']==0


def test_calibrated_camera_density_has_priority_over_raw_score(client):
    at=datetime(2026,1,15,7,tzinfo=history.LOCAL)
    a=sample(1,at,.8)
    b=sample(1,at,.4,camera_id=2)
    # Camera A has a high capacity/threshold, camera B a lower calibrated threshold.
    get_database().traffic_samples.update_one({'_id':a.id},{'$set':{'density':'LOW'}})
    get_database().traffic_samples.update_one({'_id':b.id},{'$set':{'density':'HIGH'}})
    data=report(client)
    assert data['hourly'][7]['high_share']==1
    assert data['hourly'][7]['average_score']==.4


def test_partial_publication_can_be_retried_without_duplicate_samples(admin_client,media_paths):
    job=completed_job(now()-timedelta(minutes=10))
    assert admin_client.post(f'/api/videos/{job.id}/publish',json={'share_preview':True}).status_code==409
    assert admin_client.post(f'/api/videos/{job.id}/publish',json={'share_preview':False}).status_code==200
    assert get_database().traffic_samples.count_documents({'job_id':job.id})==4


def test_latest_published_frame_updates_current_road_density(admin_client,media_paths):
    job=completed_job(now()-timedelta(minutes=10))
    with SessionLocal() as db:
        item=db.get(VideoJob,job.id)
        db.add(AlertRule(user_id=1,segment_id=1,density='HIGH'))
        item.result['density']='LOW';item.result['score']=.1
        item.result['samples'][0]['density']='LOW';item.result['samples'][0]['score']=.1
        db.commit()
    assert admin_client.post(f'/api/videos/{job.id}/publish',json={}).status_code==200
    assert admin_client.get('/api/segments').json()[0]['observation']['density']=='HIGH'
    notices=admin_client.get('/api/alerts').json()['notifications']
    assert len(notices)==1 and 'mật độ cao' in notices[0]['message']


def test_future_route_does_not_reuse_present_density(admin_client,route_request):
    assert admin_client.post('/api/observations',json={'segment_id':1,'score':.1,'count':1,'note':'Current observation only','observed_at':now().isoformat()}).status_code==201
    route_request['departure_at']=(now()+timedelta(days=1)).isoformat()
    data=admin_client.post('/api/routes/search',json=route_request).json()
    assert all(s['density'] is None for r in data['routes'] for s in r['segments'])


@pytest.mark.parametrize('retain',[False,True])
def test_worker_decodes_video_and_applies_explicit_retention(admin_client,media_paths,monkeypatch,tmp_path,retain):
    """Real OpenCV decode/storage pipeline, with detector isolated as a unit-test stub."""
    import cv2
    import numpy as np
    from types import SimpleNamespace
    from backend.app import video
    clip=tmp_path/'empty-road.avi'
    writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'MJPG'),5,(64,48))
    assert writer.isOpened()
    for _ in range(10): writer.write(np.zeros((48,64,3),dtype=np.uint8))
    writer.release()
    model=tmp_path/'unit-test-model.pt';model.write_bytes(b'unit-test-placeholder')
    monkeypatch.setattr(main,'MODEL_PATH',model)
    monkeypatch.setattr(video,'MODEL_PATH',model)
    monkeypatch.setattr(video,'UPLOADS',monitoring.UPLOADS)
    monkeypatch.setattr(main,'submit',lambda _:None)
    detector=SimpleNamespace(predict=lambda *args,**kwargs:[SimpleNamespace(boxes=[],names={})])
    monkeypatch.setattr(video,'get_model',lambda:detector)
    response=admin_client.post('/api/videos',data={'camera_id':'1','retain_video':str(retain).lower(),
        'observed_at':(now()-timedelta(minutes=10)).isoformat()},files={'file':('empty-road.avi',clip.read_bytes(),'video/x-msvideo')})
    assert response.status_code==202
    job_id=response.json()['id']
    video.analyze(job_id)
    job=admin_client.get(f'/api/videos/{job_id}').json()
    assert job['status']=='completed' and len(job['result']['samples'])==2
    assert not (monitoring.UPLOADS/f'{job_id}.video').exists()
    assert (monitoring.UPLOADS/f'{job_id}.retained').is_file()==retain
    assert admin_client.post(f'/api/videos/{job_id}/archive',json={'share_preview':True}).status_code==200
    board=admin_client.get('/api/monitor/cameras').json()['cameras'][0]
    assert bool(board['video_url'])==retain and board['image_url']
    assert board['vehicle_counts']['car']==board['vehicle_counts']['motorcycle']==0


def test_route_api_labels_weekday_hour_history(admin_client,route_request):
    departure=(now().astimezone(history.LOCAL)+timedelta(days=1)).replace(hour=7,minute=0,second=0,microsecond=0)
    for weeks in (1,2,3):
        for minute in (0,10,20,30): sample(1,departure-timedelta(weeks=weeks)+timedelta(minutes=minute))
    route_request['departure_at']=departure.isoformat()
    # Use an endpoint pair that keeps the monitored direct road among candidates.
    route_request['destination']={'node':'badinh','name':'Quảng trường Ba Đình','lat':21.0368,'lng':105.8346}
    response=admin_client.post('/api/routes/search',json=route_request)
    assert response.status_code==200
    matched=[s for r in response.json()['routes'] for s in r['segments'] if s['id']==1]
    assert matched and all(s['source']=='historical' and s['density']=='HIGH' and s['evidence_days']==3 for s in matched)
