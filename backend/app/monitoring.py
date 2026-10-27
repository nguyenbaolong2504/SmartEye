"""Shared camera media and historical samples require explicit publication."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError
from .config import DATA, UPLOADS, TTL_MINUTES
from .db import get_db, now, stamp
from .models import Camera, Segment, VideoJob, Observation, TrafficSample
from .security import operator, require_user, audit
from .schemas import PublishOptions
from .history import history_report, parse_timestamp
from .traffic import emit_alerts, observation_dict

router = APIRouter()
PREVIEWS = DATA/'camera_previews'
MIME = {'.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime','.avi':'video/x-msvideo','.mkv':'video/x-matroska'}


def media_folder(camera_id, job_id):
    # Both path components originate from application IDs, never user filenames.
    safe_job = str(uuid.UUID(job_id))
    return PREVIEWS/str(int(camera_id))/safe_job


def append_video_samples(db, job, observation):
    start = parse_timestamp(job.observed_at)
    documents = []
    for sample in job.result.get('samples',[]):
        second = int(sample['second'])
        counts = Counter(box['label'] for box in sample.get('boxes',[]))
        if 'motorbike' in counts: counts['motorcycle'] += counts.pop('motorbike')
        row = TrafficSample(sample_key=f'video:{job.id}:{second}',segment_id=observation.segment_id,
            camera_id=job.camera_id,observation_id=observation.id,job_id=job.id,
            observed_at=(start+timedelta(seconds=second)).isoformat(),score=sample['score'],
            density=sample['density'],count=sample['count'],source='yolo',
            occupancy=sample.get('occupancy'),vehicle_counts={label:counts.get(label,0) for label in ('car','motorcycle','bus','truck')})
        documents.append(row.values())
    if not documents: return
    counter = db.database.counters.find_one_and_update({'_id':'traffic_samples'},
        {'$inc':{'seq':len(documents)}},upsert=True,return_document=ReturnDocument.AFTER)
    for index,document in enumerate(documents):
        document.pop('id',None)
        document['_id'] = counter['seq']-len(documents)+index+1
    try:
        db.database.traffic_samples.insert_many(documents,ordered=False)
    except BulkWriteError as exc:
        # Safe retry after a partial write; never hide non-duplicate DB failures.
        if exc.details.get('writeConcernErrors') or any(e['code']!=11000 for e in exc.details.get('writeErrors',[])): raise


def share_media(db, camera, job, share):
    if not share:
        if camera.preview_job_id == job.id:
            db.update(Camera,camera.id,{'preview_public':False,'preview_job_id':None,'preview_at':None,'preview_mime':None})
        return
    folder = media_folder(camera.id,job.id)
    frames = sorted(UPLOADS.glob(f'{job.id}-*.jpg'))
    if not frames: raise HTTPException(409,'Không còn ảnh video để chia sẻ. Hãy phân tích lại video.')
    folder.mkdir(parents=True,exist_ok=True)
    pending = folder/'poster.pending'
    shutil.copyfile(frames[0],pending)
    pending.replace(folder/'poster.jpg')
    retained = UPLOADS/f'{job.id}.retained'
    mime = None
    if job.retain_video and retained.is_file():
        pending = folder/'video.pending'
        shutil.copyfile(retained,pending)
        pending.replace(folder/'video.bin')
        mime = MIME.get(Path(job.filename).suffix.lower(),'application/octet-stream')
    db.update(Camera,camera.id,{'preview_public':True,'preview_job_id':job.id,
        'preview_at':job.observed_at,'preview_source':'uploaded','preview_mime':mime})


def publish_job(db, job, user, options, historical=False):
    if job.user_id!=user.id and user.role!='admin': raise HTTPException(403,'Bạn không có quyền truy cập dữ liệu này.')
    if job.status!='completed' or not job.result: raise HTTPException(409,'Video chưa phân tích xong.')
    if not job.observed_at: raise HTTPException(422,'Cần thời điểm ghi hình để đưa video vào thống kê giao thông.')
    start = parse_timestamp(job.observed_at)
    age = (now()-start).total_seconds()
    if age<0 or (not historical and age>TTL_MINUTES*60):
        raise HTTPException(422,'Video quá cũ để cập nhật hiện tại. Dùng "Lưu vào lịch sử" cho video quay từ trước.')
    samples = job.result.get('samples',[])
    if samples and start+timedelta(seconds=max(s['second'] for s in samples))>now()+timedelta(seconds=30):
        raise HTTPException(422,'Thời điểm kết thúc video đang ở tương lai. Kiểm tra lại thời điểm bắt đầu ghi hình.')
    camera = db.get(Camera,job.camera_id)
    if not camera: raise HTTPException(404,'Không tìm thấy camera.')
    segment_id = job.camera_config['segment_id']
    segment = db.get(Segment,segment_id)
    if not segment: raise HTTPException(404,'Không tìm thấy đoạn đường.')
    if not historical and (not camera.active or not segment.active or camera.segment_id!=segment_id):
        raise HTTPException(409,'Camera/đoạn đường đã ngừng hoặc camera đã đổi vị trí. Hãy phân tích lại.')
    if options.share_preview and camera.segment_id!=segment_id:
        raise HTTPException(409,'Camera đã đổi đoạn đường; chỉ lưu lịch sử, không chia sẻ ảnh cho vị trí mới.')
    existing = db.find_one(Observation,{'job_id':job.id})
    if existing and job.history_published: raise HTTPException(409,'Video này đã được công bố.')
    row = existing or Observation(segment_id=segment_id,camera_id=camera.id,user_id=user.id,job_id=job.id,
        density=job.result['density'],score=job.result['score'],count=round(job.result['average_count']),
        source='yolo',note=f'YOLO {job.result["model"]}; video {job.id}',observed_at=job.observed_at)
    if not existing: db.add(row); db.flush()
    append_video_samples(db,job,row)
    share_media(db,camera,job,options.share_preview)
    db.update(VideoJob,job.id,{'history_published':True})
    emit_alerts(db,row)
    audit(db,user.id,'video_archived' if historical else 'video_published',job.id)
    db.commit()
    return observation_dict(row)


def camera_for_media(db, camera_id):
    camera = db.get(Camera,camera_id)
    segment = db.get(Segment,camera.segment_id) if camera else None
    if not camera or not camera.active or not segment or not segment.active or not camera.preview_public or not camera.preview_job_id:
        raise HTTPException(404,'Camera chưa có ảnh/video được cho phép chia sẻ.')
    return camera


@router.get('/api/monitor/cameras/{camera_id}/frame')
def shared_frame(camera_id:int,db=Depends(get_db)):
    camera = camera_for_media(db,camera_id)
    path = media_folder(camera_id,camera.preview_job_id)/'poster.jpg'
    if not path.is_file(): raise HTTPException(404,'Chưa có khung hình.')
    return FileResponse(path,media_type='image/jpeg')


@router.get('/api/monitor/cameras/{camera_id}/video')
def shared_video(camera_id:int,db=Depends(get_db)):
    camera = camera_for_media(db,camera_id)
    path = media_folder(camera_id,camera.preview_job_id)/'video.bin'
    if not camera.preview_mime or not path.is_file(): raise HTTPException(404,'Video không được giữ để chia sẻ; xem ảnh minh họa.')
    return FileResponse(path,media_type=camera.preview_mime)


@router.get('/api/videos/{ident}/source')
def private_video(ident:str,user=Depends(require_user),db=Depends(get_db)):
    job = db.get(VideoJob,ident)
    if not job: raise HTTPException(404,'Không tìm thấy video.')
    if job.user_id!=user.id and user.role!='admin': raise HTTPException(403,'Bạn không có quyền truy cập dữ liệu này.')
    path = UPLOADS/f'{job.id}.retained'
    if not job.retain_video or not path.is_file(): raise HTTPException(404,'Video gốc không được giữ lại.')
    return FileResponse(path,media_type=MIME.get(Path(job.filename).suffix.lower(),'application/octet-stream'))


@router.post('/api/videos/{ident}/archive')
def archive_video(ident:str,options:PublishOptions,user=Depends(operator),db=Depends(get_db)):
    job = db.get(VideoJob,ident)
    if not job: raise HTTPException(404,'Không tìm thấy video.')
    return publish_job(db,job,user,options,historical=True)


@router.post('/api/videos/{ident}/share-preview')
def change_preview(ident:str,options:PublishOptions,user=Depends(operator),db=Depends(get_db)):
    job = db.get(VideoJob,ident)
    if not job: raise HTTPException(404,'Không tìm thấy video.')
    if job.user_id!=user.id and user.role!='admin': raise HTTPException(403,'Bạn không có quyền truy cập dữ liệu này.')
    if not db.find_one(Observation,{'job_id':ident}): raise HTTPException(409,'Hãy công bố hoặc lưu lịch sử trước khi chia sẻ ảnh/video.')
    camera = db.get(Camera,job.camera_id)
    if not camera or camera.segment_id!=job.camera_config['segment_id']: raise HTTPException(409,'Camera đã đổi vị trí.')
    share_media(db,camera,job,options.share_preview)
    audit(db,user.id,'camera_preview_shared' if options.share_preview else 'camera_preview_hidden',ident)
    db.commit()
    return {'message':'Đã cập nhật quyền chia sẻ ảnh/video camera.'}


def latest_by(collection,field):
    return {row['_id']:row['item'] for row in collection.aggregate([
        {'$match':{'observed_at':{'$lte':stamp()}}},
        {'$sort':{'observed_at':-1,'_id':-1}},
        {'$group':{'_id':'$'+field,'item':{'$first':'$$ROOT'}}}])}


@router.get('/api/monitor/cameras')
def camera_board(db=Depends(get_db)):
    segments = {s.id:s for s in db.find(Segment)}
    latest = latest_by(db.database.traffic_samples,'camera_id')
    observations = latest_by(db.database.observations,'camera_id')
    result = []
    for camera in db.find(Camera,sort=[('id',1)]):
        segment = segments.get(camera.segment_id)
        row = latest.get(camera.id)
        ob = observations.get(camera.id)
        if ob and (not row or ob['observed_at']>row['observed_at']): row=ob
        # A camera moved to another road must not display data from its old location.
        if row and row['segment_id']!=camera.segment_id: row=None
        active = camera.active and bool(segment and segment.active)
        current = bool(row and active and now()-timedelta(minutes=TTL_MINUTES)<=parse_timestamp(row['observed_at'])<=now())
        preview = bool(active and camera.preview_public and camera.preview_job_id)
        token = camera.preview_job_id or ''
        result.append({'id':camera.id,'name':camera.name,'segment_id':camera.segment_id,
            'segment_name':segment.name if segment else 'Đoạn đường không còn tồn tại',
            'is_demo':segment.is_demo if segment else False,'active':active,
            'state':'inactive' if not active else ('current' if current else ('stale' if row else 'empty')),
            'density':row['density'] if current else None,'last_density':row['density'] if row else None,
            'score':row['score'] if current else None,'count':row['count'] if row else None,
            'vehicle_counts':row.get('vehicle_counts',{}) if row else {},
            'observed_at':row['observed_at'] if row else None,'source':row['source'] if row else None,
            'preview_at':camera.preview_at if preview else None,
            'image_url':f'/api/monitor/cameras/{camera.id}/frame?v={token}' if preview else None,
            'video_url':f'/api/monitor/cameras/{camera.id}/video?v={token}' if preview and camera.preview_mime else None})
    return {'generated_at':stamp(),'ttl_minutes':TTL_MINUTES,'cameras':result}


@router.get('/api/traffic/history')
def road_history(segment_id:int,period:str,value:str,db=Depends(get_db)):
    segment = db.get(Segment,segment_id)
    if not segment: raise HTTPException(404,'Không tìm thấy đoạn đường.')
    return history_report(db.database,segment,period,value)
