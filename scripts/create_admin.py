"""Interactive administrator bootstrap; password is never a CLI argument."""
import getpass
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from backend.app.db import Base,engine,SessionLocal
from backend.app.models import User
from backend.app.schemas import Register
from backend.app.passwords import hash_password
from backend.app.migrations import upgrade

if __name__ == '__main__':
    email=input('Administrator email: ').strip().lower()
    password=getpass.getpass('Password (at least 10 characters): ')
    confirm=getpass.getpass('Confirm password: ')
    if password != confirm: raise SystemExit('Passwords do not match.')
    body=Register(name='Quản trị SmartEye',email=email,password=password)
    Base.metadata.create_all(engine)
    upgrade()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email==body.email)):
            raise SystemExit('Account already exists. Use an existing admin to change roles.')
        db.add(User(name=body.name,email=body.email,password=hash_password(body.password),role='admin'))
        db.commit()
    print('Administrator created. Sign in through the web interface.')
