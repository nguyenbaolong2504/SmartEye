"""Run real YOLO on a frozen video made from an input image; no network downloads."""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
from sqlalchemy import select
from backend.app.db import Base,engine,SessionLocal
from backend.app.models import VideoJob,Camera,User
from backend.app.seed import seed
from backend.app.security import hash_password
from backend.app.config import UPLOADS
from backend.app.video import analyze
from backend.app.migrations import upgrade

if __name__ == '__main__':
    if len(sys.argv)!=2: raise SystemExit('Usage: python scripts/smoke_video.py /path/to/vehicle-image.jpg')
    image=cv2.imread(sys.argv[1])
    if image is None: raise SystemExit('Cannot read fixture image')
    Base.metadata.create_all(engine)
    upgrade()
    with SessionLocal() as db:
        seed(db)
        user=db.scalar(select(User).where(User.email=='smoke-fixture@example.invalid'))
        if not user:
            user=User(name='Video smoke fixture',email='smoke-fixture@example.invalid',password=hash_password(uuid.uuid4().hex),role='user');db.add(user);db.flush()
        camera=db.scalar(select(Camera).where(Camera.active.is_(True)).limit(1))
        if not camera: raise SystemExit('At least one camera is required')
        ident=str(uuid.uuid4())
        config={k:getattr(camera,k) for k in ('segment_id','capacity','low_threshold','high_threshold','roi')}
        db.add(VideoJob(id=ident,user_id=user.id,camera_id=camera.id,filename='stationary-fixture.avi',camera_config=config));db.commit()
    h,w=image.shape[:2]
    # Encode as AVI, then rename to the same opaque extension used by uploads.
    temp=UPLOADS/f'{ident}.avi'
    writer=cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*'MJPG'),10,(w,h))
    if not writer.isOpened(): raise SystemExit('Cannot create test video')
    for _ in range(20): writer.write(image)
    writer.release()
    temp.replace(UPLOADS/f'{ident}.video')
    analyze(ident)
    with SessionLocal() as db:
        job=db.get(VideoJob,ident)
        if job.status!='completed': raise SystemExit(job.error)
        result=job.result
        assert len(result['samples'])==2
        assert all(s['count']>0 for s in result['samples']), 'Expected stationary vehicles in both frames'
        assert not (UPLOADS/f'{ident}.video').exists(), 'Raw video must be deleted'
        print(json.dumps({'status':job.status,'samples':len(result['samples']),'counts':[s['count'] for s in result['samples']],'density':result['density'],'model':result['model'],'raw_video_deleted':True},ensure_ascii=False))
