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
_accurate_model=None


class Cancelled(Exception):pass


def counts_for(boxes):
    counts=Counter('motorcycle' if box['label']=='motorbike' else box['label'] for box in boxes)
    return {label:counts[label] for label in VEHICLES}


def detect_clip(path,config,checkpoint):
    from .video import get_model,_lock,summarize_boxes
    weights=MODEL_PATH.with_name('yolo11s.pt') if config.get('detector_model')=='yolo11s' else MODEL_PATH
    signature={'version':VERSION,'video':hashlib.sha256(path.read_bytes()).hexdigest(),
        'weights':hashlib.sha256(weights.read_bytes()).hexdigest(),'roi':config['roi'],'parameters':PARAMETERS,'camera_motion_version':1}
    if config.get('detect_full_frame'):signature['detect_full_frame']=True
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
            if weights!=MODEL_PATH:
                global _accurate_model
                if _accurate_model is None:
                    from ultralytics import YOLO
                    _accurate_model=YOLO(str(weights))
                model=_accurate_model
            else:model=get_model()
            frames=[];previous_gray=None
            for index in range(length):
                ok,frame=cap.read()
                if not ok:raise ValueError('Video bị thiếu khung hình. Cần chuẩn bị lại video.')
                h,w=frame.shape[:2]
                gray=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(320,180)).astype(np.float32)
                shift=[0.,0.]
                if previous_gray is not None:
                    (dx,dy),response=cv2.phaseCorrelate(previous_gray,gray)
                    if response>.2 and abs(dx)<8 and abs(dy)<8:shift=[round(dx*w/320,4),round(dy*h/180,4)]
                previous_gray=gray
                x1,y1,x2,y2=[round(value*size) for value,size in zip(config['roi'],(w,h,w,h))]
                if x2-x1<2 or y2-y1<2:raise ValueError('Vùng quan sát camera quá nhỏ.')
                with _lock:
                    full=config.get('detect_full_frame',False)
                    prediction=model.predict(frame if full else frame[y1:y2,x1:x2],verbose=False,**PARAMETERS)[0]
                offset_x,offset_y=(0,0) if full else (x1,y1)
                boxes=[]
                for box in prediction.boxes:
                    label=prediction.names[int(box.cls[0])]
                    if label not in (*VEHICLES,'motorbike'):continue
                    a,b,c,d=[float(v) for v in box.xyxy[0]]
                    boxes.append({'box':[round(a+offset_x,1),round(b+offset_y,1),round(c+offset_x,1),round(d+offset_y,1)],
                        'label':'motorcycle' if label=='motorbike' else label,'confidence':round(float(box.conf[0]),3)})
                frames.append({'frame_index':index,'second':round(index/fps,6),'boxes':boxes,'width':w,'height':h,'camera_shift':shift})
                if index%8==0:checkpoint(min(90,round((index+1)/length*90)))
            raw={'frames':frames,'fps':fps,'duration_seconds':length/fps,'signature':signature}
            FOLDER.mkdir(parents=True,exist_ok=True)
            pending=cached.with_suffix(f'.{uuid.uuid4().hex}.pending')
            try:
                pending.write_text(json.dumps(raw,separators=(',',':')),encoding='utf-8');pending.replace(cached)
            finally:pending.unlink(missing_ok=True)
        finally:cap.release()
    output=[]
    from .road_capacity import frame_load,geometry,motion_evidence,VERSION as CAPACITY_VERSION
    for frame in raw['frames']:
        boxes,occupancy,score=summarize_boxes(frame['boxes'],config['roi'],config['capacity'],frame['width'],frame['height'])
        counts=counts_for(boxes)
        load=frame_load(counts,config)
        if load:score=min(1.,load['load_ratio'])
        output.append({**frame,'boxes':boxes,'vehicle_counts':counts,'count':sum(counts.values()),
            'occupancy':round(occupancy,4),'score':round(score,4),
            'density':classify(score,config['low_threshold'],config['high_threshold']),**load})
    if not output:raise ValueError('Chưa có khung hình hợp lệ.')
    from .camera_counting import cumulative_tracks,VERSION as COUNTING_VERSION
    output=cumulative_tracks(output,raw['fps'])
    output=motion_evidence(output)
    from .camera_measurements import measurement_frames
    output,measurements=measurement_frames(output,config,raw['fps'])
    # Keep one sample per second for existing archive APIs; the viewer uses all frames.
    samples=[];last_second=-1
    for frame in output:
        second=int(frame['second']+1e-5)
        if second!=last_second:samples.append({**frame,'second':second});last_second=second
    score=float(np.median([frame['score'] for frame in output]))
    return {'detection_version':VERSION,'frames':output,'samples':samples,'fps':raw['fps'],
        'capacity_version':CAPACITY_VERSION,'road_geometry':geometry(config),
        'measurement_version':measurements['version'],'measurements':measurements,
        'counting_version':COUNTING_VERSION,'counting_method':'ByteTrack',
        'total_unique_count':output[-1]['cumulative_count'],
        'total_unique_vehicle_counts':output[-1]['cumulative_vehicle_counts'],
        'sample_rate':raw['fps'],'duration_seconds':round(raw['duration_seconds'],6),
        'average_count':round(float(np.mean([frame['count'] for frame in output])),1),
        'peak_count':max(frame['count'] for frame in output),'score':round(score,4),
        'density':classify(score,config['low_threshold'],config['high_threshold']),
        'distribution':{label:sum(frame['density']==label for frame in output) for label in ('LOW','NORMAL','HIGH')},
        'model':weights.name,'parameters':PARAMETERS,'roi':config['roi'],
        'note':'Đang xuất hiện là số ô trong khung hình; cộng dồn là số mã xe đã được ByteTrack xác nhận từ đầu clip, không cộng lại từng khung hình. Mất dấu có thể làm đổi mã.'}


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
