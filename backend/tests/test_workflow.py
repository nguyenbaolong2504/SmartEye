"""Main, alternative, permission and conflict paths in the supplied chapter IV."""
from datetime import timedelta
import pytest
from pymongo.errors import PyMongoError
from backend.app.db import SessionLocal, now, stamp
from backend.app.models import User
from backend.app.passwords import hash_password

PASSWORD='workflow-test-password'


def login(client,email):
    client.cookies.clear()
    assert client.post('/api/auth/login',json={'email':email,'password':PASSWORD if email!='admin@test.vn' else 'test-password-only'}).status_code==200


def people(client):
    with SessionLocal() as db:
        for email,role in [('viewer@test.vn','user'),('manager@test.vn','analyst'),('other-manager@test.vn','analyst'),('other-viewer@test.vn','user')]:
            db.add(User(email=email,name=email.split('@')[0],password=hash_password(PASSWORD),role=role))
        db.commit()


def incident(client):
    point=client.get('/api/segments').json()[0]['geometry'][0]
    response=client.post('/api/incidents',json={'segment_id':1,'direction':'forward','kind':'obstruction','position':point,
        'occurred_at':(now()-timedelta(minutes=2)).isoformat(),'content':'Có vật cản ảnh hưởng đến việc di chuyển trên tuyến.', 'submission_key':'request-incident-001'})
    assert response.status_code==201,response.text
    return response.json()


def note(item,text='Đã đối chiếu và ghi nhận căn cứ xử lý.'):
    return {'revision':item['revision'],'note':text}


def warning(client,incident_id=None):
    body={'segment_id':1,'direction':'forward','kind':'obstruction','position':client.get('/api/segments').json()[0]['geometry'][0],
          'severity':'high','content':'Có vật cản, cần chú ý khi di chuyển qua tuyến đường này.',
          'start_at':(now()-timedelta(minutes=1)).isoformat(),'end_at':(now()+timedelta(hours=2)).isoformat(), 'incident_id':incident_id}
    response=client.post('/api/management/warnings',json=body)
    assert response.status_code==201,response.text
    return response.json(),body


def source(client,speed=True,state=True,direction='forward'):
    login(client,'admin@test.vn')
    response=client.post('/api/admin/sources',json={'name':'Nguồn quan trắc kiểm thử','kind':'file','format':'csv','segment_id':1,'direction':direction,
            'authorized':True,'speed_verified':speed,'state_verified':state,'count_method':'crossings','interval_seconds':60})
    assert response.status_code==201,response.text
    value=response.json();assert not value['active']
    mapping={key:key for key in ('observed_at','segment_id','direction','count','interval_seconds','speed_kmh','score','density','state')}
    value=client.put(f'/api/admin/sources/{value["id"]}/mapping',json={'revision':value['revision'],'mapping':mapping,'units':{'speed_kmh':'km/h'},'confirmed':True}).json()
    sample={'observed_at':(now()-timedelta(seconds=30)).isoformat(),'segment_id':1,'direction':direction,'count':20,'speed_kmh':12,'score':.8,'state':'JAM'}
    value=client.post(f'/api/admin/sources/{value["id"]}/test',json={'revision':value['revision'],'sample':sample}).json()
    assert value['tested']
    value=client.post(f'/api/admin/sources/{value["id"]}/toggle',json={'revision':value['revision'],'active':True,'confirmed':True}).json()
    return value,sample


