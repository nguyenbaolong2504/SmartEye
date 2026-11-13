from copy import deepcopy
import uuid
import pytest
from backend.app.camera_summary import summarize_video
from backend.app import camera_forecast,camera_context
from backend.app.db import SessionLocal
from backend.app.models import Camera,VideoJob
from backend.tests.test_camera_video import published_video


def frame(second,count,score,known=False,stopped=None):
    return {'second':second,'count':count,'score':score,'occupancy':.1,'density':'NORMAL',
        'vehicle_counts':{'car':count,'motorcycle':0,'bus':0,'truck':0},
        'load_ratio':score,'motion_known':known,'stopped_share':stopped,'cumulative_count':1000}


def test_video_summary_uses_recent_typical_load_not_peak_or_cumulative_total():
    rows=[frame(i,90,.99) for i in range(10)]+[frame(i,4,.2,True,.3) for i in range(10,19)]+[frame(19,70,.9)]
    original=deepcopy(rows)
    sample,basis,summary=summarize_video({'frames':rows,'fps':1})
    assert summary['start_second']==10 and summary['end_second']==20 and summary['frames']==10
    assert summary['median_count']==sample['count']==4
    assert sample['score']==sample['load_ratio']==.2 and sample['second']==19
    assert sample['motion_known'] and sample['stopped_share']==pytest.approx(.3)
    assert basis['second']==18 and basis['count']==sum(basis['vehicle_counts'].values())==4
    assert basis['cumulative_count']==1000
    assert rows==original


def test_short_video_uses_all_frames_and_missing_motion_stays_unknown():
    rows=[frame(i/2,2*i,.1*i,i==0,.8 if i==0 else None) for i in range(4)]
    sample,basis,summary=summarize_video({'frames':rows,'fps':2})
    assert summary['observed_seconds']==2 and summary['frames']==4
    assert sample['count']==summary['median_count']==3
    assert sample['score']==pytest.approx(.15)
    assert not sample['motion_known'] and sample['stopped_share'] is None
    assert basis['count'] in (2,4)


def test_legacy_samples_have_vehicle_counts_without_returning_boxes():
    sample={'second':0,'count':3,'score':.2,'boxes':[{'label':name} for name in ('car','motorcycle','motorbike')]}
    _,basis,summary=summarize_video({'samples':[sample]})
    assert basis['vehicle_counts']=={'car':1,'motorcycle':2,'bus':0,'truck':0}
    assert 'boxes' not in basis and summary['observed_seconds']==1
    with pytest.raises(ValueError):summarize_video({'frames':[]})


def test_compact_analysis_preserves_evidence_and_permissions(client):
    job=published_video()
    full=client.get('/api/traffic/cameras/recordings/1/analysis').json()
    compact=client.get('/api/traffic/cameras/recordings/1/analysis?include_forecast=false').json()
    assert full['forecast']['timeline'] and compact['forecast']['timeline']==[]
    assert compact['analysis_id']==job.id and compact['samples']==full['samples']
    assert {k:v for k,v in compact.items() if k!='forecast'}=={k:v for k,v in full.items() if k!='forecast'}


def test_selected_horizon_analyzes_one_video_summary_without_mutating_shared_records(client,monkeypatch):
    job=published_video()
    with SessionLocal() as db:
        updated=deepcopy(job.result)
        updated['frames']=[frame(i,5,.2) for i in range(11)]+[frame(11,50,.9)]
        updated['fps']=1
        db.update(VideoJob,job.id,{'result':updated});db.commit()
    captured=[]
    def predict(database,ident,samples,config,**options):
        captured.append((samples,options))
        return {'is_demo':True,'timeline':[{'second':samples[0]['second'],'predictions':[
            {'horizon_minutes':h,'congestion_probabilities':{'FREE':.9,'SLOW':.08,'JAM':.02}} for h in options['horizons']]}]}
    monkeypatch.setattr(camera_forecast,'predict_samples',predict)
    monkeypatch.setattr(camera_context,'weather_at',lambda *_:{'known':False,'source':'Open-Meteo'})
    response=client.post('/api/traffic/cameras/recordings/1/forecast',json={
        'horizon_minutes':30,'analysis_id':job.id,'whole_video':True})
    assert response.status_code==200
    body=response.json()
    assert body['scope']=='video' and body['analysis_id']==job.id and body['summary']['frames']==10
    assert len(body['timeline'])==len(body['timeline'][0]['predictions'])==1
    assert body['timeline'][0]['predictions'][0]['horizon_minutes']==30
    assert len(captured[0][0])==1 and captured[0][0][0]['score']==.2 and captured[0][1]['horizons']==(30,)
    assert body['basis']['count']==5
    with SessionLocal() as db:
        assert db.get(VideoJob,job.id).result==updated
        assert db.database.observations.count_documents({'job_id':job.id})==0


def test_selected_forecast_rejects_stale_or_unpublished_video_and_bad_horizon(client):
    job=published_video();endpoint='/api/traffic/cameras/recordings/1/forecast'
    body={'horizon_minutes':15,'analysis_id':job.id,'whole_video':True}
    assert client.post(endpoint,json={**body,'analysis_id':str(uuid.uuid4())}).status_code==409
    assert client.post(endpoint,json={'whole_video':True,'horizon_minutes':15}).status_code==409
    assert client.post(endpoint,json={**body,'horizon_minutes':45}).status_code==422
    assert client.post(endpoint,json={**body,'analysis_id':'not-a-job'}).status_code==422
    with SessionLocal() as db:db.update(Camera,1,{'preview_job_id':None});db.commit()
    assert client.post(endpoint,json=body).status_code==409
