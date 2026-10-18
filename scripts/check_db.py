"""Check MongoDB connectivity without printing a URI or password."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.db import get_database

if __name__=='__main__':
    try:
        database=get_database()
        database.command('ping')
        print(f'MongoDB OK. Database: {database.name}. Collections: {len(database.list_collection_names())}')
    except Exception:
        print('MongoDB is not reachable. Start MongoDB Server/Docker and check MONGODB_URI, MONGODB_DB and authentication in .env.',file=sys.stderr)
        raise SystemExit(1)
