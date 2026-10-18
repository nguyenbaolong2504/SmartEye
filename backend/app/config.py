import os
from pathlib import Path
from dotenv import load_dotenv
from .database_config import resolve_mongodb_settings

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATA = ROOT / 'backend' / 'data'
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS = DATA / 'uploads'
UPLOADS.mkdir(exist_ok=True)
MONGODB_URI, MONGODB_DB = resolve_mongodb_settings(os.environ)
PRODUCTION = os.getenv('APP_ENV', 'development') == 'production'
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'true' if PRODUCTION else 'false').lower() == 'true'
SEED_DEMO = os.getenv('SEED_DEMO', 'true').lower() == 'true'
TTL_MINUTES = int(os.getenv('OBSERVATION_TTL_MINUTES', '15'))
MAX_UPLOAD = int(os.getenv('MAX_UPLOAD_MB', '150')) * 1024 * 1024
MAX_VIDEO_SECONDS = int(os.getenv('MAX_VIDEO_SECONDS', '300'))
MODEL_PATH = Path(os.getenv('YOLO_MODEL_PATH', str(DATA / 'models' / 'yolo11n.pt')))
if not MODEL_PATH.is_absolute():
    MODEL_PATH = ROOT / MODEL_PATH
