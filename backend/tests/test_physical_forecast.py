from datetime import timedelta
import io
import uuid
import numpy as np
import pytest
from backend.app.db import SessionLocal,now,get_database
from backend.app.models import Segment,ForecastRun
from backend.app.traffic_windows import WindowInput,save_windows,key,reconcile
from backend.app.traffic_forecast import prepare,examples,predict
from backend.app.traffic_learning import partition


def real_road():
    with SessionLocal() as db:
        road=Segment(name='Đường thử nghiệm có phép',start_node='real_a',end_node='real_b',distance_km=1,
            geometry=[[21.,105.8],[21.01,105.8]],is_demo=False)
        db.add(road);db.commit();return road.id


def observation(sid,at,**changes):
    return dict(segment_id=sid,direction='forward',window_end=at.isoformat(),present_count=10,crossing_count=150,
        avg_speed_kmh=20,free_flow_speed_kmh=40,observed_length_m=100,lanes=2,coverage_seconds=300,
        speed_calibrated=True,length_verified=True,verified_state='SLOW',verification_note='Đối chiếu video quan trắc độc lập',
        source='Nguồn thử kiểm chứng',training_allowed=True,**changes)


def test_window_api_permissions_dry_run_and_direction(analyst_client):
    sid=real_road();at=(now()-timedelta(minutes=10)).replace(minute=0,second=0,microsecond=0)
    data=observation(sid,at)
    result=analyst_client.post('/api/forecast/traffic/windows',json=data)
    assert result.status_code==201,result.text
    assert result.json()['metrics']['flow_veh_per_hour']==1800
    assert result.json()['metrics']['congestion_index']==.5
    database=get_database();assert database.traffic_windows.count_documents({})==1
    data['direction']='reverse';assert analyst_client.post('/api/forecast/traffic/windows',json=data).status_code==201
    assert database.traffic_windows.count_documents({})==2
    assert database.traffic_samples.count_documents({})==0
    data['window_end']=(now()+timedelta(days=1)).isoformat()
    assert analyst_client.post('/api/forecast/traffic/windows',json=data).status_code==422
    analyst_client.post('/api/auth/logout')
    assert analyst_client.get(f'/api/forecast/traffic/windows?segment_id={sid}').status_code in (401,403)


def test_import_rejects_demo_roads_and_reports_incomplete_quality(analyst_client):
    sid=real_road();at=(now()-timedelta(days=1)).replace(minute=0,second=0,microsecond=0)
    data=observation(sid,at);data['coverage_seconds']=30
    output=io.StringIO();import csv
    writer=csv.DictWriter(output,fieldnames=list(data));writer.writeheader();writer.writerow(data)
    result=analyst_client.post('/api/forecast/traffic/import',files={'file':('observations.csv',output.getvalue(),'text/csv')})
    assert result.status_code==200,result.text
    assert result.json()['usable']==0 and get_database().traffic_windows.count_documents({})==0
    data['segment_id']=1
    assert analyst_client.post('/api/forecast/traffic/windows',json=data).status_code==422


def test_examples_use_future_labels_but_only_past_features_and_preserve_gaps():
    at=(now()-timedelta(days=3)).replace(minute=0,second=0,microsecond=0)
    rows={}
    for i in range(90):
        doc=WindowInput(**observation(99,at+timedelta(minutes=5*i))).document(1)
        doc['at']=at+timedelta(minutes=5*i);rows[doc['at']]=doc
    data=examples({99:rows},[99],30)
    changed={key:dict(row) for key,row in rows.items()}
    future=at+timedelta(minutes=5*17)
    changed[future]=dict(changed[future],verified_state='JAM')
    again=examples({99:changed},[99],30)
    assert data['y'][0]!=again['y'][0] and np.array_equal(data['x'][0],again['x'][0])
    del changed[at+timedelta(minutes=5*8)]
    fewer=examples({99:changed},[99],30)
    assert len(fewer['y'])<len(data['y'])


