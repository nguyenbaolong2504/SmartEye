import os
import tempfile
from pathlib import Path
import pytest

TEST_DIR=Path(tempfile.mkdtemp(prefix='smarteye-tests-'))
os.environ['DATABASE_URL']=f'sqlite:///{(TEST_DIR/"tests.db").as_posix()}'
os.environ['SEED_DEMO']='true'
os.environ.pop('ADMIN_PASSWORD',None)
from fastapi.testclient import TestClient
from backend.app.main import app, _requests
from backend.app.db import Base, engine, SessionLocal
from backend.app.models import User
from backend.app.security import hash_password

@pytest.fixture
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); _requests.clear()
    with TestClient(app) as c:
        with SessionLocal() as db:
            db.add(User(email='admin@test.vn',name='Test Admin',role='admin',password=hash_password('test-password-only')))
            db.commit()
        yield c

@pytest.fixture
def admin_client(client):
    assert client.post('/api/auth/login',json={'email':'admin@test.vn','password':'test-password-only'}).status_code==200
    return client

@pytest.fixture
def route_request():
    return {'origin':{'node':'hoankiem','name':'Hồ Hoàn Kiếm','lat':21.0287,'lng':105.8524},'destination':{'node':'caugiay','name':'Cầu Giấy','lat':21.0333,'lng':105.7984},'provider':'demo','mode':'DRIVE','weights':{'time':.45,'distance':.2,'density':.35}}
