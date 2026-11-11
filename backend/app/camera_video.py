"""Publish sample-video analysis without writing it into real road observations."""
import logging
import shutil
import uuid
from collections import Counter
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from .business_common import check_segment_scope
from .config import UPLOADS
from .db import get_db,SessionLocal,stamp
from .models import Camera,Segment,VideoJob
from .security import can,permit,audit
from .monitoring import share_media

router=APIRouter()
CALIBRATION=('segment_id','capacity','low_threshold','high_threshold','roi')
logger=logging.getLogger('smarteye.camera_video')


def camera_config(camera):
    return {key:getattr(camera,key) for key in ('id','name','active',*CALIBRATION)}


def matches(camera,job):
    return all(getattr(camera,key)==job.camera_config.get(key) for key in CALIBRATION)


def finish_analysis(ident):
    from .camera_detection import analyze_camera
    from .camera_forecast import predict_samples
    if not analyze_camera(ident):return
    with SessionLocal() as db:
        job=db.get(VideoJob,ident)
        if not job or job.status!='completed' or not job.result:return
        camera=db.get(Camera,job.camera_id)
        if not camera or camera.analysis_job_id!=ident or not matches(camera,job):return
        result=dict(job.result)
        try:
            result['camera_forecast']=predict_samples(db.database,camera.segment_id,result.get('frames',result['samples']),job.camera_config)
        except Exception:
            logger.exception('Camera forecast unavailable for %s',ident)
            result['camera_forecast']={'state':'unavailable','is_demo':True,'timeline':[],
                'message':'Chưa đủ lịch sử minh họa hoặc mô hình cho tuyến này.'}
        db.update(VideoJob,ident,{'result':result})
        try:
            share_media(db,camera,job,True)
        except Exception:
            logger.exception('Camera media publication failed for %s',ident)
            db.update(VideoJob,ident,{'status':'failed','error':'Không chia sẻ được video. Vui lòng kiểm tra bộ nhớ và phân tích lại.'})
            db.commit()
            return
        audit(db,job.user_id,'camera_video_analyzed',ident)
        db.commit()


def queue_video(db,camera,user_id,path,metadata):
    current=db.get(VideoJob,camera.analysis_job_id) if camera.analysis_job_id else None
    if current and current.status in ('queued','processing'):
        raise HTTPException(409,'Camera đang được phân tích. Vui lòng đợi hoàn tất.')
    if db.count(VideoJob,{'status':{'$in':['queued','processing']}})>=5:
        raise HTTPException(429,'Có nhiều video đang chờ. Vui lòng thử lại sau.')
    ident=str(uuid.uuid4())
    destination=UPLOADS/f'{ident}.video'
    try:
        shutil.copyfile(path,destination)
        filename=Path(path).name if Path(path).suffix.lower()=='.mp4' else 'camera.mp4'
        job=VideoJob(id=ident,user_id=user_id,camera_id=camera.id,filename=filename,
            camera_config=camera_config(camera),retain_video=True,source_metadata={**metadata,'detection_version':2})
        db.add(job);db.commit()
        condition={'analysis_job_id':camera.analysis_job_id,'active':camera.active,
                   **{key:getattr(camera,key) for key in CALIBRATION}}
        claimed=db.update(Camera,camera.id,{'analysis_job_id':ident},condition=condition)
        if not claimed:
            db.delete(job)
            raise HTTPException(409,'Camera vừa được thay đổi hoặc đã có lượt phân tích mới. Vui lòng tải lại.')
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return job