def test_training_real_xgboost_regression_and_calibration_are_chronological(analyst_client,tmp_path,monkeypatch):
    from backend.app import forecast_ml
    sid=real_road();end=now().replace(hour=0,minute=0,second=0,microsecond=0);start=end-timedelta(days=8)
    docs=[]
    # A deliberately synthetic TEST fixture, isolated from deployed observations.
    for i in range(8*288):
        at=start+timedelta(minutes=5*i)
        phase=(i//12)%3;state=('FREE','SLOW','JAM')[phase];speed=(36,20,8)[phase]
        data=observation(sid,at);data.update(avg_speed_kmh=speed,verified_state=state,present_count=(4,10,30)[phase])
        docs.append(WindowInput(**data).document(1))
    database=get_database();save_windows(database,docs)
    ready,datasets=prepare(database,[sid],start,end)
    assert ready['ready'] and set(ready['horizons'])=={'15','30','60'}
    for horizon,data in datasets.items():
        train,early,calibration,test=partition(data,horizon)
        assert max(data['times'][train])+horizon*60<min(data['times'][early])
        assert max(data['times'][early])+horizon*60<min(data['times'][calibration])
        assert max(data['times'][calibration])+horizon*60<min(data['times'][test])
    monkeypatch.setattr(forecast_ml,'ARTIFACTS',tmp_path)
    ident=str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(ForecastRun(id=ident,user_id=1,target='traffic',segment_ids=[sid],start_at=start.isoformat(),end_at=end.isoformat()));db.commit()
    forecast_ml.train_run(ident,database)
    run=database.forecast_runs.find_one({'_id':ident})
    assert run['status']=='completed',run.get('message')
    for horizon,info in run['report']['horizons'].items():
        assert 0<=info['test_brier_score']<=2 and info['speed_test_mae_kmh']>=0
        assert info['test']['XGBoost']['samples']>25 and 0<info['temperature']<6
        assert (tmp_path/ident/f'traffic-{horizon}.json').is_file() and (tmp_path/ident/f'speed-{horizon}.json').is_file()
    assert not database.forecast_registry.find_one({'_id':'traffic'})  # Never auto-activate.


def test_reconcile_requires_reviewed_actual_at_exact_future_time(analyst_client):
    sid=real_road();at=(now()-timedelta(days=1)).replace(minute=0,second=0,microsecond=0)
    database=get_database();doc=WindowInput(**observation(sid,at)).document(1)
    prediction={'_id':'issued-test','segment_id':sid,'direction':'forward','issue_at':(at-timedelta(minutes=15)).isoformat(),
        'predicted_at':at.isoformat(),'evaluated':False,'run_id':str(uuid.uuid4()),'label':'SLOW','predicted_speed_kmh':18.}
    database.traffic_forecast_outcomes.insert_one(prediction)
    assert reconcile(database)==0
    save_windows(database,[dict(doc,verified_state=None)])
    assert reconcile(database)==0
    save_windows(database,[doc])
    assert reconcile(database)==1
    value=database.traffic_forecast_outcomes.find_one({'_id':'issued-test'})
    assert value['correct'] and value['speed_absolute_error']==2 and reconcile(database)==0


def test_served_probability_speed_ci_and_live_observation_are_distinct(analyst_client,monkeypatch):
    from backend.app import traffic_forecast
    sid=real_road();database=get_database();ident=str(uuid.uuid4())
    issue=(now()-timedelta(minutes=5)).replace(second=0,microsecond=0)
    issue=issue.replace(minute=issue.minute//5*5)
    docs=[WindowInput(**observation(sid,issue-timedelta(minutes=5*i))).document(1) for i in reversed(range(12))]
    save_windows(database,docs)
    info={'deployable':True,'supported_segment_ids':[sid],'speed_deployable':True,'speed_supported_segment_ids':[sid],
        'temperature':1.,'test':{'XGBoost':{'macro_f1':.8}}}
    with SessionLocal() as db:
        db.add(ForecastRun(id=ident,user_id=1,target='traffic',segment_ids=[sid],start_at=(issue-timedelta(days=8)).isoformat(),
            end_at=issue.isoformat(),status='completed',running=False,report={'horizons':{str(h):info for h in (15,30,60)}}));db.commit()
    database.forecast_registry.insert_one({'_id':'traffic:forward','run_id':ident,'activated_by':1,'activated_at':now().isoformat()})
    class Classifier:
        def predict_proba(self,x):return np.asarray([[.05,.1,.85]])
    class Regressor:
        def predict(self,x):return np.asarray([.25])
    monkeypatch.setattr(traffic_forecast,'_cache',{(ident,h):(Classifier(),Regressor()) for h in (15,30,60)})
    result=analyst_client.get(f'/api/forecast/predict?target=traffic&segment_id={sid}').json()
    assert result['state']=='ready' and not result['is_demo'] and len(result['predictions'])==3
    for row in result['predictions']:
        assert row['jam_probability']==pytest.approx(.85) and row['predicted_speed_kmh']==10
        assert row['predicted_congestion_index']==.75 and row['predicted_travel_time_index']==4
        assert sum(row['probabilities'].values())==pytest.approx(1)
    assert database.traffic_forecast_outcomes.count_documents({})==3
    assert predict(database,sid)['state']=='ready' and database.traffic_forecast_outcomes.count_documents({})==3
    assert predict(database,sid,'reverse')['state']=='no_model'
    actual=analyst_client.get(f'/api/traffic/road?segment_id={sid}').json()
    assert actual['metrics']['speed_kmh']['value']==20 and actual['metrics']['congestion_index']['value']==50
    selected=analyst_client.get(f'/api/traffic/forecast?segment_id={sid}&horizon=30').json()
    assert selected['selected']['horizon_minutes']==30 and selected['comparison']['current']['state']=='SLOW'
    database.traffic_windows.delete_one({'_id':key(docs[3])})
    assert predict(database,sid)['state']=='insufficient'