def test_report_main_lifecycle_keeps_owner_privacy_and_history(client):
    people(client);login(client,'viewer@test.vn');item=incident(client);ident=item['id']
    assert item['status']=='pending'
    assert len(client.get('/api/incidents').json())==1
    login(client,'other-viewer@test.vn');assert client.get(f'/api/incidents/{ident}').status_code==403
    login(client,'admin@test.vn');assert client.get(f'/api/incidents/{ident}').status_code==403
    assert client.get('/api/management/incidents').status_code==403
    login(client,'manager@test.vn')
    assert len(client.get('/api/management/incidents').json())==1
    item=client.post(f'/api/management/incidents/{ident}/accept',json=note(item)).json()
    assert item['status']=='verifying'
    stale=client.post(f'/api/management/incidents/{ident}/accept',json=note(item));assert stale.status_code==409
    item=client.post(f'/api/management/incidents/{ident}/verify',json={**note(item),'conclusion':'insufficient'}).json()
    assert item['status']=='verifying'
    item=client.post(f'/api/management/incidents/{ident}/verify',json={**note(item),'conclusion':'valid'}).json()
    assert item['status']=='processing'
    item=client.post(f'/api/management/incidents/{ident}/progress',json=note(item)).json()
    item=client.post(f'/api/management/incidents/{ident}/resolve',json=note(item)).json()
    assert item['status']=='resolved' and len(item['history'])==6
    assert client.post(f'/api/management/incidents/{ident}/progress',json=note(item)).status_code==409
    login(client,'viewer@test.vn');assert client.get(f'/api/incidents/{ident}').json()['status']=='resolved'


def test_report_rejection_requires_saved_invalid_verification(client):
    people(client);login(client,'viewer@test.vn');item=incident(client);ident=item['id'];login(client,'manager@test.vn')
    item=client.post(f'/api/management/incidents/{ident}/accept',json=note(item)).json()
    assert client.post(f'/api/management/incidents/{ident}/reject',json=note(item)).status_code==409
    item=client.post(f'/api/management/incidents/{ident}/verify',json={**note(item),'conclusion':'invalid'}).json()
    assert item['status']=='verifying'
    item=client.post(f'/api/management/incidents/{ident}/reject',json=note(item)).json();assert item['status']=='rejected'
    assert client.post(f'/api/management/incidents/{ident}/resolve',json=note(item)).status_code==409


def test_other_manager_cannot_take_over_and_scope_is_checked(client):
    people(client);login(client,'viewer@test.vn');item=incident(client);login(client,'manager@test.vn')
    item=client.post(f'/api/management/incidents/{item["id"]}/accept',json=note(item)).json()
    login(client,'other-manager@test.vn')
    assert client.post(f'/api/management/incidents/{item["id"]}/verify',json={**note(item),'conclusion':'valid'}).status_code==403
    with SessionLocal() as db:db.database.users.update_one({'email':'other-manager@test.vn'},{'$set':{'managed_segment_ids':[]}})
    assert client.get(f'/api/incidents/{item["id"]}').status_code==403
    assert client.get('/api/management/incidents').json()==[]


def test_invalid_image_and_future_position_never_create_a_report(client):
    people(client);login(client,'viewer@test.vn')
    import json
    body={'segment_id':1,'direction':'forward','kind':'other','position':[21.0287,105.8524],
          'occurred_at':(now()-timedelta(minutes=1)).isoformat(),'content':'Nội dung đủ dài để kiểm tra.','submission_key':'invalid-image-test'}
    response=client.post('/api/incidents/with-image',data={'payload':json.dumps(body)},files={'image':('x.jpg',b'not an image','image/jpeg')})
    assert response.status_code==422
    body['occurred_at']=(now()+timedelta(hours=1)).isoformat()
    assert client.post('/api/incidents',json=body).status_code==422
    assert client.get('/api/incidents').json()==[]


def test_same_submission_key_is_idempotent(client):
    people(client);login(client,'viewer@test.vn');first=incident(client);second=incident(client)
    assert first['id']==second['id'] and len(client.get('/api/incidents').json())==1


