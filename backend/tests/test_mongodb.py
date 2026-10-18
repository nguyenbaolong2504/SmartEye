import json
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse,unquote_plus
import pytest
from pymongo.errors import DuplicateKeyError, OperationFailure
from backend.app.db import SessionLocal, get_database, initialize_database, now, stamp
from backend.app.models import ALL_MODELS, User, LoginSession, ResetToken, Observation, VideoJob
from backend.app.database_config import resolve_mongodb_settings
from backend.app.demo_accounts import DEMO_ACCOUNTS, seed_demo_accounts
from backend.app.passwords import hash_password, verify_password
from backend.app.security import token_hash

ROOT=Path(__file__).resolve().parents[2]


def test_mongodb_collections_and_unique_indexes(client):
    database=get_database()
    assert set(database.list_collection_names()) == {m.collection for m in ALL_MODELS}|{'counters'}
    assert database.users.index_information()['unique_email']['unique']
    assert database.observations.index_information()['one_publication_per_video']['partialFilterExpression'] == {'job_id':{'$type':'string'}}
    assert database.sessions.index_information()['expire_tokens']['expireAfterSeconds']==0


def test_multiple_manual_observations_and_single_video_publication(admin_client):
    with SessionLocal() as db:
        for _ in range(2):
            db.add(Observation(segment_id=1,user_id=1,density='LOW',score=.1,observed_at=stamp()))
        db.commit()
        db.add(Observation(segment_id=1,user_id=1,job_id='one-job',density='LOW',score=.1,observed_at=stamp()))
        db.commit()
        db.add(Observation(segment_id=1,user_id=1,job_id='one-job',density='HIGH',score=.9,observed_at=stamp()))
        with pytest.raises(DuplicateKeyError): db.commit()


def test_changed_fields_do_not_overwrite_concurrent_cancel(client):
    with SessionLocal() as db:
        db.add(VideoJob(id='race-job',user_id=1,camera_id=1,filename='test.mp4',camera_config={},status='processing'))
        db.commit()
    with SessionLocal() as first,SessionLocal() as second:
        old=first.get(VideoJob,'race-job')
        second.update(VideoJob,'race-job',{'status':'cancelled'})
        old.progress=25
        first.commit()
        assert second.get(VideoJob,'race-job').status=='cancelled'
        assert first.update(VideoJob,'race-job',{'status':'completed'},condition={'status':'processing'}) is None


def test_counter_sync_after_compass_import(client):
    get_database().users.insert_one({'_id':50,'email':'imported@smarteye.test','name':'Imported','password':hash_password('test-import-password'),'role':'user','active':True,'auth_version':0,'created_at':stamp()})
    initialize_database()
    with SessionLocal() as db:
        user=User(email='next@smarteye.test',name='Next',password=hash_password('test-import-password'))
        db.add(user);db.commit()
        assert user.id==51


def test_session_version_revokes_without_deleting_token(client):
    response=client.post('/api/auth/register',json={'name':'Version test','email':'version@smarteye.test','password':'test-version-password'})
    assert response.status_code==201
    with SessionLocal() as db:
        db.update(User,response.json()['id'],{},increment={'auth_version':1})
        assert db.count(LoginSession)==1
    assert client.get('/api/auth/me').json() is None


def test_reset_token_used_once_and_other_old_tokens_invalid(client):
    for token in ('token-a','token-b'):
        with SessionLocal() as db:
            db.add(ResetToken(token_hash=token_hash(token),user_id=1,expires_at=(now()+timedelta(minutes=20)).isoformat(),auth_version=0));db.commit()
    assert client.post('/api/auth/reset-password',json={'token':'token-a','password':'brand-new-password'}).status_code==200
    assert client.post('/api/auth/reset-password',json={'token':'token-a','password':'another-new-password'}).status_code==400
    assert client.post('/api/auth/reset-password',json={'token':'token-b','password':'another-new-password'}).status_code==400


def test_demo_accounts_idempotent_and_preserve_existing_password(client):
    with SessionLocal() as db:
        created,skipped=seed_demo_accounts(db);db.commit()
        assert len(created)==3 and not skipped
        admin=db.find_one(User,{'email':DEMO_ACCOUNTS[0]['email']})
        admin.password=hash_password('private-changed-password');admin.role='user';admin.active=False;db.commit()
        created,skipped=seed_demo_accounts(db);db.commit()
        assert not created and len(skipped)==3
        existing=db.get(User,admin.id)
        assert existing.role=='user' and not existing.active
        assert verify_password('private-changed-password',existing.password)


