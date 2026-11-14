"""Enable the new ForecastRun target without changing records or application roles."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()
from pymongo import MongoClient
from backend.app.db import get_database,initialize_database
from backend.app.mongo_schema import SCHEMAS


def migrate():
    database=get_database()
    if database.forecast_runs.options().get('validator')==SCHEMAS['forecast_runs']:
        initialize_database();print('Traffic schema already current.');return
    root_user=os.getenv('MONGO_ROOT_USERNAME','smarteye_root');root_password=os.getenv('MONGO_ROOT_PASSWORD')
    if root_password:
        # Compose supplies private values through env_file; never echo a URI.
        client=MongoClient(host=os.getenv('MONGODB_HOST','localhost'),port=int(os.getenv('MONGODB_PORT','27017')),
            username=root_user,password=root_password,authSource='admin',serverSelectionTimeoutMS=5000)
        try:client[database.name].command('collMod','forecast_runs',validator=SCHEMAS['forecast_runs'])
        finally:client.close()
    else:database.command('collMod','forecast_runs',validator=SCHEMAS['forecast_runs'])
    initialize_database();print('Traffic schema updated; existing records preserved.')


if __name__=='__main__':migrate()
