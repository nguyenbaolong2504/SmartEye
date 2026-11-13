import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import httpx
import pytest
from backend.app import camera_context as context,camera_video
from backend.app.db import get_database,now,SessionLocal
from backend.app.models import VideoJob,User
from backend.app.passwords import hash_password
from backend.app.history import LOCAL
from backend.tests.test_camera_video import published_video


def test_conditions_use_only_publications_known_at_issue_on_exact_road_and_direction(client):
    db=get_database();issue=now()
    snapshot={'segment_id':1,'direction':'forward','kind':'accident',
              'published_at':(issue-timedelta(hours=1)).isoformat(),
              'start_at':(issue-timedelta(minutes=30)).isoformat(),'end_at':(issue+timedelta(hours=1)).isoformat()}
    # Collection is intentionally raw here: also verifies malformed legacy publications are ignored.
    docs=[{'public_snapshot':snapshot,'status':'published'},
          {'public_snapshot':dict(snapshot,kind='roadwork',segment_id=2),'status':'published'},
          {'public_snapshot':dict(snapshot,kind='roadwork',direction='reverse'),'status':'published'},
          {'public_snapshot':dict(snapshot,kind='flood',published_at=(issue+timedelta(minutes=1)).isoformat()),'status':'published'},
          {'public_snapshot':dict(snapshot,kind='flood',end_at=issue.isoformat()),'status':'ended'},
          {'public_snapshot':dict(snapshot,kind='obstruction'),'status':'cancelled'},
          {'public_snapshot':dict(snapshot,kind='roadwork',start_at='broken'),'status':'published'},
          {'public_snapshot':None,'status':'pending_verification','kind':'flood'}]
    # Use an isolated collection without the live business validator for legacy-shape cases.
    db.create_collection('camera_context_publication_fixture')
    db.camera_context_publication_fixture.insert_many(docs)
    database=SimpleNamespace(traffic_warnings=db.camera_context_publication_fixture)
    actual=context.public_conditions(database,1,issue)
    assert actual['accident'] and actual['notice_count']==1
    assert not any(actual[k] for k in ('roadwork','flood','obstruction'))
    assert not {'content','incident_id','user_id','attachments'} & actual.keys()
    # A historically valid publication still counts after automatic expiration today.
    db.camera_context_publication_fixture.update_one({'public_snapshot':snapshot},{'$set':{'status':'ended'}})
    assert context.public_conditions(database,1,issue)['accident']


def test_weather_uses_utc_date_and_latest_nonfuture_hour_and_reuses_cache(monkeypatch):
    issue=now().astimezone(LOCAL).replace(hour=1,minute=15,second=0,microsecond=0)
    utc=issue.astimezone(timezone.utc);hour=utc.replace(minute=0)
    monkeypatch.setattr(context,'_cache',{})
    calls=[]
    def get(url,**options):
        calls.append(options['params'])
        return httpx.Response(200,request=httpx.Request('GET',url),json={'hourly':{
            'time':[hour.timestamp(),(hour+timedelta(hours=1)).timestamp()],
            'precipitation':[7,50],'visibility':[2500,10],'wind_speed_10m':[12,99]}})
    monkeypatch.setattr(context.httpx,'get',get)
    actual=context.weather_at([21.01,105.82],issue)
    assert actual['known'] and actual['rain_mm']==7 and actual['visibility_km']==2.5
    assert actual['at']==hour.isoformat()
    assert calls[0]['start_date']==utc.date().isoformat()
    assert context.weather_at([21.01,105.82],issue)==actual and len(calls)==1


@pytest.mark.parametrize('failure',['timeout','missing','negative','nan'])
def test_weather_failure_is_unknown_and_never_fabricates_dry_weather(monkeypatch,failure):
    monkeypatch.setattr(context,'_cache',{})
    def get(url,**_):
        if failure=='timeout':raise httpx.ReadTimeout('slow')
        rain={'missing':None,'negative':-1,'nan':float('nan')}[failure]
        return httpx.Response(200,request=httpx.Request('GET',url),content=json.dumps({'hourly':{
            'time':[now().timestamp()-60],'precipitation':[rain],'visibility':[10000],'wind_speed_10m':[10]}}))
    monkeypatch.setattr(context.httpx,'get',get)
    actual=context.weather_at([21,105],now())
    assert not actual['known'] and actual['rain_mm'] is None


def test_demo_conditions_are_explicit_and_do_not_change_publication_records(client,monkeypatch):
    database=get_database();before=list(database.traffic_warnings.find())
    def no_weather_call(*_):raise AssertionError('Simulated weather must not wait for an external API')
    monkeypatch.setattr(context,'weather_at',no_weather_call)
    result=context.resolve(database,SimpleNamespace(id=1,geometry=[[21,105]]),now(),
                           {'weather':'heavy','incident':'accident','road_condition':'flood'})
    assert result['weather']['source']=='demo_override' and result['weather']['rain_mm']==12
    assert result['road']['accident'] and result['road']['flood'] and result['road']['wet_surface']
    assert len(context.vector(result))==len(context.FEATURES)
    assert list(database.traffic_warnings.find())==before


def test_training_conditions_affect_labels_and_missing_flags_are_part_of_features():
    changed=0;missing=0
    for hour in range(24):
        row={'at':datetime(2026,11,1,hour,tzinfo=LOCAL),'score':.3,'count':10,'speed_kmh':25}
        adjusted,label,conditions=context.training_row(row,1)
        assert adjusted['at']==row['at'] and 0<=adjusted['score']<=1
        if adjusted['speed_kmh']<25:changed+=1
        if not conditions['weather']['known']:
            missing+=1;assert context.vector(conditions)[0]==0 and context.vector(conditions)[3]==0
        assert label in ('FREE','SLOW','JAM')
    assert changed and missing


def test_forecast_preview_requires_both_permissions_and_keeps_shared_analysis_unchanged(client,monkeypatch):
    from backend.app import camera_forecast
    job=published_video()
    seen=[]
    def predict(*args,**kwargs):
        seen.append(kwargs['conditions']);return {'is_demo':True,'timeline':[],'conditions':kwargs['conditions']}
    monkeypatch.setattr(camera_forecast,'predict_samples',predict)
    monkeypatch.setattr(context,'weather_at',lambda *_:{'known':False,'source':'Open-Meteo'})
    endpoint='/api/traffic/cameras/recordings/1/forecast'
    response=client.post(endpoint,json={'weather':'heavy','road_condition':'roadwork','incident':'accident'})
    assert response.status_code==200
    assert seen[0]['road']['accident'] and seen[0]['road']['roadwork']
    with SessionLocal() as db:
        assert db.get(VideoJob,job.id).result==job.result
        db.add(User(email='camera-context@test.vn',name='Camera only',role='user',password=hash_password('test-context-password'),permissions=['cameras.view']));db.commit()
    client.post('/api/auth/login',json={'email':'camera-context@test.vn','password':'test-context-password'})
    assert client.post(endpoint,json={}).status_code==403
    assert len(seen)==1


def test_forecast_preview_validates_inputs_and_rejects_changed_camera(client,monkeypatch):
    from backend.app.models import Camera
    published_video();endpoint='/api/traffic/cameras/recordings/1/forecast'
    assert client.post(endpoint,json={'weather':'tornado'}).status_code==422
    assert client.post(endpoint,json={'url':'http://private/'}).status_code==422
    with SessionLocal() as db:db.update(Camera,1,{'capacity':99});db.commit()
    assert client.post(endpoint,json={}).status_code==409