def test_publication_requires_verification_and_versions_do_not_leak(client):
    people(client);login(client,'viewer@test.vn')
    assert client.patch('/api/auth/profile',json={'name':'Viewer','notifications_enabled':True}).status_code==200
    login(client,'manager@test.vn');item,body=warning(client);ident=item['id']
    assert client.get('/api/warnings').json()==[]
    assert client.post(f'/api/management/warnings/{ident}/publish',json={'revision':item['revision']}).status_code==409
    item=client.post(f'/api/management/warnings/{ident}/verify',json={**note(item),'conclusion':'valid'}).json()
    item=client.post(f'/api/management/warnings/{ident}/publish',json={'revision':item['revision']}).json()
    first=client.get(f'/api/warnings/{ident}').json()
    assert first['version']==1 and 'created_by' not in first and 'incident_id' not in first
    assert client.post(f'/api/management/warnings/{ident}/publish',json={'revision':item['revision']}).status_code==409
    body['content']='Nội dung chỉnh sửa mới vẫn đang chờ quản lý xác minh.'
    item=client.patch(f'/api/management/warnings/{ident}',json={**body,'revision':item['revision']}).json()
    assert item['content_version']==2 and item['status']=='pending_verification'
    assert client.get(f'/api/warnings/{ident}').json()['content']==first['content']
    item=client.post(f'/api/management/warnings/{ident}/verify',json={**note(item),'conclusion':'valid'}).json()
    item=client.post(f'/api/management/warnings/{ident}/publish',json={'revision':item['revision']}).json()
    assert client.get(f'/api/warnings/{ident}').json()['version']==2
    login(client,'viewer@test.vn')
    with SessionLocal() as db:
        notices=list(db.database.notifications.find({'warning_id':ident}));assert len(notices)==2
    login(client,'manager@test.vn')
    client.post('/api/management/warnings/retry-deliveries')
    with SessionLocal() as db:assert db.database.notifications.count_documents({'warning_id':ident})==2
    item=client.post(f'/api/management/warnings/{ident}/end',json=note(item)).json()
    assert item['status']=='ended' and client.get('/api/warnings').json()==[]
    assert client.get(f'/api/warnings/{ident}').status_code==404


def test_warning_hides_reporter_contacts_in_publication_and_inbox(client):
    people(client);login(client,'viewer@test.vn')
    client.patch('/api/auth/profile',json={'name':'Tên Người Gửi','notifications_enabled':True})
    report=incident(client);login(client,'manager@test.vn');ident=report['id']
    report=client.post(f'/api/management/incidents/{ident}/accept',json=note(report)).json()
    client.post(f'/api/management/incidents/{ident}/verify',json={**note(report),'conclusion':'valid'})
    item,body=warning(client,ident);ident=item['id']
    content='Tên Người Gửi báo vật cản. Liên hệ viewer@test.vn hoặc 0912 345 678.'
    item=client.patch(f'/api/management/warnings/{ident}',json={**body,'content':content,'revision':item['revision']}).json()
    item=client.post(f'/api/management/warnings/{ident}/verify',json={**note(item),'conclusion':'valid'}).json()
    assert client.post(f'/api/management/warnings/{ident}/publish',json={'revision':item['revision']}).status_code==200
    public=client.get(f'/api/warnings/{ident}').json()['content']
    assert public=='[đã ẩn] báo vật cản. Liên hệ [đã ẩn] hoặc [đã ẩn].'
    with SessionLocal() as db:
        assert public in db.database.notifications.find_one({'warning_id':ident})['message']


def test_cancel_withdraws_publication_and_retains_history(client):
    people(client);login(client,'manager@test.vn');item,_=warning(client);ident=item['id']
    item=client.post(f'/api/management/warnings/{ident}/verify',json={**note(item),'conclusion':'valid'}).json()
    item=client.post(f'/api/management/warnings/{ident}/publish',json={'revision':item['revision']}).json()
    item=client.post(f'/api/management/warnings/{ident}/cancel',json=note(item)).json()
    assert item['status']=='cancelled' and len(item['versions'])==1 and len(item['history'])==4
    assert client.get(f'/api/warnings/{ident}').status_code==404


def test_source_mapping_check_enable_import_and_missing_speed_are_honest(client):
    value,sample=source(client,speed=False,state=False)
    response=client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':[sample,{**sample,'segment_id':999}]})
    assert response.status_code==200 and response.json()['accepted']==1 and response.json()['rejected']==1
    actual=client.get('/api/traffic/road?segment_id=1').json()
    assert actual['state'] is None and actual['fresh']
    assert 'speed_kmh' not in actual['metrics'] and actual['metrics']['count']['value']==20
    assert 'flow_per_minute' not in actual['metrics']
    duplicate=client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':[sample]}).json()
    assert duplicate['duplicates']==1
    value=client.post(f'/api/admin/sources/{value["id"]}/toggle',json={'revision':value['revision'],'active':False,'confirmed':True}).json()
    assert client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':[sample]}).status_code==409
    assert not client.get('/api/traffic/road?segment_id=1').json()['fresh']
    with SessionLocal() as db:assert db.database.road_readings.count_documents({})==1


