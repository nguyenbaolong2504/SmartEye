"""Download a pretrained COCO detector once; never download during an API request."""
from pathlib import Path
import urllib.request
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from backend.app.config import MODEL_PATH


def download_model(path,variant='n'):
    if variant not in ('n','s'):raise ValueError('Unsupported detector variant')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file():return path
    temporary=path.with_suffix('.download')
    try:
        urllib.request.urlretrieve(f'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11{variant}.pt',temporary)
        temporary.replace(path)
        from ultralytics import YOLO
        model=YOLO(str(path))
        if not {'car','bus','truck'}<=set(model.names.values()):
            path.unlink();raise RuntimeError('Downloaded model does not include vehicle classes')
    finally:temporary.unlink(missing_ok=True)
    return path

if __name__ == '__main__':
    MODEL_PATH.parent.mkdir(parents=True,exist_ok=True)
    if MODEL_PATH.exists():
        print(f'Model already exists: {MODEL_PATH}')
    else:
        url='https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt'
        temporary=MODEL_PATH.with_suffix('.download')
        try:
            urllib.request.urlretrieve(url,temporary)
            from ultralytics import YOLO
            model=YOLO(str(temporary.rename(MODEL_PATH)))
            if not {'car','bus','truck'} <= set(model.names.values()):
                MODEL_PATH.unlink(); raise RuntimeError('Downloaded model does not include vehicle classes')
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        print(f'Model ready: {MODEL_PATH}')
