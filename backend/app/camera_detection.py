"""Frame-aligned detections for camera clips; counts and boxes share one result."""
import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
import cv2
import numpy as np
from .config import DATA,MODEL_PATH,UPLOADS
from .db import SessionLocal
from .models import VideoJob
from .traffic import classify

VERSION=2
VEHICLES=('car','motorcycle','bus','truck')
PARAMETERS={'imgsz':960,'conf':.25,'iou':.5,'classes':[2,3,5,7],'agnostic_nms':True,'max_det':120}
FOLDER=DATA/'camera-detections'


class Cancelled(Exception):pass


def counts_for(boxes):
    counts=Counter('motorcycle' if box['label']=='motorbike' else box['label'] for box in boxes)
    return {label:counts[label] for label in VEHICLES}


def detect_clip(path,config,checkpoint):
    from .video import get_model,_lock,summarize_boxes
    signature={'version':VERSION,'video':hashlib.sha256(path.read_bytes()).hexdigest(),
        'weights':hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),'roi':config['roi'],'parameters':PARAMETERS}
    key=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    cached=FOLDER/f'{key}.json'
    if cached.is_file():
        checkpoint(90)
        raw=json.loads(cached.read_text(encoding='utf-8'))
    else:
        cap=cv2.VideoCapture(str(path))
        try:
            fps=cap.get(cv2.CAP_PROP_FPS);length=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if not cap.isOpened() or fps<=0 or length<=0:raise ValueError('Không đọc được video camera.')
            if length>1800 or length/fps>120:raise ValueError('Video nhận diện cần dài tối đa 120 giây và không quá 1800 khung hình.')
            model=get_model();frames=[]
            for index in range(length):
                ok,frame=cap.read()
                if not ok:raise ValueError('Video bị thiếu khung hình. Cần chuẩn bị lại video.')
                h,w=frame.shape[:2]
                x1,y1,x2,y2=[round(value*size) for value,size in zip(config['roi'],(w,h,w,h))]
                if x2-x1<2 or y2-y1<2:raise ValueError('Vùng quan sát camera quá nhỏ.')
                with _lock:
                    prediction=model.predict(frame[y1:y2,x1:x2],verbose=False,**PARAMETERS)[0]
                boxes=[]
                for box in prediction.boxes:
                    label=prediction.names[int(box.cls[0])]
                    if label not in (*VEHICLES,'motorbike'):continue
                    a,b,c,d=[float(v) for v in box.xyxy[0]]
                    boxes.append({'box':[round(a+x1,1),round(b+y1,1),round(c+x1,1),round(d+y1,1)],
                        'label':'motorcycle' if label=='motorbike' else label,'confidence':round(float(box.conf[0]),3)})
                frames.append({'frame_index':index,'second':round(index/fps,6),'boxes':boxes,'width':w,'height':h})
                if index%8==0:checkpoint(min(90,round((index+1)/length*90)))
            raw={'frames':frames,'fps':fps,'duration_seconds':length/fps,'signature':signature}
            FOLDER.mkdir(parents=True,exist_ok=True)
            pending=cached.with_suffix(f'.{uuid.uuid4().hex}.pending')
            try:
                pending.write_text(json.dumps(raw,separators=(',',':')),encoding='utf-8');pending.replace(cached)
            finally:pending.unlink(missing_ok=True)
        finally:cap.release()
    output=[]
    for frame in raw['frames']:
        boxes,occupancy,score=summarize_boxes(frame['boxes'],config['roi'],config['capacity'],frame['width'],frame['height'])
        counts=counts_for(boxes)
        output.append({**frame,'boxes':boxes,'vehicle_counts':counts,'count':sum(counts.values()),
            'occupancy':round(occupancy,4),'score':round(score,4),
            'density':classify(score,config['low_threshold'],config['high_threshold'])})
    if not output:raise ValueError('Chưa có khung hình hợp lệ.')
    # Keep one sample per second for existing archive APIs; the viewer uses all frames.
    samples=[];last_second=-1
    for frame in output:
        second=int(frame['second']+1e-5)
        if second!=last_second:samples.append({**frame,'second':second});last_second=second
    score=float(np.median([frame['score'] for frame in output]))
    return {'detection_version':VERSION,'frames':output,'samples':samples,'fps':raw['fps'],
        'sample_rate':raw['fps'],'duration_seconds':round(raw['duration_seconds'],6),
        'average_count':round(float(np.mean([frame['count'] for frame in output])),1),
        'peak_count':max(frame['count'] for frame in output),'score':round(score,4),
        'density':classify(score,config['low_threshold'],config['high_threshold']),
        'distribution':{label:sum(frame['density']==label for frame in output) for label in ('LOW','NORMAL','HIGH')},
        'model':MODEL_PATH.name,'parameters':PARAMETERS,'roi':config['roi'],
        'note':'Số xe trong từng khung hình bằng số ô nhận diện trong vùng quan sát; không phải số xe duy nhất qua đường.'}


def analyze_camera(ident):
    from .video import logger
    path=UPLOADS/f'{ident}.video';completed=False;started=False
    try:
        with SessionLocal() as db:
            job=db.get(VideoJob,ident)
            if not job or not db.update(VideoJob,ident,{'status':'processing'},condition={'status':'queued'}):return False
            started=True
            config=job.camera_config
        def checkpoint(progress):
            with SessionLocal() as db:
                job=db.get(VideoJob,ident)
                if not job or job.status!='processing':raise Cancelled()
                db.update(VideoJob,ident,{'progress':progress},condition={'status':'processing'})
        result=detect_clip(path,config,checkpoint)
        cap=cv2.VideoCapture(str(path))
        try:
            ok,frame=cap.read()
            if not ok:raise ValueError('Không đọc được ảnh xem trước.')
            for box in result['frames'][0]['boxes']:
                a,b,c,d=map(round,box['box']);cv2.rectangle(frame,(a,b),(c,d),(75,207,150),2)
                cv2.putText(frame,box['label'],(a,max(14,b-4)),cv2.FONT_HERSHEY_SIMPLEX,.4,(75,207,150),1)
            if not cv2.imwrite(str(UPLOADS/f'{ident}-0.jpg'),frame):raise ValueError('Không lưu được ảnh nhận diện.')
        finally:cap.release()
        checkpoint(95)
        with SessionLocal() as db:
            job=db.get(VideoJob,ident)
            if not job or job.status!='processing':raise Cancelled()
            path.replace(UPLOADS/f'{ident}.retained')
            completed=bool(db.update(VideoJob,ident,{'status':'completed','progress':100,'result':result},condition={'status':'processing'}))
    except Cancelled:pass
    except Exception as error:
        logger.exception('Camera frame detection failed for %s',ident)
        with SessionLocal() as db:
            message=str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Không phân tích được video. Vui lòng kiểm tra mô hình và bộ nhớ.'
            db.update(VideoJob,ident,{'status':'failed','error':message},condition={'status':{'$in':['queued','processing']}})
    finally:
        if started:
            path.unlink(missing_ok=True)
            if not completed:(UPLOADS/f'{ident}.retained').unlink(missing_ok=True)
    return completed
