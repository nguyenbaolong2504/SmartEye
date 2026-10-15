from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from backend.app.database_config import resolve_database_url
from backend.app.db import Base, get_db, SessionLocal
from backend.app.demo_accounts import DEMO_ACCOUNTS, seed_demo_accounts
from backend.app.main import app
from backend.app.models import User
from backend.app.passwords import verify_password, hash_password

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / 'database'


def test_packaged_sqlite_integrity_schema_and_only_synthetic_data():
    with closing(sqlite3.connect(f'file:{(BUNDLE / "smarteye-demo.sqlite3").as_posix()}?mode=ro', uri=True)) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert names == set(Base.metadata.tables)
        accounts = db.execute('SELECT email,password,role FROM users ORDER BY id').fetchall()
        assert len(accounts) == 3
        for account, (email, encoded, role) in zip(DEMO_ACCOUNTS, accounts):
            assert (email, role) == (account['email'], account['role'])
            assert encoded != account['password']
            assert verify_password(account['password'], encoded)
        assert db.execute('SELECT count(*) FROM segments').fetchone()[0] == 13
        assert db.execute('SELECT count(*) FROM cameras').fetchone()[0] == 4
        for table in names - {'users', 'segments', 'cameras'}:
            assert db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0


def test_sqlite_sql_restore_uses_same_schema_and_passwords():
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript((BUNDLE / 'schema.sqlite.sql').read_text(encoding='utf-8'))
        db.executescript((BUNDLE / 'seed.demo.sqlite.sql').read_text(encoding='utf-8'))
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 3
        encoded = db.execute('SELECT password FROM users WHERE role="admin"').fetchone()[0]
        assert verify_password(DEMO_ACCOUNTS[0]['password'], encoded)
        assert db.execute('SELECT count(*) FROM segments').fetchone()[0] == 13


def test_seed_does_not_reset_existing_account(client):
    with SessionLocal() as db:
        created, skipped = seed_demo_accounts(db)
        assert len(created) == 3 and skipped == []
        admin = db.scalar(select(User).where(User.email == DEMO_ACCOUNTS[0]['email']))
        admin.password = hash_password('private-new-password')
        admin.role = 'user'
        admin.active = False
        db.commit()
        created, skipped = seed_demo_accounts(db)
        db.commit()
        assert created == [] and len(skipped) == 3
        assert admin.role == 'user' and not admin.active
        assert verify_password('private-new-password', admin.password)
        assert db.scalar(select(func.count()).select_from(User)) == 4


def test_all_bundled_accounts_login_with_correct_permissions(client, tmp_path):
    path = tmp_path / 'working.sqlite3'
    shutil.copyfile(BUNDLE / 'smarteye-demo.sqlite3', path)
    engine = create_engine(f'sqlite:///{path.as_posix()}', connect_args={'check_same_thread':False})
    sessions = sessionmaker(bind=engine)
    def override_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    try:
        for account in DEMO_ACCOUNTS:
            response = client.post('/api/auth/login', json={'email':account['email'],'password':account['password']})
            assert response.status_code == 200
            assert response.json()['role'] == account['role']
            assert 'password' not in response.json()
            assert client.get('/api/admin/users').status_code == (200 if account['role']=='admin' else 403)
            assert client.get('/api/reports').status_code == (403 if account['role']=='user' else 200)
            assert client.post('/api/auth/logout').status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_demo_cli_refuses_production_before_creating_database(tmp_path):
    path = tmp_path / 'production.sqlite3'
    result = subprocess.run([sys.executable, 'scripts/init_db.py', '--demo-accounts'], cwd=ROOT,
        env={**os.environ,'APP_ENV':'production','DATABASE_URL':f'sqlite:///{path.as_posix()}'},
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
    assert result.returncode != 0
    assert not path.exists()


def test_init_cli_can_run_twice_without_duplicate_accounts(tmp_path):
    path = tmp_path / 'new.sqlite3'
    environment = {**os.environ,'APP_ENV':'development','SEED_DEMO':'true','DATABASE_URL':f'sqlite:///{path.as_posix()}','ADMIN_EMAIL':'','ADMIN_PASSWORD':''}
    for _ in range(2):
        result = subprocess.run([sys.executable, 'scripts/init_db.py', '--demo-accounts'], cwd=ROOT,
            env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        assert result.returncode == 0, result.stderr
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 3
        assert db.execute('SELECT count(*) FROM segments').fetchone()[0] == 13


def test_init_does_not_import_api_or_video_packages(tmp_path):
    path = tmp_path / 'db-only.sqlite3'
    code = "import runpy,sys; sys.argv=['init_db.py','--demo-accounts']; ns=runpy.run_path('scripts/init_db.py'); assert ns['main']()==0; assert not {'torch','cv2','fastapi'} & sys.modules.keys()"
    result = subprocess.run([sys.executable,'-c',code],cwd=ROOT,
        env={**os.environ,'APP_ENV':'development','DATABASE_URL':f'sqlite:///{path.as_posix()}','ADMIN_EMAIL':'','ADMIN_PASSWORD':''},
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
    assert result.returncode == 0, result.stderr


def test_builder_does_not_export_configured_admin(monkeypatch,tmp_path):
    from scripts.build_demo_database import build
    monkeypatch.setenv('ADMIN_EMAIL','private-owner@example.invalid')
    monkeypatch.setenv('ADMIN_PASSWORD','private-password-not-for-export')
    counts = build(tmp_path)
    assert counts['users'] == 3
    for path in tmp_path.iterdir():
        data = path.read_bytes()
        assert b'private-owner@example.invalid' not in data
        assert b'private-password-not-for-export' not in data


def test_db_defaults_and_url_precedence(tmp_path):
    assert resolve_database_url({}, tmp_path).endswith('/smarteye.db')
    explicit = 'sqlite:///explicit.sqlite3'
    assert resolve_database_url({'DATABASE_URL':explicit,'DB_ENGINE':'postgresql'},tmp_path) == explicit
    assert make_url(resolve_database_url({'DATABASE_URL':'postgresql://test:pass@localhost/demo'},tmp_path)).drivername == 'postgresql+psycopg'


def test_postgres_fields_preserve_special_characters_in_password(tmp_path):
    password = 'my@password:/#%?2026'
    url = make_url(resolve_database_url({'DATABASE_URL':'','DB_ENGINE':'postgresql','POSTGRES_PASSWORD':password},tmp_path))
    assert url.drivername == 'postgresql+psycopg'
    assert url.password == password
    assert url.host == '127.0.0.1' and url.port == 5432 and url.database == 'smarteye'


@pytest.mark.parametrize('fields',[
    {'DB_ENGINE':'postgresql'},
    {'DB_ENGINE':'mysql'},
    {'DB_ENGINE':'postgresql','POSTGRES_PASSWORD':'secret','POSTGRES_PORT':'invalid'},
])
def test_invalid_connection_fields_fail_without_exposing_password(fields,tmp_path):
    with pytest.raises(ValueError) as exc:
        resolve_database_url(fields,tmp_path)
    assert 'secret' not in str(exc.value)
