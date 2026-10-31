import json
from datetime import timedelta
from backend.app import demo_data as demo,calendar_forecast as planning
from backend.app.db import get_database,now,SessionLocal
from backend.app.history import LOCAL


def test_year_history_day_ahead_forecast_and_no_future_leakage(client,monkeypatch,tmp_path):
    monkeypatch.setenv('DEMO_DATA_ENABLED','true');monkeypatch.setattr(demo,'FOLDER',tmp_path)
    database=get_database()
    # Keep one road in this isolated test database; production roads are untouched.
    database.segments.update_many({'_id':{'$ne':1}},{'$set':{'active':False}})
    database.segments.update_one({'_id':1},{'$set':{'name':'Hoàng Quốc Việt'}})
    protected={name:list(database[name].find()) for name in ('observations','traffic_samples','traffic_labels','forecast_registry')}
    assert demo.prepare_demo(database,days=365,estimators=12)
    active=database.demo_registry.find_one({'_id':'active'})
    assert active['history_days']==365 and active['generator_version']==2
    assert database.demo_profiles.count_documents({'dataset_id':active['run_id']})==366
    today=now().astimezone(LOCAL).date();tomorrow=today+timedelta(days=1)
    response=client.get('/api/traffic/outlook',params={'segment_id':1,'date':tomorrow.isoformat(),'hour':17})
    assert response.status_code==200,response.text
    data=response.json();assert data['history_days']==365 and data['date']==tomorrow.isoformat()
    assert data['selected']['similar_days']>=52 and len(data['hourly'])==24
    assert data['is_demo'] and data['source']=='history'
    assert all(row['label'] in ('FREE','SLOW','JAM') for row in data['hourly'])
    assert all(row['label']!='JAM' for row in data['alternatives'])
    # A future generated document cannot influence forecasts or similar-day evidence.
    database.demo_profiles.insert_one({'dataset_id':active['run_id'],'segment_id':1,'date':tomorrow.isoformat(),
        'source':'synthetic','hourly':[{'hour':17,'state':'JAM','slot_count':12,'score':1,'count':100,'speed_kmh':0,'jam_share':1,'free_share':0}],'slots':[]})
    planning._cache.clear()
    again=client.get('/api/traffic/outlook',params={'segment_id':1,'date':tomorrow.isoformat(),'hour':17}).json()
    assert again['hourly']==data['hourly']
    metadata=json.loads((tmp_path/active['run_id']/'outlook-metadata.json').read_text(encoding='utf-8'))
    assert metadata['train_label_end']<metadata['validation_issue_start']
    assert metadata['validation_label_end']<metadata['test_issue_start']
    report=client.get('/api/demo/history?segment_id=1&period=year').json()
    assert report['summary']['observed_days']==365 and len(report['weekdays'])==7*24
    assert report['summary']['slot_count']==365*288
    assert 12<=len(report['monthly'])<=13
    assert {name:list(database[name].find()) for name in protected}==protected
    from backend.app.routing import route_evidence
    from backend.app.schemas import RouteRequest
    from backend.app.models import Segment
    def forbid_future_generation(sid,day,seed=42):
        assert day<=today,'A future generated label must never be used as a prediction'
        return []
    monkeypatch.setattr(demo,'day_rows',forbid_future_generation)
    request=RouteRequest(origin={'lat':21.03,'lng':105.82},destination={'lat':21.04,'lng':105.83},traffic_mode='demo',
        departure_at=planning.datetime.combine(tomorrow,planning.datetime.min.time(),LOCAL)+timedelta(hours=17))
    with SessionLocal() as db:evidence=route_evidence(db,request,[db.get(Segment,1)])
    assert evidence[1].source=='forecast'
    for day,hour in [(today-timedelta(days=1),17),(today+timedelta(days=8),17),(tomorrow,24)]:
        assert client.get('/api/traffic/outlook',params={'segment_id':1,'date':day.isoformat(),'hour':hour}).status_code==422


def test_calendar_requires_history_and_preserves_missing_values(client):
    response=client.get('/api/traffic/outlook',params={'segment_id':1,'date':(now().astimezone(LOCAL).date()+timedelta(days=1)).isoformat()})
    assert response.status_code==409
