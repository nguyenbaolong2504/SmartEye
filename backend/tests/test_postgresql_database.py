"""Opt-in restore tests on the disposable PostgreSQL database provided by CI."""
import os
from pathlib import Path
import uuid
import pytest
from sqlalchemy.engine import make_url
from backend.app.demo_accounts import DEMO_ACCOUNTS
from backend.app.passwords import verify_password

URL = os.getenv('SMARTEYE_POSTGRES_TEST_URL')


@pytest.mark.skipif(not URL, reason='Set SMARTEYE_POSTGRES_TEST_URL to a disposable *_ci database.')
def test_postgresql_schema_seed_sequences_and_foreign_keys():
    import psycopg
    url = make_url(URL)
    assert url.database and url.database.endswith('_ci'), 'Only a disposable *_ci database is allowed.'
    schema = 'smarteye_test_' + uuid.uuid4().hex
    root = Path(__file__).resolve().parents[2] / 'database'
    with psycopg.connect(host=url.host, port=url.port or 5432, dbname=url.database,
                         user=url.username, password=url.password, **dict(url.query)) as conn:
        try:
            conn.execute(f'CREATE SCHEMA "{schema}"')
            conn.execute(f'SET search_path TO "{schema}"')
            conn.commit()
            conn.execute((root / 'schema.postgresql.sql').read_text(encoding='utf-8'))
            conn.execute((root / 'seed.demo.postgresql.sql').read_text(encoding='utf-8'))
            rows = conn.execute('SELECT email,password,role FROM users ORDER BY id').fetchall()
            assert len(rows) == 3
            for account, (email, encoded, role) in zip(DEMO_ACCOUNTS, rows):
                assert (email,role) == (account['email'],account['role'])
                assert verify_password(account['password'], encoded)
            assert conn.execute('SELECT count(*) FROM segments').fetchone()[0] == 13
            geometry = conn.execute('SELECT geometry FROM segments ORDER BY id LIMIT 1').fetchone()[0]
            assert isinstance(geometry,list) and len(geometry) == 2
            ident = conn.execute("INSERT INTO users (email,name,password,role,active,created_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                ('new@smarteye.test','New account',rows[0][1],'user',True,'2026-01-01T00:00:00+00:00')).fetchone()[0]
            assert ident == 4
            conn.commit()
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute('INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (%s,%s,%s)',
                        ('invalid-fixture',999999,'2026-01-01T00:00:00+00:00'))
        finally:
            conn.rollback()
            # Drop only the random schema created by this test, not public/user data.
            assert schema.startswith('smarteye_test_') and schema[14:].isalnum()
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.commit()
