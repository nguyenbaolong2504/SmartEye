"""Create MongoDB collections/indexes/seed without loading the video backend."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import PRODUCTION
from backend.app.db import initialize_database, get_database, SessionLocal
from backend.app.models import ALL_MODELS
from backend.app.seed import seed
from backend.app.demo_accounts import seed_demo_accounts


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Khởi tạo MongoDB SmartEye và các index từ cấu hình .env.')
    parser.add_argument('--demo-accounts', action='store_true', help='Thêm 3 tài khoản công khai chỉ dành cho demo local.')
    args = parser.parse_args()
    if args.demo_accounts and PRODUCTION:
        parser.error('Không tạo tài khoản demo khi APP_ENV=production. Dùng scripts/create_admin.py.')
    try:
        initialize_database()
        with SessionLocal() as db:
            seed(db)
            if args.demo_accounts:
                created, skipped = seed_demo_accounts(db)
                db.commit()
                print(f'Tài khoản demo: đã tạo {len(created)}, đã tồn tại {len(skipped)}. Không đổi tài khoản cũ.')
        names = [model.collection for model in ALL_MODELS]
        print(f'MongoDB: {get_database().name}. Đã sẵn sàng {len(names)} collection nghiệp vụ + counters:')
        print(', '.join(names))
    except Exception:
        # Connection failures may include URLs/credentials. Show a safe explanation.
        print('Không kết nối/khởi tạo được MongoDB. Kiểm tra MongoDB Server hoặc Docker, MONGODB_URI, MONGODB_DB và thông tin xác thực. Compass không thay thế MongoDB Server.', file=sys.stderr)
        return 1
    if args.demo_accounts:
        print('Thông tin đăng nhập demo: database/README.md. Không dùng các tài khoản công khai này để triển khai thật.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