def test_import_retry_recovers_forecast_input_without_counting_reading_twice(client,monkeypatch):
    from backend.app import sources
    value,sample=source(client)
    url=f'/api/admin/sources/{value["id"]}/receive'
    rows={'rows':[{**sample,'interval_seconds':120,'density':'HIGH'}]}
    def fail_mirror(db,record):
        raise PyMongoError('test-only downstream write failure')
    with monkeypatch.context() as patch:
        patch.setattr(sources,'mirror_forecast_sample',fail_mirror)
        assert client.post(url,json=rows).status_code==503
    response=client.post(url,json=rows)
    assert response.status_code==200 and response.json()['duplicates']==1
    actual=client.get('/api/traffic/road?segment_id=1').json()
    assert actual['metrics']['flow_per_minute']['value']==10
    with SessionLocal() as db:
        assert db.database.road_readings.count_documents({})==1
        assert db.database.traffic_samples.count_documents({'source':'source'})==1


@pytest.mark.parametrize('bad', ['http://example.org/data','https://user:password@example.org/data','https://example.org/data?token=secret','https://127.0.0.1/data','file:///etc/passwd'])
def test_source_rejects_secret_urls_and_unsafe_targets(admin_client,bad):
    response=admin_client.post('/api/admin/sources',json={'name':'Nguồn kiểm thử URL','kind':'api','format':'json','segment_id':1,'authorized':True,'url':bad})
    assert response.status_code==422


def test_current_conditions_are_scoped_and_stale_values_are_not_current(client):
    value,sample=source(client)
    client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':[sample]})
    current=client.get('/api/traffic/road?segment_id=1').json()
    assert current['state']=='JAM' and current['metrics']['speed_kmh']['value']==12
    assert client.get('/api/traffic/road?segment_id=1&direction=reverse').json()['state'] is None
    with SessionLocal() as db:db.database.road_readings.update_many({}, {'$set':{'observed_at':(now()-timedelta(hours=1)).isoformat()}})
    old=client.get('/api/traffic/road?segment_id=1').json()
    assert not old['fresh'] and old['state'] is None and old['metrics']=={}


def test_rule_proposes_only_pending_warning_and_keeps_version(client):
    people(client);value,sample=source(client)
    base=now()
    rows=[{**sample,'observed_at':(base-timedelta(minutes=i,seconds=30)).isoformat()} for i in range(5)]
    client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':rows})
    login(client,'manager@test.vn')
    rule=client.post('/api/management/rules',json={'name':'Theo dõi tốc độ thấp','segment_id':1,'metric':'speed_kmh','operator':'lt','threshold':20,'unit':'km/h','window_minutes':4}).json()
    assert not rule['active']
    rule=client.post(f'/api/management/rules/{rule["id"]}/test',json={'revision':rule['revision']}).json()
    assert rule['tested']
    rule=client.post(f'/api/management/rules/{rule["id"]}/toggle',json={'revision':rule['revision'],'active':True,'confirmed':True}).json()
    login(client,'admin@test.vn')
    result=client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':[{**sample,'observed_at':(base-timedelta(seconds=10)).isoformat()}]})
    assert result.status_code==200,result.text
    assert client.get('/api/warnings').json()==[]
    with SessionLocal() as db:
        warning=db.database.traffic_warnings.find_one({});assert warning and warning['status']=='pending_verification'
        assert warning['rule_id']==rule['id'] and warning['rule_version']==1
    login(client,'manager@test.vn')
    assert client.post(f'/api/management/rules/{rule["id"]}/delete',json=note(rule)).status_code==200
    with SessionLocal() as db:assert db.database.managed_alert_rules.find_one({'_id':rule['id']})['deleted']


