"""Create schema/seed data for DATABASE_URL without loading the video backend."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from backend.app.config import PRODUCTION
from backend.app.db import Base, engine, SessionLocal
from backend.app import models  # Register the complete schema.
from backend.app.migrations import upgrade
from backend.app.seed import seed
from backend.app.demo_accounts import seed_demo_accounts


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Khởi tạo 11 bảng SmartEye cho database trong .env.')
    parser.add_argument('--demo-accounts', action='store_true', help='Thêm 3 tài khoản công khai chỉ dành cho demo local.')
    args = parser.parse_args()
    if args.demo_accounts and PRODUCTION:
        parser.error('Không tạo tài khoản demo khi APP_ENV=production. Dùng scripts/create_admin.py.')
    try:
        Base.metadata.create_all(engine)
        upgrade()
        with SessionLocal() as db:
            seed(db)
            if args.demo_accounts:
                created, skipped = seed_demo_accounts(db)
                db.commit()
                print(f'Tài khoản demo: đã tạo {len(created)}, đã tồn tại {len(skipped)}. Không đổi tài khoản cũ.')
        tables = inspect(engine).get_table_names()
        print(f'Database: {engine.dialect.name}. Đã sẵn sàng {len(tables)} bảng:')
        print(', '.join(tables))
    except Exception:
        # Connection failures may include URLs/credentials. Show a safe explanation.
        print('Không khởi tạo được database. Kiểm tra dịch vụ, tên DB, quyền user, mật khẩu và dung lượng ổ đĩa.', file=sys.stderr)
        return 1
    if args.demo_accounts:
        print('Thông tin đăng nhập demo: database/README.md. Không dùng các tài khoản công khai này để triển khai thật.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