@router.post('/api/cameras/{ident}/analyze-video',status_code=202)
def analyze_again(ident:int,user=Depends(permit('network.manage')),db=Depends(get_db)):
    from .video import executor
    camera=db.get(Camera,ident)
    if not camera:raise HTTPException(404,'Không tìm thấy camera.')
    check_segment_scope(user,camera.segment_id)
    segment=db.get(Segment,camera.segment_id)
    if not camera.active or not segment or not segment.active:raise HTTPException(409,'Camera hoặc tuyến đường đã tắt.')
    previous=db.get(VideoJob,camera.analysis_job_id) if camera.analysis_job_id else None
    if previous and previous.status in ('queued','processing'):
        raise HTTPException(409,'Camera đang được phân tích. Vui lòng đợi hoàn tất.')
    if not previous or not previous.source_metadata.get('is_demo'):
        raise HTTPException(409,'Camera chưa được gắn video mẫu. Cần chuẩn bị video trước.')
    path=UPLOADS/f'{previous.id}.retained'
    if not path.is_file() and camera.preview_job_id:
        shared=db.get(VideoJob,camera.preview_job_id)
        if shared and shared.camera_id==camera.id and shared.source_metadata.get('is_demo'):
            previous=shared
            path=UPLOADS/f'{previous.id}.retained'
    if not path.is_file():raise HTTPException(409,'Không còn tệp video. Cần chuẩn bị lại video mẫu.')
    job=queue_video(db,camera,user.id,path,previous.source_metadata)
    executor.submit(finish_analysis,job.id)
    return {'id':job.id,'status':job.status,'message':'Đang phân tích lại video camera.'}


def visible_analysis(db,ident):
    camera=db.get(Camera,ident)
    segment=db.get(Segment,camera.segment_id) if camera else None
    if not camera or not camera.active or not camera.preview_public or not segment or not segment.active:
        raise HTTPException(404,'Camera chưa có kết quả được chia sẻ.')
    job=db.get(VideoJob,camera.analysis_job_id) if camera.analysis_job_id else None
    if not job or job.camera_id!=ident or not job.source_metadata.get('is_demo'):
        raise HTTPException(404,'Chưa có phân tích video cho camera này.')
    return camera,job


@router.get('/api/traffic/cameras/recordings/{ident}/analysis')
def analysis(ident:int,user=Depends(permit('cameras.view')),db=Depends(get_db)):
    camera,job=visible_analysis(db,ident)
    base={'state':job.status,'progress':job.progress,'is_demo':True,'source':job.source_metadata,
          'segment_id':camera.segment_id,'analyzed_at':job.created_at}
    if not matches(camera,job):return {**base,'state':'outdated','message':'Cấu hình camera đã thay đổi. Cần phân tích lại video.'}
    if job.status!='completed' or not job.result:
        return {**base,'message':job.error or 'Đang phân tích video. Vui lòng chờ trong giây lát.'}
    result=job.result
    if 'camera_forecast' not in result:return {**base,'state':'processing','progress':99,'message':'Đang đối chiếu lịch sử để dự báo.'}
    samples=[]
    for row in result['samples']:
        counts=Counter(box['label'] for box in row.get('boxes',[]))
        samples.append({key:row[key] for key in ('second','count','score','occupancy','density')}|{
            'vehicle_counts':{'car':counts['car'],'motorcycle':counts['motorcycle']+counts['motorbike'],
                              'bus':counts['bus'],'truck':counts['truck']}})
    forecast=result.get('camera_forecast') if can(user,'forecast.view') else None
    frames=result.get('frames',[])
    return {**base,'duration_seconds':result['duration_seconds'],'samples':samples,
        'frames':frames,'fps':result.get('fps',1),'roi':job.camera_config['roi'],
        'detection_version':result.get('detection_version',1),'capacity':job.camera_config['capacity'],
        'average_count':result['average_count'],'peak_count':result['peak_count'],
        'low_threshold':job.camera_config['low_threshold'],'high_threshold':job.camera_config['high_threshold'],
        'frame_url':f'/api/traffic/cameras/recordings/{ident}/analysis-frame?v={job.id}',
        'forecast':forecast,'method':'YOLO11','message':'Kết quả mô tả lượng xe xuất hiện trong video.'}


@router.get('/api/traffic/cameras/recordings/{ident}/analysis-frame',dependencies=[Depends(permit('cameras.view'))])
def analysis_frame(ident:int,db=Depends(get_db)):
    camera,job=visible_analysis(db,ident)
    if not matches(camera,job) or job.status!='completed':raise HTTPException(404,'Chưa có khung hình phân tích phù hợp.')
    path=UPLOADS/f'{uuid.UUID(job.id)}-0.jpg'
    if not path.is_file():raise HTTPException(404,'Chưa có khung hình phân tích.')
    return FileResponse(path,media_type='image/jpeg')
