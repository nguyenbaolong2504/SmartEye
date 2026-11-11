"""Public camera directory and explicitly shared images, separate from monitoring."""
import time
from collections import OrderedDict
from datetime import timedelta
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from .business_models import DataSource
from .db import get_db, now, stamp
from .models import Camera, Segment
from .security import permit
from . import monitoring, sources
from .business_common import utc

router=APIRouter(dependencies=[Depends(permit('cameras.view'))])
_images=OrderedDict()


def location(segment, position=None):
    points=segment.geometry
    return position or (points[len(points)//2] if points else None)


def published_source(db, ident):
    source=db.get(DataSource,ident)
    segment=db.get(Segment,source.segment_id) if source else None
    if not (source and source.kind=='camera' and source.public_preview and source.authorized
            and source.active and source.tested and segment and segment.active):
        raise HTTPException(404,'Camera chưa được chia sẻ hoặc đã ngừng hoạt động.')
    sources.url_valid(source.url)
    return source


@router.get('/api/traffic/cameras')
def directory(db=Depends(get_db)):
    segments={item.id:item for item in db.find(Segment)}
    cameras=[]
    for source in db.find(DataSource,{'kind':'camera','public_preview':True,'authorized':True},sort=[('id',1)]):
        segment=segments.get(source.segment_id)
        if not segment:continue
        active=bool(source.active and segment.active)
        state='inactive'
        if active:
            state='ready' if source.tested else 'empty'
            if source.connection_state=='error':state='error'
            elif source.checked_at and now()-utc(source.checked_at)>timedelta(minutes=source.stale_minutes):state='stale'
        try:
            sources.url_valid(source.url)
            public_url=source.url if not source.credential_env else None
        except HTTPException:
            public_url=None
            state='error'
        playable=active and source.tested
        video=public_url if playable and source.format=='video' else None
        cameras.append({'id':f'source-{source.id}','name':source.name,'segment_id':segment.id,
            'segment_name':segment.name,'area':segment.area,'location_name':source.location_name or source.name,
            'position':location(segment,source.position),'position_exact':source.position is not None,
            'is_demo':segment.is_demo,'direction':source.direction,'state':state,'active':active,'segment_active':segment.active,
            'source_name':source.name,'source_host':urlsplit(source.url).hostname,'captured_at':None,
            'checked_at':source.checked_at,'refresh_seconds':max(10,source.interval_seconds),
            'image_url':f'/api/traffic/cameras/sources/{source.id}/frame?v={source.revision}' if playable and source.format=='image' else None,
            'video_url':video,'source_url':public_url,'media_kind':source.format})
    for camera in db.find(Camera,sort=[('id',1)]):
        segment=segments.get(camera.segment_id)
        if not segment:continue
        active=bool(camera.active and segment.active)
        shared=active and camera.preview_public and bool(camera.preview_job_id)
        token=camera.preview_job_id or ''
        cameras.append({'id':f'recording-{camera.id}','name':camera.name,'segment_id':segment.id,
            'segment_name':segment.name,'area':segment.area,'location_name':camera.name,
            'position':location(segment),'position_exact':False,'is_demo':segment.is_demo,'direction':'forward',
            'state':'inactive' if not active else 'archive' if shared else 'empty','active':active,'segment_active':segment.active,
            'source_name':'Hình ảnh được chia sẻ','source_host':None,'captured_at':camera.preview_at if shared else None,
            'analysis_url':f'/api/traffic/cameras/recordings/{camera.id}/analysis?v={camera.analysis_job_id}' if active and camera.preview_public and camera.analysis_job_id else None,
            'checked_at':None,'refresh_seconds':0,'source_url':None,'media_kind':'recording',
            'image_url':f'/api/traffic/cameras/recordings/{camera.id}/frame?v={token}' if shared else None,
            'video_url':f'/api/traffic/cameras/recordings/{camera.id}/video?v={token}' if shared and camera.preview_mime else None})
    return {'cameras':cameras,'generated_at':stamp()}


@router.get('/api/traffic/cameras/sources/{ident}/frame')
async def source_frame(ident:int,db=Depends(get_db)):
    source=published_source(db,ident)
    if source.format!='image':raise HTTPException(404,'Camera này không cung cấp ảnh cập nhật.')
    key=(db.database.name,source.id,source.revision)
    cached=_images.get(key)
    if cached and time.monotonic()-cached[0]<min(60,max(10,source.interval_seconds)):
        return Response(cached[1],media_type=cached[2],headers={'Cache-Control':'no-store','X-Camera-Received-At':cached[3]})
    try:
        raw,mime=await sources.source_request(source)
        if mime not in sources.CAMERA_TYPES['image'] or not raw:
            raise HTTPException(502,'Nguồn chưa cung cấp hình ảnh phù hợp.')
    except HTTPException:
        db.database.data_sources.update_one({'_id':ident,'revision':source.revision},{'$set':{
            'connection_state':'error','checked_at':stamp(),'last_error':'Không lấy được hình ảnh từ camera.'}})
        raise
    current=published_source(db,ident)
    if current.revision!=source.revision:raise HTTPException(409,'Cấu hình camera đã thay đổi. Vui lòng mở lại camera.')
    received_at=stamp()
    db.database.data_sources.update_one({'_id':ident,'revision':source.revision},{'$set':{
        'connection_state':'ready','checked_at':received_at,'last_received_at':received_at,'last_error':None}})
    _images[key]=(time.monotonic(),raw,mime,received_at)
    _images.move_to_end(key)
    while len(_images)>24:_images.popitem(last=False)
    return Response(raw,media_type=mime,headers={'Cache-Control':'no-store','X-Camera-Received-At':received_at})


@router.get('/api/traffic/cameras/recordings/{ident}/frame')
def recording_frame(ident:int,db=Depends(get_db)):
    return monitoring.shared_frame(ident,db)


@router.get('/api/traffic/cameras/recordings/{ident}/video')
def recording_video(ident:int,db=Depends(get_db)):
    return monitoring.shared_video(ident,db)
