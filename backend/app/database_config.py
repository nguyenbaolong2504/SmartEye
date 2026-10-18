"""MongoDB-only configuration; credentials are never printed."""
import re
from urllib.parse import quote_plus


def resolve_mongodb_settings(environment):
    database = environment.get('MONGODB_DB', 'smarteye').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,63}', database) or database in ('admin','local','config'):
        raise ValueError('MONGODB_DB cần là tên DB riêng, ví dụ smarteye; không dùng admin/local/config.')
    explicit = environment.get('MONGODB_URI', '').strip()
    if explicit:
        if not explicit.startswith(('mongodb://','mongodb+srv://')):
            raise ValueError('MONGODB_URI phải bắt đầu bằng mongodb:// hoặc mongodb+srv://.')
        return explicit, database
    host = environment.get('MONGODB_HOST', '127.0.0.1').strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]+',host):
        raise ValueError('MONGODB_HOST không hợp lệ.')
    try:
        port = int(environment.get('MONGODB_PORT','27017'))
        if not 1 <= port <= 65535: raise ValueError()
    except ValueError:
        raise ValueError('MONGODB_PORT phải từ 1 đến 65535.') from None
    username = environment.get('MONGODB_USERNAME','')
    password = environment.get('MONGODB_PASSWORD','')
    if bool(username) != bool(password):
        raise ValueError('Cần khai báo đủ MONGODB_USERNAME và MONGODB_PASSWORD.')
    credentials = f'{quote_plus(username)}:{quote_plus(password)}@' if username else ''
    auth_source = environment.get('MONGODB_AUTH_SOURCE',database)
    uri = f'mongodb://{credentials}{host}:{port}/'
    if username:
        uri += f'?authSource={quote_plus(auth_source)}'
    return uri, database
