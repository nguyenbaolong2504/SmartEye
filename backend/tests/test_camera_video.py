import json
import uuid
from datetime import timedelta
import pytest
from fastapi import HTTPException
from backend.app import camera_video,camera_forecast,demo_data,video
from backend.app.db import SessionLocal,get_database,now
from backend.app.history import LOCAL
from backend.app.models import Camera,Segment,User,VideoJob
from backend.app.passwords import hash_password


def published_video():
    with SessionLocal() as db:
        camera=db.get(Camera,1)
        sample={'second':0,'count':3,'score':.2,'occupancy':.1,'density':'LOW',
            'boxes':[{'label':'car'},{'label':'motorcycle'},{'label':'motorbike'}]}
        job=VideoJob(id=str(uuid.uuid4()),user_id=1,camera_id=1,filename='camera.mp4',
            camera_config=camera_video.camera_config(camera),status='completed',retain_video=True,
            source_metadata={'is_demo':True,'author':'Sample creator','page_url':'https://www.pexels.com/video/example/'},
            result={'samples':[sample],'duration_seconds':1,'average_count':3,'peak_count':3,
                'camera_forecast':{'is_demo':True,'timeline':[{'second':0,'predictions':[
                    {'horizon_minutes':h,'label':'LOW'} for h in (15,30,60)]}]}})
        db.add(job);db.update(Camera,1,{'analysis_job_id':job.id,'preview_public':True,'preview_job_id':job.id});db.commit()
        return job


def test_public_video_analysis_separates_frame_counts_and_demo_forecasts(client):
    job=published_video()
    result=client.get('/api/traffic/cameras/recordings/1/analysis')
    assert result.status_code==200
    body=result.json()
    assert body['is_demo'] and body['source']['author']=='Sample creator'
    assert body['samples'][0]['vehicle_counts']=={'car':1,'motorcycle':2,'bus':0,'truck':0}
    assert 'boxes' not in body['samples'][0]
    assert {item['horizon_minutes'] for item in body['forecast']['timeline'][0]['predictions']}=={15,30,60}
    with SessionLocal() as db:assert db.database.observations.count_documents({'job_id':job.id})==0


def test_camera_only_viewer_cannot_read_forecasts(client):
    published_video()
    with SessionLocal() as db:
        db.add(User(email='video-camera@test.vn',name='Camera viewer',role='user',
            password=hash_password('camera-video-test'),permissions=['cameras.view']));db.commit()
    client.post('/api/auth/login',json={'email':'video-camera@test.vn','password':'camera-video-test'})
    body=client.get('/api/traffic/cameras/recordings/1/analysis').json()
    assert body['samples'] and body['forecast'] is None
    assert client.post('/api/cameras/1/analyze-video').status_code==403


def test_recalibration_or_revoking_camera_sharing_blocks_stale_results(client):
    published_video()
    with SessionLocal() as db:db.update(Camera,1,{'capacity':50});db.commit()
    assert client.get('/api/traffic/cameras/recordings/1/analysis').json()['state']=='outdated'
    assert client.get('/api/traffic/cameras/recordings/1/analysis-frame').status_code==404
    with SessionLocal() as db:db.update(Camera,1,{'preview_public':False});db.commit()
    assert client.get('/api/traffic/cameras/recordings/1/analysis').status_code==404


def test_video_analysis_never_follows_another_cameras_private_job(client):
    job=published_video()
    with SessionLocal() as db:db.update(VideoJob,job.id,{'camera_id':2});db.commit()
    assert client.get('/api/traffic/cameras/recordings/1/analysis').status_code==404


def test_admin_reanalysis_is_queued_once_and_keeps_playable_mp4_metadata(admin_client,tmp_path,monkeypatch):
    previous=published_video()
    monkeypatch.setattr(camera_video,'UPLOADS',tmp_path)
    (tmp_path/f'{previous.id}.retained').write_bytes(b'test-video')
    scheduled=[]
    monkeypatch.setattr(video.executor,'submit',lambda *args:scheduled.append(args))
    result=admin_client.post('/api/cameras/1/analyze-video')
    assert result.status_code==202
    ident=result.json()['id']
    with SessionLocal() as db:
        current=db.get(VideoJob,ident);camera=db.get(Camera,1)
        assert current.filename.endswith('.mp4') and camera.analysis_job_id==ident
        assert camera.preview_job_id==previous.id
    assert (tmp_path/f'{ident}.video').read_bytes()==b'test-video'
    assert len(scheduled)==1
    assert admin_client.post('/api/cameras/1/analyze-video').status_code==409


def test_manager_cannot_reanalyze_camera_outside_scope(analyst_client):
    published_video()
    with SessionLocal() as db:
        owner=db.find_one(User,{'email':'analyst@test.vn'});owner.managed_segment_ids=[2];db.commit()
    assert analyst_client.post('/api/cameras/1/analyze-video').status_code==403


