"""Resolve either a full database URL or beginner-friendly PostgreSQL fields."""
from pathlib import Path
from sqlalchemy.engine import make_url, URL


def resolve_database_url(environment, data_directory: Path):
    explicit = environment.get('DATABASE_URL', '').strip()
    if explicit:
        url = make_url(explicit)
        if url.drivername in ('postgres', 'postgresql'):
            url = url.set(drivername='postgresql+psycopg')
        return url.render_as_string(hide_password=False)
    kind = environment.get('DB_ENGINE', 'sqlite').strip().lower()
    if kind == 'sqlite':
        return f'sqlite:///{(data_directory / "smarteye.db").as_posix()}'
    if kind not in ('postgresql', 'postgres'):
        raise ValueError('DB_ENGINE phải là sqlite hoặc postgresql.')
    password = environment.get('POSTGRES_PASSWORD', '')
    if not password:
        raise ValueError('Cần đặt POSTGRES_PASSWORD cho kết nối PostgreSQL.')
    try:
        port = int(environment.get('POSTGRES_PORT', '5432'))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        raise ValueError('POSTGRES_PORT phải là số từ 1 đến 65535.') from None
    return URL.create(
        'postgresql+psycopg',
        username=environment.get('POSTGRES_USER', 'smarteye'),
        password=password,
        host=environment.get('POSTGRES_HOST', '127.0.0.1'),
        port=port,
        database=environment.get('POSTGRES_DB', 'smarteye'),
    ).render_as_string(hide_password=False)
