import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2
import numpy as np
from .config import MODEL_PATH, UPLOADS, MAX_VIDEO_SECONDS
from .db import SessionLocal
from .models import VideoJob
from .traffic import classify

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='smarteye-video')
_model = None
_lock = threading.Lock()

def get_model():
    global _model
    if not MODEL_PATH.is_file():
        raise RuntimeError('Chưa có trọng số YOLO. Quản trị viên cần chạy python scripts/download_model.py.')
    if _model is None:
        from ultralytics import YOLO
        _model = YOLO(str(MODEL_PATH))
    return _model

def summarize_boxes(boxes, roi, capacity, width, height):
    # Union of clipped boxes; overlapping detections do not double-count occupancy.
    x1,y1,x2,y2 = roi
    mask = np.zeros((256,256),np.uint8)
    accepted = []
    for box in boxes:
        a,b,c,d = box['box']
        cx,cy = (a+c)/2/width,(b+d)/2/height
        if not x1 <= cx <= x2 or not y1 <= cy <= y2:
            continue
        a,b,c,d = max(a/width,x1),max(b/height,y1),min(c/width,x2),min(d/height,y2)
        px1,py1,px2,py2 = [max(0,min(256,round(v*256))) for v in (a,b,c,d)]
        mask[py1:py2,px1:px2] = 1
        accepted.append(box)
    rx1,ry1,rx2,ry2 = [round(v*256) for v in roi]
    area = max(1,(rx2-rx1)*(ry2-ry1))
    occupancy = min(1,float(mask.sum())/area)
    score = min(1,max(occupancy,len(accepted)/capacity))
    return accepted, occupancy, score

def analyze(job_id):
    cap = None
    try:
        with SessionLocal() as db:
            job = db.get(VideoJob,job_id)
            if not job or job.status == 'cancelled': return
            if not db.update(VideoJob,job_id,{'status':'processing'},condition={'status':'queued'}): return
            config = job.camera_config
            db.commit()
        model = get_model()
        cap = cv2.VideoCapture(str(UPLOADS / f'{job_id}.video'))
        fps, frames = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or fps <= 0 or frames <= 0:
            raise ValueError('Video không đọc được hoặc codec không được hỗ trợ. Hãy dùng MP4 H.264.')
        duration = frames/fps
        if duration > MAX_VIDEO_SECONDS:
            raise ValueError(f'Video vượt quá giới hạn {MAX_VIDEO_SECONDS} giây. Vui lòng cắt một đoạn ngắn.')
        samples = []
        target_count = max(1,int(np.ceil(duration)))
        for index in range(target_count):
            with SessionLocal() as db:
                job = db.get(VideoJob,job_id)
                if not job or job.status == 'cancelled': return
            cap.set(cv2.CAP_PROP_POS_MSEC,index*1000)
            ok,frame = cap.read()
            if not ok: break
            original_h,original_w = frame.shape[:2]
            if original_w > 1280:
                frame = cv2.resize(frame,(1280,round(original_h*1280/original_w)))
            h,w = frame.shape[:2]
            with _lock:
                prediction = model.predict(frame,conf=.3,imgsz=640,verbose=False)[0]
            boxes = []
            for box in prediction.boxes:
                cls = int(box.cls[0])
                label = prediction.names[cls]
                if label not in ('car','motorcycle','motorbike','bus','truck'): continue
                boxes.append({'box':[round(float(v),1) for v in box.xyxy[0]],'label':label,'confidence':round(float(box.conf[0]),3)})
            accepted, occupancy, score = summarize_boxes(boxes,config['roi'],config['capacity'],w,h)
            sample = {'second':index,'count':len(accepted),'occupancy':round(occupancy,4),'score':round(score,4),'density':classify(score,config['low_threshold'],config['high_threshold']),'boxes':accepted,'width':w,'height':h}
            samples.append(sample)
            if index == 0 or index % 10 == 0:
                for box in accepted:
                    a,b,c,d = [int(v) for v in box['box']]
                    cv2.rectangle(frame,(a,b),(c,d),(75,207,150),2)
                r = config['roi']; cv2.rectangle(frame,(int(r[0]*w),int(r[1]*h)),(int(r[2]*w),int(r[3]*h)),(255,170,40),2)
                cv2.imwrite(str(UPLOADS / f'{job_id}-{index}.jpg'),frame)
            with SessionLocal() as db:
                job = db.get(VideoJob,job_id)
                if not job or job.status == 'cancelled': return
                db.update(VideoJob,job_id,{'progress':min(99,round((index+1)/target_count*100))},condition={'status':'processing'})
        if not samples: raise ValueError('Video không có khung hình hợp lệ.')
        score = float(np.median([s['score'] for s in samples]))
        distribution = {k:sum(s['density']==k for s in samples) for k in ('LOW','NORMAL','HIGH')}
        result = {'samples':samples,'density':classify(score,config['low_threshold'],config['high_threshold']),'score':round(score,4),'average_count':round(float(np.mean([s['count'] for s in samples])),1),'peak_count':max(s['count'] for s in samples),'duration_seconds':round(duration,1),'distribution':distribution,'model':MODEL_PATH.name,'sample_rate':1,'note':'Mật độ được phân loại theo ngưỡng camera, không phải xác suất ùn tắc hay tốc độ xe.'}
        with SessionLocal() as db:
            job = db.get(VideoJob,job_id)
            if job and job.status != 'cancelled':
                db.update(VideoJob,job_id,{'result':result,'status':'completed','progress':100},condition={'status':'processing'})
    except Exception as exc:
        logger.exception('Video analysis failed: %s',job_id)
        with SessionLocal() as db:
            job = db.get(VideoJob,job_id)
            if job and job.status != 'cancelled':
                message = str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Không xử lý được video. Kiểm tra trọng số YOLO, codec và bộ nhớ máy chủ.'
                db.update(VideoJob,job_id,{'status':'failed','error':message},condition={'status':{'$in':['queued','processing']}})
    finally:
        if cap: cap.release()
        (UPLOADS / f'{job_id}.video').unlink(missing_ok=True)

def submit(job_id):
    return executor.submit(analyze,job_id)