def test_two_stale_camera_sessions_cannot_queue_competing_jobs(client,tmp_path,monkeypatch):
    previous=published_video()
    monkeypatch.setattr(camera_video,'UPLOADS',tmp_path)
    path=tmp_path/'camera.mp4';path.write_bytes(b'test-video')
    with SessionLocal() as first,SessionLocal() as second:
        camera1=first.get(Camera,1);camera2=second.get(Camera,1)
        winner=camera_video.queue_video(first,camera1,1,path,previous.source_metadata)
        with pytest.raises(HTTPException) as error:
            camera_video.queue_video(second,camera2,1,path,previous.source_metadata)
        assert error.value.status_code==409
        assert first.get(Camera,1).analysis_job_id==winner.id
        assert first.count(VideoJob,{'status':'queued'})==1
        assert len(list(tmp_path.glob('*.video')))==1


def test_failed_reanalysis_can_recover_from_the_last_shared_video(admin_client,tmp_path,monkeypatch):
    previous=published_video()
    monkeypatch.setattr(camera_video,'UPLOADS',tmp_path)
    (tmp_path/f'{previous.id}.retained').write_bytes(b'last-good-video')
    with SessionLocal() as db:
        failed=VideoJob(id=str(uuid.uuid4()),user_id=1,camera_id=1,filename='camera.mp4',
            camera_config=previous.camera_config,status='failed',source_metadata=previous.source_metadata)
        db.add(failed);db.update(Camera,1,{'analysis_job_id':failed.id});db.commit()
    monkeypatch.setattr(video.executor,'submit',lambda *args:None)
    response=admin_client.post('/api/cameras/1/analyze-video')
    assert response.status_code==202
    assert (tmp_path/f'{response.json()["id"]}.video').read_bytes()==b'last-good-video'


def test_density_model_has_purged_time_splits_and_never_writes_real_observations(client,tmp_path,monkeypatch):
    database=get_database()
    active={'run_id':str(uuid.uuid4()),'segment_ids':[1],'history_days':365}
    monkeypatch.setattr(camera_forecast,'require_active',lambda _:active)
    monkeypatch.setattr(camera_forecast,'FOLDER',tmp_path)
    today=now().astimezone(LOCAL).date()
    for offset in range(1,9):
        day=today-timedelta(days=offset)
        database.demo_profiles.insert_one({'dataset_id':active['run_id'],'segment_id':1,'date':day.isoformat(),
            'slots':demo_data.day_rows(1,day),'source':'synthetic'})
    protected=('observations','traffic_samples','traffic_labels','forecast_runs','forecast_registry')
    before={name:list(database[name].find()) for name in protected}
    report=camera_forecast.prepare_models(database,estimators=5)
    assert 'rain_mm' in report['condition_features'] and 'accident' in report['condition_features']
    assert report['condition_training']=='synthetic_not_real_world_validated'
    for horizon,targets in report['horizons'].items():
      for metrics in targets.values():
        assert metrics['train_label_end']<metrics['validation_issue_start']
        assert metrics['validation_label_end']<metrics['calibration_issue_start']
        assert metrics['calibration_label_end']<metrics['test_issue_start']
        assert metrics['test']['samples']>0 and metrics['test_log_loss']>=0
        assert 0<=metrics['test_high_brier']<=1
    output=camera_forecast.predict_samples(database,1,[{'second':0,'count':4,'score':.1},
        {'second':1,'count':25,'score':.9}],{'low_threshold':.25,'high_threshold':.6})
    assert output['is_demo'] and output['target']=='density_and_congestion' and output['synthetic_context_slots']==11
    assert output['probability_kind']=='calibrated_synthetic' and not output['real_world_validated']
    assert {item['horizon_minutes'] for item in output['timeline'][0]['predictions']}=={15,30,60}
    for frame in output['timeline']:
      for prediction in frame['predictions']:
        assert sum(prediction['congestion_probabilities'].values())==pytest.approx(1,abs=2e-6)
        assert prediction['congestion_probability']==prediction['congestion_probabilities']['JAM']
        assert prediction['congestion_label'] in ('FREE','SLOW','JAM')
        assert prediction['history']['is_demo']
    assert {name:list(database[name].find()) for name in protected}==before
    assert json.loads((camera_forecast.model_folder(active)/'metadata.json').read_text(encoding='utf-8'))['is_demo']


