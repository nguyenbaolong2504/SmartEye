import os
import uuid
import pytest

os.environ['MONGODB_DB']='smarteye_test_suite'
os.environ['SEED_DEMO']='true'
os.environ['APP_ENV']='development'
os.environ['COOKIE_SECURE']='false'
os.environ['ADMIN_EMAIL']=''
os.environ['ADMIN_PASSWORD']=''

from fastapi.testclient import TestClient
from backend.app.main import app, _requests
from backend.app import db as storage
from backend.app.db import SessionLocal
from backend.app.models import ALL_MODELS, User
from backend.app.passwords import hash_password


@pytest.fixture
def client(monkeypatch):
    live_uri=os.getenv('SMARTEYE_TEST_MONGODB_URI')
    if live_uri:
        from pymongo import MongoClient
        mongo=MongoClient(live_uri,serverSelectionTimeoutMS=5000,tz_aware=True)
        mongo.admin.command('ping')
    else:
        import mongomock
        mongo=mongomock.MongoClient(tz_aware=True)
    name='smarteye_test_'+uuid.uuid4().hex
    monkeypatch.setattr(storage,'_client',mongo)
    monkeypatch.setattr(storage,'MONGODB_DB',name)
    if not live_uri:
        # Mock cannot enforce server JSONSchema. Live CI tests create validators.
        for model in ALL_MODELS: mongo[name].create_collection(model.collection)
        mongo[name].create_collection('counters')
    _requests.clear()
    try:
        with TestClient(app) as c:
            with SessionLocal() as db:
                db.add(User(email='admin@test.vn',name='Test Admin',role='admin',password=hash_password('test-password-only')))
                db.commit()
            yield c
    finally:
        assert name.startswith('smarteye_test_') and name[14:].isalnum()
        mongo.drop_database(name)
        mongo.close()


@pytest.fixture
def admin_client(client):
    assert client.post('/api/auth/login',json={'email':'admin@test.vn','password':'test-password-only'}).status_code==200
    return client


@pytest.fixture
def route_request():
    return {'origin':{'node':'hoankiem','name':'Hồ Hoàn Kiếm','lat':21.0287,'lng':105.8524},'destination':{'node':'caugiay','name':'Cầu Giấy','lat':21.0333,'lng':105.7984},'provider':'demo','mode':'DRIVE','weights':{'time':.45,'distance':.2,'density':.35}}
