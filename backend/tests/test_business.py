from datetime import timedelta
from pydantic import ValidationError
import pytest
from backend.app.db import SessionLocal, now
from backend.app.models import Observation, VideoJob
from backend.app.schemas import CameraInput, RouteRequest
from backend.app.routing import rank_routes
from backend.app.traffic import classify
from backend.app.video import summarize_boxes

def test_exact_density_boundaries():
    assert [classify(v) for v in (0,.249,.25,.599,.6,1)] == ['LOW','LOW','NORMAL','NORMAL','HIGH','HIGH']

def test_stationary_vehicles_and_overlap():
    boxes=[{'box':[10,10,90,90],'label':'car','confidence':.9}]*2
    accepted,occupancy,score=summarize_boxes(boxes,[0,0,1,1],30,100,100)
    assert len(accepted)==2
    assert .63 < occupancy < .66 # union of two identical boxes, not sum
    assert classify(score)=='HIGH'

def test_roi_excludes_non_road_vehicles():
    boxes=[{'box':[0,0,20,20],'label':'car','confidence':.9}]
    accepted,occupied,score=summarize_boxes(boxes,[.5,.5,1,1],30,100,100)
    assert accepted==[] and occupied==score==0

def test_invalid_camera_configuration():
    with pytest.raises(ValidationError): CameraInput(name='Test',segment_id=1,low_threshold=.7,high_threshold=.6)
    with pytest.raises(ValidationError): CameraInput(name='Test',segment_id=1,roi=[1,0,.5,1])

def test_ranking_respects_priority_and_dominance():
    routes=[{'id':'fast','duration_seconds':600,'distance_km':8,'risk':.9},{'id':'safe','duration_seconds':800,'distance_km':7,'risk':.1},{'id':'worse','duration_seconds':900,'distance_km':9,'risk':.8}]
    ranked=rank_routes(routes,{'time':0,'distance':0,'density':1})
    assert ranked[0]['id']=='safe'
    assert next(r for r in ranked if r['id']=='worse')['dominated']

def test_route_input_validation(client,route_request):
    route_request['destination']=route_request['origin']
    assert client.post('/api/routes/search',json=route_request).status_code==422
    route_request['weights']={'time':0,'distance':0,'density':0}
    with pytest.raises(ValidationError): RouteRequest(**route_request)

def test_unknown_data_never_claims_free_flow(client,route_request):
    response=client.post('/api/routes/search',json=route_request)
    assert response.status_code==200
    data=response.json()
    assert len(data['routes'])==3
    assert all(r['unknown_share']==1 for r in data['routes'])
    assert 'chưa thể khẳng định không tắc' in data['recommendation']['reason']

def test_fresh_density_changes_recommendation(admin_client,route_request):
    # Make all roads on initial shortest route crowded, alternate corridor clear.
    for segment_id in range(1,7):
        response=admin_client.post('/api/observations',json={'segment_id':segment_id,'score':.95 if segment_id<=3 else .05,'count':25,'note':'Quan sát kiểm thử đường','observed_at':now().isoformat()})
        assert response.status_code==201
    result=admin_client.post('/api/routes/search',json=route_request).json()
    assert result['routes'][0]['high_share']==0
    assert result['routes'][0]['unknown_share']==0

def test_stale_and_future_data(admin_client):
    response=admin_client.post('/api/observations',json={'segment_id':1,'score':.9,'note':'Dữ liệu cũ kiểm thử','observed_at':(now()-timedelta(hours=1)).isoformat()})
    assert response.status_code==201
    assert admin_client.get('/api/segments').json()[0]['observation'] is None
    response=admin_client.post('/api/observations',json={'segment_id':1,'score':.9,'note':'Thời gian tương lai','observed_at':(now()+timedelta(hours=1)).isoformat()})
    assert response.status_code==422

def test_alert_cooldown_and_read(admin_client):
    assert admin_client.post('/api/alerts',json={'segment_id':1,'density':'HIGH'}).status_code==201
    assert admin_client.post('/api/alerts',json={'segment_id':1,'density':'HIGH'}).status_code==409
    for _ in range(2):
        assert admin_client.post('/api/observations',json={'segment_id':1,'score':.8,'note':'Kiểm thử cảnh báo','observed_at':now().isoformat()}).status_code==201
    notices=admin_client.get('/api/alerts').json()['notifications']
    assert len(notices)==1
    assert admin_client.post(f'/api/notifications/{notices[0]["id"]}/read').status_code==200
    assert admin_client.get('/api/alerts').json()['notifications'][0]['read']

def test_historical_video_cannot_publish(admin_client):
    with SessionLocal() as db:
        db.add(VideoJob(id='historical',user_id=1,camera_id=1,filename='old.mp4',status='completed',observed_at=(now()-timedelta(hours=2)).isoformat(),camera_config={'segment_id':1},result={'density':'HIGH','score':.9,'average_count':30,'model':'test'}));db.commit()
    assert admin_client.post('/api/videos/historical/publish').status_code==422
    with SessionLocal() as db: assert db.query(Observation).count()==0

def test_video_publishes_once(admin_client):
    with SessionLocal() as db:
        db.add(VideoJob(id='fresh',user_id=1,camera_id=1,filename='new.mp4',status='completed',observed_at=now().isoformat(),camera_config={'segment_id':1},result={'density':'HIGH','score':.9,'average_count':30,'model':'test'}));db.commit()
    assert admin_client.post('/api/videos/fresh/publish').status_code==200
    assert admin_client.post('/api/videos/fresh/publish').status_code==409

def test_csv_formula_injection(admin_client):
    admin_client.post('/api/observations',json={'segment_id':1,'score':.8,'note':'=HYPERLINK("bad")','observed_at':now().isoformat()})
    export=admin_client.get('/api/reports/export')
    assert export.status_code==200 and "'=HYPERLINK" in export.text