def test_camera_detection_processes_every_frame_and_counts_exactly_the_displayed_boxes(tmp_path,monkeypatch):
    import cv2
    import numpy as np
    from types import SimpleNamespace
    from backend.app import camera_detection
    path=tmp_path/'input.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),12,(400,240))
    for _ in range(4):writer.write(np.zeros((240,400,3),dtype=np.uint8))
    writer.release()
    weights=tmp_path/'model.pt';weights.write_bytes(b'fake-only-for-unit-test')
    monkeypatch.setattr(camera_detection,'MODEL_PATH',weights)
    monkeypatch.setattr(camera_detection,'FOLDER',tmp_path/'cache')
    calls=[]
    class Detector:
        def predict(self,frame,**options):
            calls.append((frame.shape,options))
            return [SimpleNamespace(names={2:'car',3:'motorcycle'},boxes=[
                SimpleNamespace(cls=[2],xyxy=[[10,10,90,90]],conf=[.9]),
                SimpleNamespace(cls=[3],xyxy=[[150,80,170,100]],conf=[.8])])]
    monkeypatch.setattr(video,'get_model',lambda:Detector())
    config={'roi':[.1,.25,.9,.9],'capacity':20,'low_threshold':.25,'high_threshold':.6}
    result=camera_detection.detect_clip(path,config,lambda _:None)
    assert len(result['frames'])==4 and result['fps']==12 and len(calls)==4
    assert [frame['frame_index'] for frame in result['frames']]==[0,1,2,3]
    for frame in result['frames']:
        assert frame['count']==len(frame['boxes'])==sum(frame['vehicle_counts'].values())==2
        assert frame['vehicle_counts']=={'car':1,'motorcycle':1,'bus':0,'truck':0}
        assert frame['boxes'][0]['box']==[50,70,130,150]
        assert frame['cumulative_count']==2
        assert sum(frame['cumulative_vehicle_counts'].values())==2
    assert calls[0][0]==(156,320,3) and calls[0][1]['agnostic_nms']
    again=camera_detection.detect_clip(path,{**config,'capacity':50},lambda _:None)
    assert len(calls)==4 and again['frames'][0]['count']==2


def test_probability_temperature_outputs_distribution_without_forcing_ninety_percent():
    import numpy as np
    values=camera_forecast.probabilities(np.array([[.1,.2,.7],[.6,.3,.1]]),2.)
    assert values.sum(axis=1)==pytest.approx([1,1])
    assert 0<values[0,2]<.7 and values[1,2]!=values[0,2]


def test_cumulative_tracking_does_not_add_the_same_stopped_or_briefly_hidden_car_again():
    from backend.app.camera_counting import cumulative_tracks
    first={'box':[20,30,100,100],'label':'car','confidence':.95}
    second={'box':[180,40,220,100],'label':'motorcycle','confidence':.95}
    sequence=[[first],[first],[first],[],[first],[first,second],[first,second],[first,second]]
    frames=[{'second':i/15,'frame_index':i,'width':400,'height':240,'boxes':boxes} for i,boxes in enumerate(sequence)]
    output=cumulative_tracks(frames,15)
    assert [row['cumulative_count'] for row in output[:5]]==[1]*5
    assert output[-1]['cumulative_count']==2
    assert output[-1]['cumulative_vehicle_counts']=={'car':1,'motorcycle':1,'bus':0,'truck':0}
    car_ids=[box['track_id'] for row in output for box in row['boxes'] if box['label']=='car' and box['track_id']]
    assert len(set(car_ids))==1


def test_rush_hour_setup_is_idempotent_and_preserves_existing_roads_and_cameras(client):
    from scripts.setup_camera_videos import rush_hour_camera
    with SessionLocal() as db:
        roads=list(db.database.segments.find());cameras=list(db.database.cameras.find())
    first=rush_hour_camera();second=rush_hour_camera()
    assert first==second
    with SessionLocal() as db:
        assert db.get(Segment,first[1]).is_demo and db.get(Camera,first[0]).capacity==20
        assert all(db.database.segments.find_one({'_id':row['_id']})==row for row in roads)
        assert all(db.database.cameras.find_one({'_id':row['_id']})==row for row in cameras)


@pytest.mark.parametrize('status,suffix',[('completed','retained'),('processing','video')])
def test_duplicate_camera_worker_does_not_delete_another_runs_video(client,tmp_path,monkeypatch,status,suffix):
    from backend.app import camera_detection
    job=published_video()
    monkeypatch.setattr(camera_detection,'UPLOADS',tmp_path)
    path=tmp_path/f'{job.id}.{suffix}';path.write_bytes(b'owned-by-another-invocation')
    with SessionLocal() as db:db.update(VideoJob,job.id,{'status':status})
    assert camera_detection.analyze_camera(job.id) is False
    assert path.read_bytes()==b'owned-by-another-invocation'


def test_camera_explanation_uses_only_prior_days_at_the_matching_hour_and_weekday(client):
    from datetime import datetime
    database=get_database();active={'run_id':str(uuid.uuid4())}
    issue=datetime(2026,11,12,17,0,tzinfo=LOCAL)
    for day in ('2026-11-05','2026-11-06','2026-11-12','2026-11-19'):
        database.demo_profiles.insert_one({'dataset_id':active['run_id'],'segment_id':1,'date':day,
            'slots':[{'minute':17*60+15,'state':'JAM'},{'minute':17*60+30,'state':'FREE'}]})
    evidence=camera_forecast.history_evidence(database,active,1,issue)
    assert evidence[15]['matching_days']==evidence[15]['jam_days']==1
    assert evidence[15]['hour']=='17:15' and evidence[15]['lookback_days']==100
    assert evidence[30]['matching_days']==1 and evidence[30]['jam_days']==0


@pytest.mark.parametrize('score,expected',[(.1,.125),(.4,.425),(.9,.9)])
def test_forecast_respects_camera_thresholds(score,expected):
    assert camera_forecast.normalized_score(score,.2,.6)==pytest.approx(expected)
