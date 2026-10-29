from datetime import timedelta
import json
import pytest
from backend.app import demo_data as demo
from backend.app.db import get_database,SessionLocal,now
from backend.app.history import LOCAL
from backend.app.schemas import RouteRequest
from backend.app.routing import search_routes


def test_synthetic_training_prediction_history_and_provenance(client,monkeypatch,tmp_path,route_request):
    monkeypatch.setenv('DEMO_DATA_ENABLED','true')
    monkeypatch.setattr(demo,'FOLDER',tmp_path)
    database=get_database()
    protected=('observations','traffic_samples','traffic_labels','forecast_registry','forecast_runs')
    before={name:list(database[name].find()) for name in protected}
    assert client.get('/api/demo/predict?segment_id=1').status_code==409
    assert demo.prepare_demo(database,days=9,estimators=24)
    state=client.get('/api/demo/status').json()
    assert state['ready'] and state['is_demo']
    road=state['segment_ids'][0]
    output=client.get(f'/api/demo/predict?segment_id={road}').json()
    assert output['is_demo'] and output['state']=='ready'
    assert {p['horizon_minutes'] for p in output['predictions']}=={15,30}
    assert all(p['label'] in demo.CLASSES['congestion'] for p in output['predictions'])
    assert client.get('/api/demo/predict?segment_id=999999').status_code==404
    active=database.demo_registry.find_one({'_id':'active'})
    metadata=json.loads((tmp_path/active['run_id']/'metadata.json').read_text(encoding='utf-8'))
    for scores in metadata['horizons'].values():
        assert scores['train_label_end']<scores['validation_issue_start']
        assert scores['validation_label_end']<scores['test_issue_start']
        assert scores['test']['samples']>0
    yesterday=(now().astimezone(LOCAL)-timedelta(days=1)).date().isoformat()
    report=client.get(f'/api/demo/history?segment_id={road}&value={yesterday}').json()
    assert report['is_demo'] and report['summary']['slot_count']==288
    assert len(report['hourly'])==24 and report['peak_hours']
    assert client.get(f'/api/demo/history?segment_id={road}&period=month').status_code==200
    assert client.get(f'/api/demo/history?segment_id={road}&value=2099-01-01').status_code==422
    csv=client.get(f'/api/demo/export.csv?segment_id={road}').text
    assert 'source' in csv and 'synthetic' in csv
    bootstrap=client.get('/api/bootstrap?data_mode=demo').json()
    assert bootstrap['demo']['ready'] and any(s['observation'] for s in bootstrap['segments'])
    request=RouteRequest(**{**route_request,'traffic_mode':'demo'})
    import asyncio
    with SessionLocal() as db:result=asyncio.run(search_routes(db,request))
    assert result['is_demo'] and any(s['source']=='simulation' for s in result['routes'][0]['segments'])
    assert {name:list(database[name].find()) for name in protected}==before


def test_demo_seed_is_reproducible_and_distinct():
    today=now().date()
    assert demo.day_rows(1,today)==demo.day_rows(1,today)
    assert demo.day_rows(1,today)!=demo.day_rows(2,today)
    assert len(demo.day_rows(1,today))==288


def test_retired_video_and_demo_permissions(client,monkeypatch):
    monkeypatch.setenv('VIDEO_FEATURE_ENABLED','false')
    assert client.post('/api/videos').status_code==410
    assert not client.get('/api/config').json()['video_available']
    assert client.post('/api/demo/prepare').status_code==401
    monkeypatch.setenv('DEMO_DATA_ENABLED','false')
    assert client.get('/api/demo/predict?segment_id=1').status_code==503
