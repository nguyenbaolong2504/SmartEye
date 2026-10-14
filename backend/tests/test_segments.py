from backend.app.db import now

def test_surveyed_segment_and_camera_lifecycle(admin_client):
    payload={'name':'Đường khảo sát','start_node':'test_a','end_node':'test_b','distance_km':.8,'geometry':[[21.02,105.82],[21.025,105.825]],'is_demo':False}
    response=admin_client.post('/api/segments',json=payload)
    assert response.status_code==201
    ident=response.json()['id']
    camera=admin_client.post('/api/cameras',json={'name':'Camera khảo sát','segment_id':ident})
    assert camera.status_code==201
    admin_client.post('/api/observations',json={'segment_id':ident,'score':.8,'note':'Khảo sát đoạn đường thực tế','observed_at':now().isoformat()})
    payload['geometry']=[[21.03,105.83],[21.035,105.835]]
    assert admin_client.put(f'/api/segments/{ident}',json=payload).status_code==409
    assert admin_client.delete(f'/api/segments/{ident}').status_code==200
    assert not next(c for c in admin_client.get('/api/cameras').json() if c['id']==camera.json()['id'])['active']

def test_invalid_survey_coordinates(admin_client):
    payload={'name':'Invalid road','start_node':'start','end_node':'end','distance_km':1,'geometry':[[1,1],[2,2]]}
    assert admin_client.post('/api/segments',json=payload).status_code==422