def test_all_mongodb_demo_accounts_login_correct_roles(client):
    with SessionLocal() as db: seed_demo_accounts(db);db.commit()
    for account in DEMO_ACCOUNTS:
        response=client.post('/api/auth/login',json={'email':account['email'],'password':account['password']})
        assert response.status_code==200 and response.json()['role']==account['role']
        assert client.get('/api/admin/users').status_code==(200 if account['role']=='admin' else 403)
        assert client.get('/api/reports').status_code==(403 if account['role']=='user' else 200)
        assert 'password' not in response.json()
        client.post('/api/auth/logout')


def test_mongodb_settings_defaults_and_special_password():
    assert resolve_mongodb_settings({})==('mongodb://127.0.0.1:27017/','smarteye')
    password='a@b:/?#$2026'
    uri,name=resolve_mongodb_settings({'MONGODB_USERNAME':'smarteye','MONGODB_PASSWORD':password})
    assert unquote_plus(urlparse(uri).password)==password and name=='smarteye'
    assert 'authSource=smarteye' in uri
    assert resolve_mongodb_settings({'MONGODB_URI':'mongodb+srv://test:test@cluster.example.net/','MONGODB_DB':'app'})[1]=='app'


@pytest.mark.parametrize('values',[{'MONGODB_DB':'admin'},{'MONGODB_DB':'bad/name'},{'MONGODB_URI':'sqlite:///old.db'},{'MONGODB_USERNAME':'user'},{'MONGODB_PORT':'abc'}])
def test_invalid_mongodb_settings(values):
    with pytest.raises(ValueError): resolve_mongodb_settings(values)


def test_json_bundle_contains_only_public_synthetic_accounts(monkeypatch,tmp_path):
    from scripts.build_demo_database import build
    monkeypatch.setenv('ADMIN_EMAIL','private@example.invalid')
    monkeypatch.setenv('ADMIN_PASSWORD','not-for-export-password')
    counts=build(tmp_path)
    assert counts['users']==3 and counts['segments']==13 and counts['cameras']==4
    accounts=json.loads((tmp_path/'users.json').read_text(encoding='utf-8'))
    for account,row in zip(DEMO_ACCOUNTS,accounts):
        assert row['email']==account['email'] and verify_password(account['password'],row['password'])
    for path in tmp_path.iterdir():
        assert b'private@example.invalid' not in path.read_bytes()
        assert b'not-for-export-password' not in path.read_bytes()


def test_setup_preserves_api_keys_and_existing_docker_password(tmp_path):
    from scripts.setup_env import configure
    from dotenv import dotenv_values
    (tmp_path/'.env.example').write_text('MONGODB_DB=smarteye\n',encoding='utf-8')
    (tmp_path/'.env').write_text("GOOGLE_ROUTES_API_KEY='private-test-key'\nMONGODB_PASSWORD='keep-test-password'\nDATABASE_URL='sqlite:///old.db'\n",encoding='utf-8')
    configure('docker',tmp_path)
    values=dotenv_values(tmp_path/'.env')
    assert values['GOOGLE_ROUTES_API_KEY']=='private-test-key'
    assert values['MONGODB_PASSWORD']=='keep-test-password'
    assert values['MONGO_ROOT_PASSWORD']
    assert 'DATABASE_URL' not in values
    assert len(list(tmp_path.glob('.env.backup-*')))==1
    configure('local',tmp_path)
    assert dotenv_values(tmp_path/'.env')['MONGODB_URI']=='mongodb://127.0.0.1:27017/'
    configure('docker',tmp_path)
    assert dotenv_values(tmp_path/'.env')['MONGODB_PASSWORD']=='keep-test-password'


def test_restore_compass_fixture_and_register_next_id(client):
    database=get_database()
    # Test fixture owns this isolated DB; emulate Compass restore into empty collections.
    for model in ALL_MODELS:
        database[model.collection].delete_many({})
        documents=json.loads((ROOT/'database/mongodb'/f'{model.collection}.json').read_text(encoding='utf-8'))
        if documents: database[model.collection].insert_many(documents)
    initialize_database()
    for account in DEMO_ACCOUNTS:
        response=client.post('/api/auth/login',json={'email':account['email'],'password':account['password']})
        assert response.status_code==200 and response.json()['role']==account['role']
        client.post('/api/auth/logout')
    response=client.post('/api/auth/register',json={'name':'After import','email':'after-import@example.invalid','password':'after-import-password'})
    assert response.status_code==201 and response.json()['id']==4


@pytest.mark.skipif(not os.getenv('SMARTEYE_TEST_MONGODB_URI'),reason='Requires a real MongoDB server to enforce JSONSchema.')
def test_real_mongodb_rejects_invalid_density(client):
    with pytest.raises(OperationFailure):
        get_database().observations.insert_one({'_id':999,'segment_id':1,'user_id':1,'density':'INVALID','score':.5,'observed_at':stamp(),'source':'manual'})