def test_admin_accounts_are_separate_from_role_assignment_and_soft_delete(client):
    login(client,'admin@test.vn')
    body={'name':'Tài khoản mới','username':'new-account','email':'new-account@test.vn','phone':'0912345678','password':PASSWORD,'password_confirmation':PASSWORD}
    created=client.post('/api/admin/accounts',json=body);assert created.status_code==201,created.text
    item=created.json()
    assert client.post('/api/admin/accounts',json=body).status_code==409
    assert client.patch(f'/api/admin/accounts/{item["id"]}',json={'revision':1,'name':item['name'],'email':item['email'],'phone':item['phone'],'active':True,'role':'admin'}).status_code==422
    role=client.post(f'/api/admin/accounts/{item["id"]}/role',json={'revision':1,'role':'analyst','managed_segment_ids':[1],'confirmed':True}).json()
    assert role['role']=='analyst'
    disabled=client.post(f'/api/admin/accounts/{item["id"]}/disable',json={'revision':role['profile_version'],'note':'Tài khoản không còn sử dụng.'}).json()
    assert not disabled['active']
    with SessionLocal() as db:assert db.database.users.count_documents({'_id':item['id']})==1
    assert client.post('/api/admin/accounts/1/disable',json={'revision':1,'note':'Không được làm mất quản trị cuối.'}).status_code==422


def test_registration_confirmation_login_and_profile_conflicts(client):
    body={'name':'Người đăng ký','username':'new-viewer','email':'new-viewer@test.vn','password':PASSWORD,'password_confirmation':'different-password'}
    assert client.post('/api/auth/register',json=body).status_code==422
    body['password_confirmation']=PASSWORD
    response=client.post('/api/auth/register',json=body);assert response.status_code==201 and not client.cookies.get('smarteye_session')
    assert client.post('/api/auth/login',json={'email':'new-viewer','password':PASSWORD}).status_code==200
    assert client.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':PASSWORD,'password_confirmation':PASSWORD}).status_code==422
    first=client.patch('/api/auth/profile',json={'name':'Tên mới','revision':1,'phone':'0912345678'});assert first.status_code==200
    assert client.patch('/api/auth/profile',json={'name':'Tên cũ từ tab khác','revision':1}).status_code==409


def test_observed_reports_and_csv_use_identical_filters(client):
    value,sample=source(client)
    start=(now()-timedelta(hours=1)).isoformat();end=stamp()
    client.post(f'/api/admin/sources/{value["id"]}/receive',json={'rows':[sample]})
    query={'segment_id':1,'direction':'forward','start':start,'end':end}
    result=client.get('/api/admin/traffic-report',params=query);assert result.status_code==200
    assert result.json()['valid_samples']==1 and result.json()['unknown_samples']==0
    exported=client.get('/api/admin/traffic-report/export',params=query)
    assert exported.status_code==200 and 'observed' in exported.text and 'JAM' in exported.text
    assert client.get('/api/admin/traffic-report',params={**query,'start':end,'end':start}).status_code==422


def test_journal_redacts_secrets_and_is_read_only(admin_client):
    from backend.app.models import Audit
    with SessionLocal() as db:db.add(Audit(action='source_failed',detail='token=hidden-password mongodb://secret:password@db/test',level='error',service='ingestion'));db.commit()
    items=admin_client.get('/api/admin/events?level=error&service=ingestion').json();assert len(items)==1
    assert 'hidden-password' not in items[0]['detail'] and 'secret:password' not in items[0]['detail']
    assert admin_client.delete(f'/api/admin/events/{items[0]["id"]}').status_code==405


def test_failed_state_write_leaves_original_state(client,monkeypatch):
    people(client);login(client,'viewer@test.vn');item=incident(client);login(client,'manager@test.vn')
    with SessionLocal() as db:collection_type=type(db.database.incidents)
    original=collection_type.find_one_and_update
    def failing_write(collection,*args,**kwargs):
        if collection.name=='incidents':raise PyMongoError('test-only storage failure')
        return original(collection,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(collection_type,'find_one_and_update',failing_write)
        response=client.post(f'/api/management/incidents/{item["id"]}/accept',json=note(item))
        assert response.status_code==503
    data=client.get(f'/api/incidents/{item["id"]}').json();assert data['status']=='pending' and len(data['history'])==1
