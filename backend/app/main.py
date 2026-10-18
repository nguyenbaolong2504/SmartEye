import csv
import hashlib
import io
import logging
import os
import re
import secrets
import smtplib
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError
from . import schemas as S
from .config import COOKIE_SECURE, PRODUCTION, UPLOADS, MAX_UPLOAD, MODEL_PATH, TTL_MINUTES
from .db import initialize_database, get_database, get_db, SessionLocal, stamp, now
from .models import User, LoginSession, ResetToken, Segment, Camera, Observation, VideoJob, Favorite, AlertRule, Notification, Audit
from .security import optional_user, require_user, operator, admin, hash_password, verify_password, token_hash, create_session, public_user, audit
from .seed import seed, PLACES
from .traffic import classify, latest_observations, observation_dict, emit_alerts
from .routing import search_routes
from .video import submit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('smarteye')

@asynccontextmanager
async def lifespan(app):
    try:
        initialize_database()
    except PyMongoError:
        raise RuntimeError('Không kết nối được MongoDB. Chạy MongoDB Server/Docker và kiểm tra MONGODB_URI, MONGODB_DB trong .env.') from None
    with SessionLocal() as db:
        seed(db)
        for job in db.find(VideoJob,{'status':{'$in':['queued','processing']}}):
            job.status = 'failed'; job.error = 'Tác vụ bị gián đoạn do máy chủ khởi động lại. Vui lòng tải lại video.'
            (UPLOADS / f'{job.id}.video').unlink(missing_ok=True)
        db.delete_many(LoginSession,{'expires_at':{'$lt':stamp()}})
        db.delete_many(ResetToken,{'expires_at':{'$lt':stamp()}})
        db.commit()
    yield

app = FastAPI(title='SmartEye API', version='1.0.0', lifespan=lifespan)

@app.exception_handler(DuplicateKeyError)
async def duplicate_record(request,exc):
    return JSONResponse({'detail':'Dữ liệu đã tồn tại hoặc tác vụ đã được thực hiện. Vui lòng tải lại.'},status_code=409)

@app.exception_handler(PyMongoError)
async def mongo_unavailable(request,exc):
    return JSONResponse({'detail':'MongoDB chưa sẵn sàng. Kiểm tra dịch vụ database và thử lại.'},status_code=503)
_requests = defaultdict(deque)
_rate_lock = threading.Lock()

