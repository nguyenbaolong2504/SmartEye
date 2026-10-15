"""Public local-demo credentials; never automatically seeded by API startup."""
from sqlalchemy import select
from .models import User
from .passwords import hash_password

DEMO_ACCOUNTS = (
    {'name': 'Admin Demo', 'email': 'admin@smarteye.test', 'password': 'SmartEyeAdmin@2026', 'role': 'admin'},
    {'name': 'Analyst Demo', 'email': 'analyst@smarteye.test', 'password': 'SmartEyeAnalyst@2026', 'role': 'analyst'},
    {'name': 'User Demo', 'email': 'user@smarteye.test', 'password': 'SmartEyeUser@2026', 'role': 'user'},
)


def seed_demo_accounts(db):
    created, skipped = [], []
    for account in DEMO_ACCOUNTS:
        if db.scalar(select(User.id).where(User.email == account['email'])):
            skipped.append(account['email'])
            continue
        db.add(User(**{k:v for k,v in account.items() if k != 'password'}, password=hash_password(account['password'])))
        created.append(account['email'])
    db.flush()
    return created, skipped
