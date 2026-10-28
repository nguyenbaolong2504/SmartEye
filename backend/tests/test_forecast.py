from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid
import numpy as np
import pytest
from backend.app import forecast_api, forecast_data as data, forecast_ml as ml
from backend.app.db import get_database, SessionLocal, now
from backend.app.models import TrafficSample, ForecastRun


def body():
    return {'segment_ids':[1],'target':'density','start_at':(now()-timedelta(days=30)).isoformat(),'end_at':now().isoformat(),'epochs':5}


def series_fixture(days=8):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    series={1:{}}
    for i in range(days*288):
        end=start+data.STEP*i
        severity=(i//12)%3
        series[1][end]={'at':end-data.STEP,'score':[.1,.4,.8][severity],'count':[3,12,25][severity],
            'high_share':int(severity==2),'low_share':int(severity==0),'severity':severity,'sample_minutes':5}
    return series


def test_windows_and_split_cannot_leak_future_labels():
    series=series_fixture();a=data.examples(series,{},[1],'density',15)
    train,val,test=data.split_indices(a,15)
    assert a['times'][train].max()+15*60<a['times'][val].min()
    assert a['times'][val].max()+15*60<a['times'][test].min()
    assert a['x'].shape[1:]==(12,9)
    issue=datetime.fromtimestamp(float(a['times'][0]),timezone.utc)
    series[1][issue+timedelta(minutes=15)]['severity']=2
    b=data.examples(series,{},[1],'density',15)
    np.testing.assert_array_equal(a['x'][0],b['x'][0])
    assert b['y'][0]==2


def test_gaps_do_not_become_zero_or_forward_filled():
    series=series_fixture(1)
    first=len(data.examples(series,{},[1],'density',15)['y'])
    del series[1][sorted(series[1])[30]]
    second=len(data.examples(series,{},[1],'density',15)['y'])
    assert first-second==13


def test_congestion_requires_independent_current_and_future_labels():
    series=series_fixture(1)
    assert len(data.examples(series,{},[1],'congestion',15)['y'])==0
    issue=sorted(series[1])[20]
    labels={(1,issue):'FREE',(1,issue+timedelta(minutes=15)):'JAM'}
    output=data.examples(series,labels,[1],'congestion',15)
    assert output['y'].tolist()==[2] and output['baseline'].tolist()==[0]


def test_readiness_and_public_no_model_are_honest(admin_client):
    output=admin_client.post('/api/forecast/readiness',json=body())
    assert output.status_code==200 and not output.json()['ready']
    assert output.json()['horizons']['15']['windows']==0
    result=admin_client.get('/api/forecast/predict?segment_id=1').json()
    assert result['state']=='no_model' and result['predictions']==[]


def test_one_frame_does_not_make_usable_training_slot(client):
    at=(now()-timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
    with SessionLocal() as db:
        db.add(TrafficSample(sample_key='one',segment_id=1,observed_at=at.isoformat(),score=.9,density='HIGH',count=5,source='yolo'));db.commit()
    series,_,raw,slots=data.load_series(get_database(),[1],at,now())
    assert raw==slots==1 and not series


def test_completed_slots_require_three_minutes_and_real_end(client):
    at=(now()-timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
    with SessionLocal() as db:
        for minute in range(3):
            db.add(TrafficSample(sample_key=str(minute),segment_id=1,observed_at=(at+timedelta(minutes=minute)).isoformat(),score=.9,density='HIGH',count=5,source='yolo'))
        db.commit()
    series,_,_,_=data.load_series(get_database(),[1],at,at+timedelta(minutes=3))
    assert not series
    series,_,_,_=data.load_series(get_database(),[1],at,at+timedelta(minutes=5))
    assert list(series[1])==[at+data.STEP]


def test_private_training_and_labels_require_operator(client):
    assert client.post('/api/forecast/runs',json=body()).status_code==401
    assert client.get('/api/forecast/runs').status_code==401
    assert client.get('/api/forecast/status').status_code==200
    client.post('/api/auth/register',json={'name':'Test user','email':'forecast@example.invalid','password':'valid-password-test'})
    assert client.post('/api/forecast/readiness',json=body()).status_code==403
    assert client.get('/api/forecast/labels?segment_id=1').status_code==403


def test_csv_preview_is_read_only_commit_is_idempotent(admin_client):
    at=(now()-timedelta(days=1)).isoformat()
    content=f'segment_id,observed_at,score,count,density\n1,{at},0.8,25,HIGH\n'
    path='/api/forecast/import'
    assert admin_client.post(path,files={'file':('samples.csv',content,'text/csv')}).json()['rows']==1
    assert get_database().traffic_samples.count_documents({})==0
    first=admin_client.post(path+'?dry_run=false',files={'file':('samples.csv',content,'text/csv')})
    assert first.status_code==200 and first.json()['inserted']==1
    again=admin_client.post(path+'?dry_run=false',files={'file':('samples.csv',content,'text/csv')})
    assert again.json()['inserted']==0 and again.json()['duplicates']==1
    assert get_database().traffic_labels.count_documents({})==0


def test_csv_invalid_or_unknown_road_writes_nothing(admin_client):
    at=(now()-timedelta(days=1)).isoformat()
    content=f'segment_id,observed_at,score,count,density\n1,{at},0.1,2,LOW\n1,{at},nan,4,HIGH'
    response=admin_client.post('/api/forecast/import?dry_run=false',files={'file':('samples.csv',content)})
    assert response.status_code==422 and not get_database().traffic_samples.count_documents({})
    content=f'segment_id,observed_at,score,count,density\n999,{at},0.1,2,LOW'
    assert admin_client.post('/api/forecast/import?dry_run=false',files={'file':('samples.csv',content)}).status_code==404


def test_reviewed_labels_update_with_audit_and_no_auto_density_labels(admin_client):
    at=(now()-timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
    payload={'segment_id':1,'observed_at':at.isoformat(),'state':'JAM','note':'Video thực tế cho thấy dòng xe dừng kéo dài'}
    assert admin_client.post('/api/forecast/labels',json=payload).status_code==200
    payload['state']='SLOW'
    assert admin_client.post('/api/forecast/labels',json=payload).status_code==200
    rows=admin_client.get('/api/forecast/labels?segment_id=1').json()
    assert len(rows)==1 and rows[0]['state']=='SLOW' and rows[0]['reviewer_id']==1
    payload['observed_at']=(at+timedelta(minutes=1)).isoformat()
    assert admin_client.post('/api/forecast/labels',json=payload).status_code==422


def test_batch_labels_preview_and_updates_require_reviewed_evidence(admin_client):
    at=(now()-timedelta(days=1)).replace(minute=0,second=0,microsecond=0).isoformat()
    content=f'segment_id,observed_at,state,note\n1,{at},JAM,Observed stopped traffic in reviewed video\n'
    path='/api/forecast/labels/import'
    assert admin_client.post(path,files={'file':('labels.csv',content)}).status_code==200
    assert get_database().traffic_labels.count_documents({})==0
    assert admin_client.post(path+'?dry_run=false',files={'file':('labels.csv',content)}).status_code==200
    response=admin_client.post(path+'?dry_run=false',files={'file':('labels.csv',content.replace('JAM','SLOW'))})
    assert response.json()['updates']==1
    assert get_database().traffic_labels.count_documents({})==1
    assert get_database().traffic_labels.find_one()['state']=='SLOW'
    assert not get_database().traffic_samples.count_documents({})


def test_batch_labels_validate_all_before_writing(admin_client):
    at=(now()-timedelta(days=1)).replace(minute=0,second=0,microsecond=0).isoformat()
    content=f'segment_id,observed_at,state,note\n1,{at},JAM,Reviewed traffic evidence\n2,{at},FAKE,wrong state\n'
    assert admin_client.post('/api/forecast/labels/import?dry_run=false',files={'file':('labels.csv',content)}).status_code==422
    assert not get_database().traffic_labels.count_documents({})


def test_training_cancel_and_duplicate_lock(admin_client,monkeypatch):
    monkeypatch.setattr(forecast_api.importlib.util,'find_spec',lambda name:True)
    submissions=[]
    monkeypatch.setattr(ml.executor,'submit',lambda *args:submissions.append(args))
    first=admin_client.post('/api/forecast/runs',json=body())
    assert first.status_code==202 and len(submissions)==1
    ident=first.json()['id']
    assert admin_client.post('/api/forecast/runs',json=body()).status_code==409
    assert admin_client.post(f'/api/forecast/runs/{ident}/cancel').status_code==200
    ml.train_run(ident,get_database())
    assert get_database().forecast_runs.find_one({'_id':ident})['status']=='cancelled'


def test_worker_releases_lock_on_insufficient_data(admin_client):
    ident=str(uuid.uuid4());values=body()
    with SessionLocal() as db:
        db.add(ForecastRun(id=ident,user_id=1,**values));db.commit()
    ml.train_run(ident,get_database())
    result=get_database().forecast_runs.find_one({'_id':ident})
    assert result['status']=='failed' and not result['running'] and 'Chưa đủ dữ liệu' in result['message']
    assert admin_client.post(f'/api/forecast/runs/{ident}/activate').status_code==409


def test_missing_artifacts_cannot_be_activated(admin_client,tmp_path,monkeypatch):
    ident=str(uuid.uuid4());monkeypatch.setattr(ml,'ARTIFACTS',tmp_path)
    folder=ml.artifact_folder(ident);folder.mkdir();(folder/'metadata.json').write_text('{}')
    get_database().forecast_runs.insert_one({'_id':ident,'user_id':1,'target':'density','status':'completed',
        'running':False,'segment_ids':[1],'report':{'horizons':{'15':{'deployable':True,'supported_segment_ids':[1]}}}})
    assert admin_client.post(f'/api/forecast/runs/{ident}/activate').status_code==409


def test_public_forecast_does_not_serve_unqualified_road(client):
    ident=str(uuid.uuid4());database=get_database()
    database.forecast_registry.insert_one({'_id':'density','run_id':ident,'activated_by':1,'activated_at':now().isoformat()})
    database.forecast_runs.insert_one({'_id':ident,'user_id':1,'target':'density','status':'completed','running':False,
        'segment_ids':[1,2],'report':{'horizons':{'15':{'deployable':True,'supported_segment_ids':[2]}}}})
    result=client.get('/api/forecast/predict?segment_id=1').json()
    assert result['state']=='unsupported' and result['predictions']==[]


def test_future_route_uses_only_time_matched_forecast(client,route_request,monkeypatch):
    departure=now()+timedelta(minutes=15)
    def predicted(database,segment_id,target):
        return {'predictions':[{'label':'JAM','model':'XGBoost','predicted_at':departure.isoformat()}]}
    monkeypatch.setattr(ml,'forecast',predicted)
    route_request['departure_at']=departure.isoformat()
    result=client.post('/api/routes/search',json=route_request).json()
    assert all(s['source']=='forecast' for s in result['routes'][0]['segments'])
    assert 'mô hình dự báo' in result['recommendation']['reason']
    monkeypatch.setattr(ml,'forecast',lambda *args:{'predictions':[{'label':'HIGH','model':'GRU','predicted_at':(departure+timedelta(hours=1)).isoformat()}]})
    result=client.post('/api/routes/search',json=route_request).json()
    assert all(s['source'] is None for s in result['routes'][0]['segments'])


@pytest.mark.parametrize('field,value',[('target','invented'),('epochs',500),('segment_ids',[]),('end_at','2999-01-01T00:00:00Z')])
def test_training_validation(admin_client,field,value):
    payload=body();payload[field]=value
    assert admin_client.post('/api/forecast/runs',json=payload).status_code==422


def test_real_xgboost_and_gru_training_persistence_and_inference(client,tmp_path,monkeypatch):
    try:
        import torch
        import xgboost
    except (ImportError,OSError) as exc:
        if sys.platform=='win32': pytest.skip(f'Windows native ML runtime unavailable: {type(exc).__name__}')
        raise
    ident=str(uuid.uuid4());monkeypatch.setattr(ml,'ARTIFACTS',tmp_path)
    folder=ml.artifact_folder(ident);folder.mkdir()
    dataset=data.examples(series_fixture(),{},[1],'density',15)
    dataset['indices']=data.split_indices(dataset,15)
    result=ml.train_pair(dataset,folder,15,5)
    assert (folder/'xgb-15.json').stat().st_size>100
    assert (folder/'gru-15.pt').stat().st_size>100
    assert result['selected'] in ('XGBoost','GRU')
    for split in ('validation','test'):
        for name in ('XGBoost','GRU','Persistence'):
            score=result[split][name]
            assert 0<=score['macro_f1']<=1
            assert sum(map(sum,score['confusion_matrix']))==score['samples']
    network=ml.gru_network(dataset['x'].shape[2])
    network.load_state_dict(torch.load(folder/'gru-15.pt',weights_only=True))
    with torch.no_grad(): assert network(torch.zeros(1,12,dataset['x'].shape[2])).shape==(1,3)
    import json
    recent=series_fixture(1)[1]
    issue=now().replace(second=0,microsecond=0)
    latest={issue-data.STEP*i:dict(list(recent.values())[-i-1],at=issue-data.STEP*(i+1)) for i in range(12)}
    monkeypatch.setattr(ml,'load_series',lambda *args:({1:latest},{},36,12))
    database=get_database()
    assert client.post('/api/auth/login',json={'email':'admin@test.vn','password':'test-password-only'}).status_code==200
    for selected in ('XGBoost','GRU'):
        info={**result,'selected':selected,'deployable':True,'supported_segment_ids':[1]}
        report={'horizons':{'15':info,'30':{'deployable':False}}}
        (folder/'metadata.json').write_text(json.dumps(report),encoding='utf-8')
        database.forecast_runs.replace_one({'_id':ident},{'_id':ident,'user_id':1,'target':'density','status':'completed','running':False,
            'segment_ids':[1],'end_at':now().isoformat(),'report':report},upsert=True)
        assert client.post(f'/api/forecast/runs/{ident}/activate').status_code==200
        output=client.get('/api/forecast/predict?segment_id=1').json()
        assert output['state']=='ready',output
        assert output['predictions'][0]['model']==selected
        assert output['predictions'][0]['label'] in ('LOW','NORMAL','HIGH')
    # These registry documents are test fixtures only, not deployable field models.