@app.middleware('http')
async def guard(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin = request.headers.get('origin')
        allowed = {str(request.base_url).rstrip('/'),os.getenv('APP_BASE_URL','http://localhost:5173')}
        if not PRODUCTION:
            allowed |= {'http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:8000','http://localhost:8000'}
        if origin and origin.rstrip('/') not in allowed:
            return JSONResponse({'detail':'Nguồn yêu cầu không được phép.'},status_code=403)
    bucket = 'auth' if request.url.path.startswith('/api/auth/') and request.method == 'POST' else 'video' if request.url.path == '/api/videos' and request.method == 'POST' else 'route' if request.url.path == '/api/routes/search' else 'general'
    limit = {'auth':20,'video':5,'route':20,'general':180}[bucket]
    ip = request.client.host if request.client else 'unknown'
    key = (ip,bucket)
    with _rate_lock:
        clock = time.monotonic()
        timestamps = _requests[key]
        while timestamps and timestamps[0] < clock-60: timestamps.popleft()
        if len(timestamps) >= limit:
            return JSONResponse({'detail':'Bạn thao tác quá nhanh. Vui lòng chờ một phút.'},status_code=429,headers={'Retry-After':'60'})
        timestamps.append(clock)
        if len(_requests) > 10000:
            for old_key in list(_requests):
                if not _requests[old_key] or _requests[old_key][-1] < clock-60: del _requests[old_key]
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

def item(db, model, ident):
    row = db.get(model,ident)
    if not row: raise HTTPException(404,'Không tìm thấy dữ liệu.')
    return row

def camera_dict(c):
    return {k:getattr(c,k) for k in ('id','name','segment_id','active','capacity','low_threshold','high_threshold','roi')}

def own(row, user):
    if row.user_id != user.id and user.role != 'admin': raise HTTPException(403,'Bạn không có quyền truy cập dữ liệu này.')
    return row

def job_dict(j,summary=False):
    result={k:getattr(j,k) for k in ('id','camera_id','filename','status','progress','error','result','observed_at','created_at','camera_config')}
    if summary and j.result:
        result['result']={**j.result,'samples':[]}
    return result

def cookie(response, token):
    response.set_cookie('smarteye_session',token,httponly=True,secure=COOKIE_SECURE,samesite='strict',max_age=7*86400,path='/')

@app.get('/api/health')
def health():
    get_database().command('ping')
    return {'status':'ok','database':'mongodb','time':stamp()}

@app.get('/api/config')
def config():
    return {'google_routes_available':bool(os.getenv('GOOGLE_ROUTES_API_KEY')),'maps_browser_key':os.getenv('GOOGLE_MAPS_BROWSER_KEY',''),'video_available':MODEL_PATH.is_file(),'max_upload_mb':MAX_UPLOAD//1024//1024,'observation_ttl_minutes':TTL_MINUTES,'demo_available':True,'password_reset_available':bool(os.getenv('SMTP_HOST'))}

@app.post('/api/auth/register',status_code=201)
def register(body:S.Register,response:Response,db=Depends(get_db)):
    user = User(**body.model_dump(exclude={'password'}),password=hash_password(body.password))
    db.add(user)
    try: db.commit()
    except DuplicateKeyError:
        db.rollback(); raise HTTPException(409,'Email đã được đăng ký.')
    cookie(response,create_session(db,user))
    audit(db,user.id,'register'); db.commit()
    return public_user(user)

@app.post('/api/auth/login')
def login(body:S.Login,response:Response,db=Depends(get_db)):
    user = db.find_one(User,{'email':body.email.strip().lower()})
    if not user or not verify_password(body.password,user.password) or not user.active:
        raise HTTPException(401,'Email hoặc mật khẩu không đúng, hoặc tài khoản bị khóa.')
    cookie(response,create_session(db,user)); audit(db,user.id,'login'); db.commit()
    return public_user(user)

@app.post('/api/auth/logout')
def logout(request:Request,response:Response,db=Depends(get_db)):
    db.delete_many(LoginSession,{'token_hash':token_hash(request.cookies.get('smarteye_session',''))}); db.commit()
    response.delete_cookie('smarteye_session',path='/')
    return {'message':'Đã đăng xuất.'}

@app.get('/api/auth/me')
def me(user=Depends(optional_user)):
    return public_user(user) if user else None

@app.patch('/api/auth/profile')
def profile(body:S.ProfileInput,user=Depends(require_user),db=Depends(get_db)):
    row = item(db,User,user.id); row.name=body.name.strip(); db.commit()
    return public_user(row)

@app.post('/api/auth/password')
def change_password(body:S.PasswordChange,response:Response,user=Depends(require_user),db=Depends(get_db)):
    row = item(db,User,user.id)
    if not verify_password(body.current_password,row.password): raise HTTPException(400,'Mật khẩu hiện tại không đúng.')
    row = db.update(User,user.id,{'password':hash_password(body.new_password)},increment={'auth_version':1})
    db.delete_many(LoginSession,{'user_id':user.id}); audit(db,user.id,'password_changed'); db.commit()
    cookie(response,create_session(db,row))
    return {'message':'Đã đổi mật khẩu và thu hồi các phiên cũ.'}

@app.post('/api/auth/forgot-password')
def forgot_password(body:S.ResetRequest,db=Depends(get_db)):
    if not os.getenv('SMTP_HOST'): raise HTTPException(503,'Hệ thống chưa cấu hình email đặt lại mật khẩu. Vui lòng liên hệ quản trị viên.')
    row = db.find_one(User,{'email':body.email.strip().lower(),'active':True})
    if row:
        token = secrets.token_urlsafe(32)
        db.delete_many(ResetToken,{'user_id':row.id})
        db.add(ResetToken(token_hash=token_hash(token),user_id=row.id,auth_version=row.auth_version,expires_at=(now()+timedelta(minutes=30)).isoformat())); db.commit()
        msg = EmailMessage(); msg['Subject']='Đặt lại mật khẩu SmartEye'; msg['From']=os.getenv('SMTP_FROM',os.getenv('SMTP_USER','')); msg['To']=row.email
        msg.set_content(f'Mở liên kết sau trong 30 phút để đặt lại mật khẩu: {os.getenv("APP_BASE_URL","http://localhost:5173")}/?reset={token}\nNếu bạn không yêu cầu, hãy bỏ qua email này.')
        try:
            with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=10) as smtp:
                smtp.starttls()
                if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
                smtp.send_message(msg)
        except Exception:
            logger.warning('Password reset mail delivery failed')
    return {'message':'Nếu email thuộc một tài khoản hoạt động, hướng dẫn đặt lại mật khẩu sẽ được gửi.'}

@app.post('/api/auth/reset-password')
def reset_password(body:S.ResetPassword,db=Depends(get_db)):
    token = db.pop(ResetToken,{'token_hash':token_hash(body.token),'expires_at':{'$gt':stamp()}})
    if not token: raise HTTPException(400,'Liên kết không hợp lệ hoặc đã hết hạn.')
    row = item(db,User,token.user_id)
    if not row.active: raise HTTPException(400,'Tài khoản đã bị khóa.')
    changed=db.update(User,row.id,{'password':hash_password(body.password)},condition={'auth_version':token.auth_version},increment={'auth_version':1})
    if not changed: raise HTTPException(400,'Liên kết không hợp lệ hoặc đã hết hạn.')
    db.delete_many(LoginSession,{'user_id':row.id}); audit(db,row.id,'password_reset'); db.commit()
    return {'message':'Đã đặt lại mật khẩu. Vui lòng đăng nhập.'}

@app.get('/api/places')
def places(): return PLACES

@app.get('/api/segments')
def segments(db=Depends(get_db)):
    latest = latest_observations(db)
    return [{**{k:getattr(s,k) for k in ('id','name','start_node','end_node','distance_km','geometry','active','is_demo')},'observation':observation_dict(latest[s.id]) if s.id in latest else None} for s in db.find(Segment,sort=[('id',1)])]

@app.post('/api/segments',status_code=201)
def add_segment(body:S.SegmentInput,user=Depends(admin),db=Depends(get_db)):
    row=Segment(**body.model_dump()); db.add(row); audit(db,user.id,'segment_created',body.name); db.commit()
    return {'id':row.id}

@app.put('/api/segments/{ident}')
def edit_segment(ident:int,body:S.SegmentInput,user=Depends(admin),db=Depends(get_db)):
    row=item(db,Segment,ident)
    if row.geometry != body.geometry and db.find_one(Observation,{'segment_id':ident}):
        raise HTTPException(409,'Đoạn đường đã có quan sát. Hãy ngừng đoạn cũ và tạo đoạn mới khi thay đổi vị trí để bảo toàn lịch sử.')
    for k,v in body.model_dump().items(): setattr(row,k,v)
    audit(db,user.id,'segment_updated',str(ident)); db.commit(); return {'id':row.id}

@app.delete('/api/segments/{ident}')
def disable_segment(ident:int,user=Depends(admin),db=Depends(get_db)):
    row=item(db,Segment,ident); row.active=False
    for camera in db.find(Camera,{'segment_id':ident}): camera.active=False
    audit(db,user.id,'segment_disabled',str(ident));db.commit();return {'message':'Đã ngừng đoạn đường và các camera liên quan.'}

@app.get('/api/cameras')
def cameras(db=Depends(get_db)):
    return [camera_dict(c) for c in db.find(Camera,sort=[('id',1)])]

@app.post('/api/cameras',status_code=201)
def add_camera(body:S.CameraInput,user=Depends(admin),db=Depends(get_db)):
    item(db,Segment,body.segment_id)
    row = Camera(**body.model_dump()); db.add(row); audit(db,user.id,'camera_created',body.name); db.commit()
    return camera_dict(row)

@app.put('/api/cameras/{ident}')
def edit_camera(ident:int,body:S.CameraInput,user=Depends(admin),db=Depends(get_db)):
    row=item(db,Camera,ident); item(db,Segment,body.segment_id)
    for k,v in body.model_dump().items(): setattr(row,k,v)
    audit(db,user.id,'camera_updated',str(ident)); db.commit(); return camera_dict(row)

@app.delete('/api/cameras/{ident}')
def disable_camera(ident:int,user=Depends(admin),db=Depends(get_db)):
    row=item(db,Camera,ident); row.active=False
    audit(db,user.id,'camera_disabled',str(ident)); db.commit(); return {'message':'Đã ngừng camera, lịch sử vẫn được bảo toàn.'}

@app.post('/api/observations',status_code=201)
def manual_observation(body:S.ObservationInput,user=Depends(operator),db=Depends(get_db)):
    segment = item(db,Segment,body.segment_id)
    if not segment.active: raise HTTPException(400,'Đoạn đường đã ngừng theo dõi.')
    if body.observed_at > now()+timedelta(seconds=30): raise HTTPException(422,'Không thể ghi quan sát trong tương lai.')
    row=Observation(**body.model_dump(exclude={'observed_at'}),user_id=user.id,density=classify(body.score),source='manual',observed_at=body.observed_at.isoformat())
    db.add(row); db.flush(); emit_alerts(db,row); audit(db,user.id,'manual_observation',str(body.segment_id)); db.commit()
    return observation_dict(row)

@app.post('/api/routes/search')
async def routes(body:S.RouteRequest,db=Depends(get_db)):
    # Provider route results are intentionally not persisted or used for training.
    return await search_routes(db,body)

@app.post('/api/videos',status_code=202)
async def upload_video(camera_id:int=Form(...),observed_at:str|None=Form(None),file:UploadFile=File(...),user=Depends(require_user),db=Depends(get_db)):
    camera=item(db,Camera,camera_id)
    if not camera.active: raise HTTPException(400,'Camera đã ngừng hoạt động.')
    if not item(db,Segment,camera.segment_id).active: raise HTTPException(400,'Đoạn đường đã ngừng theo dõi.')
    if not MODEL_PATH.is_file(): raise HTTPException(503,'Chưa có mô hình YOLO. Quản trị viên cần tải trọng số theo README.')
    active_count = db.count(VideoJob,{'status':{'$in':['queued','processing']}})
    if active_count >= 5: raise HTTPException(429,'Hàng đợi phân tích đang đầy. Vui lòng chờ các video hiện tại hoàn tất.')
    filename = Path(file.filename or 'video.mp4').name[:180]
    if Path(filename).suffix.lower() not in ('.mp4','.avi','.mov','.mkv','.webm'):
        raise HTTPException(415,'Chỉ hỗ trợ MP4, AVI, MOV, MKV và WebM.')
    timestamp=None
    if observed_at:
        try:
            dt=datetime.fromisoformat(observed_at.replace('Z','+00:00'))
            if not dt.tzinfo or dt > now()+timedelta(seconds=30): raise ValueError()
            timestamp=dt.astimezone(timezone.utc).isoformat()
        except ValueError: raise HTTPException(422,'Thời gian quay video không hợp lệ hoặc nằm trong tương lai.')
    ident=str(uuid.uuid4()); path=UPLOADS/f'{ident}.video'; size=0
    try:
        with path.open('wb') as output:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > MAX_UPLOAD: raise HTTPException(413,f'Video tối đa {MAX_UPLOAD//1024//1024} MB.')
                output.write(chunk)
        if not size: raise HTTPException(422,'Video rỗng.')
        job=VideoJob(id=ident,user_id=user.id,camera_id=camera.id,filename=filename,observed_at=timestamp,camera_config=camera_dict(camera))
        db.add(job); audit(db,user.id,'video_uploaded',ident); db.commit()
    except Exception:
        path.unlink(missing_ok=True); raise
    finally: await file.close()
    submit(ident)
    return job_dict(job)

@app.get('/api/videos')
def videos(user=Depends(require_user),db=Depends(get_db)):
    filters={} if user.role=='admin' else {'user_id':user.id}
    return [job_dict(j,summary=True) for j in db.find(VideoJob,filters,sort=[('created_at',-1)],limit=50,exclude=['result.samples'])]

@app.get('/api/videos/{ident}')
def get_video(ident:str,user=Depends(require_user),db=Depends(get_db)):
    return job_dict(own(item(db,VideoJob,ident),user))

@app.get('/api/videos/{ident}/frames/{second}')
def frame(ident:str,second:int,user=Depends(require_user),db=Depends(get_db)):
    own(item(db,VideoJob,ident),user)
    path=UPLOADS/f'{ident}-{second}.jpg'
    if not path.is_file(): raise HTTPException(404,'Chưa có ảnh cho mốc thời gian này.')
    return FileResponse(path,media_type='image/jpeg')

@app.post('/api/videos/{ident}/cancel')
def cancel_video(ident:str,user=Depends(require_user),db=Depends(get_db)):
    job=own(item(db,VideoJob,ident),user)
    if job.status not in ('queued','processing'): raise HTTPException(409,'Tác vụ đã kết thúc.')
    job=db.update(VideoJob,ident,{'status':'cancelled'},condition={'status':{'$in':['queued','processing']}})
    if not job: raise HTTPException(409,'Tác vụ đã kết thúc.')
    return job_dict(job)

@app.delete('/api/videos/{ident}')
def delete_video(ident:str,user=Depends(require_user),db=Depends(get_db)):
    job=own(item(db,VideoJob,ident),user)
    if job.status in ('queued','processing'): raise HTTPException(409,'Hãy hủy tác vụ trước khi xóa.')
    for path in UPLOADS.glob(f'{job.id}-*.jpg'): path.unlink(missing_ok=True)
    (UPLOADS/f'{job.id}.video').unlink(missing_ok=True)
    db.delete(job); audit(db,user.id,'video_deleted',ident); db.commit()
    return {'message':'Đã xóa kết quả và ảnh video. Quan sát đã công bố vẫn giữ nguồn gốc.'}

@app.post('/api/videos/{ident}/publish')
def publish_video(ident:str,user=Depends(operator),db=Depends(get_db)):
    job=own(item(db,VideoJob,ident),user)
    if job.status != 'completed' or not job.result: raise HTTPException(409,'Video chưa phân tích xong.')
    if db.find_one(Observation,{'job_id':ident}): raise HTTPException(409,'Video này đã được công bố.')
    if not job.observed_at: raise HTTPException(422,'Video chưa có thời điểm ghi hình, chỉ có thể dùng để xem lại.')
    age=(now()-datetime.fromisoformat(job.observed_at)).total_seconds()
    if age < 0 or age > TTL_MINUTES*60: raise HTTPException(422,'Video đã quá cũ để cập nhật giao thông hiện tại.')
    camera=item(db,Camera,job.camera_id)
    if not camera.active or camera.segment_id != job.camera_config['segment_id']: raise HTTPException(409,'Camera đã đổi đoạn đường hoặc ngừng hoạt động. Hãy phân tích lại.')
    if not item(db,Segment,camera.segment_id).active: raise HTTPException(409,'Đoạn đường đã ngừng theo dõi.')
    row=Observation(segment_id=camera.segment_id,camera_id=camera.id,user_id=user.id,job_id=job.id,density=job.result['density'],score=job.result['score'],count=round(job.result['average_count']),source='yolo',note=f'YOLO {job.result["model"]}; video {job.id}',observed_at=job.observed_at)
    db.add(row); db.flush(); emit_alerts(db,row); audit(db,user.id,'video_published',ident); db.commit()
    return observation_dict(row)

@app.get('/api/favorites')
def favorites(user=Depends(require_user),db=Depends(get_db)):
    return [{'id':r.id,'name':r.name,'request':r.request} for r in db.find(Favorite,{'user_id':user.id},sort=[('id',-1)])]

@app.post('/api/favorites',status_code=201)
def add_favorite(body:S.FavoriteInput,user=Depends(require_user),db=Depends(get_db)):
    if db.count(Favorite,{'user_id':user.id}) >= 50: raise HTTPException(422,'Mỗi tài khoản lưu tối đa 50 hành trình.')
    request=body.request.model_dump(mode='json'); request['departure_at']=None
    # Save user's inputs only; no Google geometry or provider results.
    row=Favorite(user_id=user.id,name=body.name,request=request); db.add(row); db.commit()
    return {'id':row.id,'name':row.name,'request':row.request}

@app.delete('/api/favorites/{ident}')
def delete_favorite(ident:int,user=Depends(require_user),db=Depends(get_db)):
    row=own(item(db,Favorite,ident),user); db.delete(row); db.commit(); return {'message':'Đã xóa hành trình.'}

@app.get('/api/alerts')
def alerts(user=Depends(require_user),db=Depends(get_db)):
    rules=[{k:getattr(r,k) for k in ('id','segment_id','density','active')} for r in db.find(AlertRule,{'user_id':user.id})]
    notices=[{k:getattr(n,k) for k in ('id','message','read','created_at')} for n in db.find(Notification,{'user_id':user.id},sort=[('id',-1)],limit=100)]
    return {'rules':rules,'notifications':notices}

@app.post('/api/alerts',status_code=201)
def add_alert(body:S.RuleInput,user=Depends(require_user),db=Depends(get_db)):
    item(db,Segment,body.segment_id)
    if db.find_one(AlertRule,{'user_id':user.id,'segment_id':body.segment_id,'density':body.density}):
        raise HTTPException(409,'Bạn đã theo dõi điều kiện này.')
    row=AlertRule(user_id=user.id,**body.model_dump()); db.add(row); db.commit(); return {'id':row.id}

@app.delete('/api/alerts/{ident}')
def remove_alert(ident:int,user=Depends(require_user),db=Depends(get_db)):
    row=own(item(db,AlertRule,ident),user); db.delete(row); db.commit(); return {'message':'Đã bỏ theo dõi.'}

@app.post('/api/notifications/{ident}/read')
def read_notification(ident:int,user=Depends(require_user),db=Depends(get_db)):
    row=own(item(db,Notification,ident),user); row.read=True; db.commit(); return {'message':'Đã đánh dấu đã đọc.'}

def report_rows(db,segment_id=None,start=None,end=None):
    filters={}
    if segment_id: filters['segment_id']=segment_id
    for value, comparator in ((start,True),(end,False)):
        if value:
            try:
                parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
                if not parsed.tzinfo: raise ValueError()
            except ValueError: raise HTTPException(422,'Bộ lọc thời gian cần timestamp có múi giờ.')
            normalized=parsed.astimezone(timezone.utc).isoformat()
            filters.setdefault('observed_at',{})['$gte' if comparator else '$lte']=normalized
    return db.find(Observation,filters,sort=[('observed_at',-1)],limit=5000)

@app.get('/api/reports')
def reports(segment_id:int|None=None,start:str|None=None,end:str|None=None,user=Depends(operator),db=Depends(get_db)):
    rows=report_rows(db,segment_id,start,end)
    return {'total':len(rows),'limit':5000,'distribution':{k:sum(r.density==k for r in rows) for k in ('LOW','NORMAL','HIGH')},'average_count':round(sum(r.count for r in rows)/len(rows),1) if rows else 0,'observations':[observation_dict(r) for r in rows]}

@app.get('/api/reports/export')
def export(segment_id:int|None=None,start:str|None=None,end:str|None=None,user=Depends(operator),db=Depends(get_db)):
    rows=report_rows(db,segment_id,start,end); out=io.StringIO(); out.write('\ufeff'); writer=csv.writer(out)
    writer.writerow(['id','segment_id','density','score','vehicle_count','source','observed_at','note'])
    for r in rows:
        note=r.note
        if note.lstrip().startswith(('=','+','-','@')): note="'"+note
        writer.writerow([r.id,r.segment_id,r.density,r.score,r.count,r.source,r.observed_at,note])
    audit(db,user.id,'report_export',str(len(rows))); db.commit()
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="smarteye-observations.csv"'})

@app.get('/api/admin/users')
def users(q:str='',user=Depends(admin),db=Depends(get_db)):
    filters={}
    if q: filters={'$or':[{'email':{'$regex':re.escape(q[:100]),'$options':'i'}},{'name':{'$regex':re.escape(q[:100]),'$options':'i'}}]}
    return [public_user(u) for u in db.find(User,filters,sort=[('id',1)],limit=200)]

@app.patch('/api/admin/users/{ident}')
def edit_user(ident:int,body:S.UserUpdate,user=Depends(admin),db=Depends(get_db)):
    row=item(db,User,ident)
    if ident == user.id and (body.role!='admin' or not body.active): raise HTTPException(422,'Không thể tự khóa hoặc hạ quyền quản trị của mình.')
    row=db.update(User,ident,{'role':body.role,'active':body.active},increment={'auth_version':1})
    db.delete_many(LoginSession,{'user_id':ident}); audit(db,user.id,'user_updated',f'{ident}: {body.role}, active={body.active}'); db.commit()
    return public_user(row)

@app.post('/api/admin/users/{ident}/revoke')
def revoke(ident:int,user=Depends(admin),db=Depends(get_db)):
    item(db,User,ident); db.update(User,ident,{},increment={'auth_version':1}); db.delete_many(LoginSession,{'user_id':ident}); audit(db,user.id,'sessions_revoked',str(ident)); db.commit(); return {'message':'Đã thu hồi tất cả phiên đăng nhập.'}

@app.get('/api/admin/system')
def system(user=Depends(admin),db=Depends(get_db)):
    return {'model_ready':MODEL_PATH.is_file(),'model_name':MODEL_PATH.name,'google_ready':bool(os.getenv('GOOGLE_ROUTES_API_KEY')),'active_jobs':db.count(VideoJob,{'status':{'$in':['queued','processing']}}),'audit':[{k:getattr(a,k) for k in ('id','user_id','action','detail','created_at')} for a in db.find(Audit,sort=[('id',-1)],limit=100)]}
