"""Authorized source configuration, tested mappings and bounded ingestion."""
import asyncio
import csv
import io
import ipaddress
import json
import math
import os
import socket
from dataclasses import replace
from datetime import timedelta
from urllib.parse import urlsplit, parse_qsl
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import Field
from pymongo.errors import DuplicateKeyError
from .business_common import (Input, Revision, road, get_record, changed, event, log_event, serialize,
                              fingerprint, period, allowed_query, check_segment_scope)
from .business_models import DataSource, RoadReading, SourceReceipt
from .business_schemas import SourceInput, SourceEdit, MappingInput, Toggle
from .db import get_db, stamp, now
from .models import TrafficSample
from .security import admin, permit

router=APIRouter()
MAX_BYTES=2*1024*1024
CAMERA_TYPES={'image': {'image/jpeg', 'image/png', 'image/webp'}, 'video': {'video/mp4', 'video/webm'}}


def source_data(source):
    result=serialize(source)
    result['credential_configured']=bool(source.credential_env and os.getenv(source.credential_env))
    result['data_state']=source_state(source)
    return result


def source_state(source):
    if not source.active:return 'disabled'
    if source.connection_state=='error':return 'error'
    if not source.last_received_at:return 'unknown'
    from .business_common import utc
    return 'fresh' if now()-utc(source.last_received_at)<=timedelta(minutes=source.stale_minutes) else 'stale'


def url_valid(url):
    if not url:return
    try:
        parsed=urlsplit(url)
        _=parsed.port
    except ValueError:raise HTTPException(422,'Địa chỉ nguồn dữ liệu chưa hợp lệ.') from None
    if any(c.isspace() for c in url):raise HTTPException(422,'Địa chỉ nguồn không được chứa khoảng trắng.')
    private_test=os.getenv('TRAFFIC_SOURCE_ALLOW_PRIVATE','false')=='true' and os.getenv('APP_ENV')!='production'
    if parsed.scheme not in (('http','https') if private_test else ('https',)) or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422,'Nguồn kết nối cần HTTPS và không chứa thông tin đăng nhập trong địa chỉ.')
    if any(any(word in key.lower() for word in ('token','key','secret','password','auth','signature','credential')) for key,_ in parse_qsl(parsed.query)):
        raise HTTPException(422,'Không đặt mã truy cập trong URL. Hãy dùng biến môi trường TRAFFIC_SOURCE_ riêng.')
    try:
        address=ipaddress.ip_address(parsed.hostname)
        if not address.is_global and not private_test:raise HTTPException(422,'Nguồn dữ liệu không được trỏ vào mạng nội bộ.')
    except ValueError:pass


async def source_request(source,head=False):
    """Pin the validated public IP, retaining the original TLS SNI and Host.

    This avoids a second DNS resolution between checking and connecting; never
    follows redirects or uses ambient proxy credentials.
    """
    url_valid(source.url);parsed=urlsplit(source.url)
    private_test=os.getenv('TRAFFIC_SOURCE_ALLOW_PRIVATE','false')=='true' and os.getenv('APP_ENV')!='production'
    async def fetch():
        answers=await asyncio.to_thread(socket.getaddrinfo,parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),0,socket.SOCK_STREAM)
        addresses=list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses or not private_test and any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise HTTPException(422,'Nguồn dữ liệu không được trỏ vào mạng nội bộ hoặc địa chỉ đặc biệt.')
        headers={'Host':parsed.netloc,'User-Agent':'SmartEye/1.1 authorized traffic source'}
        if source.credential_env:
            secret=os.getenv(source.credential_env)
            if not secret:raise HTTPException(409,'Chưa cấu hình thông tin xác thực nguồn ở máy chủ.')
            headers['Authorization']='Bearer '+secret
        target=httpx.URL(source.url).copy_with(host=addresses[0])
        async with httpx.AsyncClient(timeout=httpx.Timeout(5,connect=3),trust_env=False,follow_redirects=False) as client:
            async with client.stream('HEAD' if head else 'GET',target,headers=headers,extensions={'sni_hostname':parsed.hostname}) as response:
                if not 200<=response.status_code<300:raise HTTPException(502,'Mất kết nối nguồn dữ liệu hoặc nguồn từ chối truy cập.')
                data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>MAX_BYTES:raise HTTPException(413,'Dữ liệu nguồn vượt giới hạn 2 MB cho một lượt nhận.')
                return bytes(data),response.headers.get('content-type','').split(';')[0]
    try:return await asyncio.wait_for(fetch(),timeout=8)
    except HTTPException:raise
    except (httpx.HTTPError,OSError,asyncio.TimeoutError):raise HTTPException(502,'Mất kết nối nguồn dữ liệu. Vui lòng kiểm tra và thử lại.') from None


def signature(body):
    return fingerprint({'kind':body.kind,'segment_id':body.segment_id,'direction':body.direction,
                        'url':body.url,'name':body.name.casefold() if body.kind=='file' else ''})


def managed_source(db,ident,user):
    source=get_record(db,DataSource,ident)
    check_segment_scope(user,source.segment_id)
    return source


def validate_credentials(body, current=None):
    if not body.credential_env:
        return
    target=urlsplit(body.url)
    if current and current.credential_env==body.credential_env:
        old=urlsplit(current.url)
        if (target.scheme,target.hostname,target.port)==(old.scheme,old.hostname,old.port):
            return
    expected=os.getenv(f'{body.credential_env}_HOST','').strip().lower()
    if target.scheme!='https' or target.port not in (None,443) or target.hostname!=expected:
        raise HTTPException(422,'Nguồn dùng mã truy cập cần máy chủ HTTPS đã được cấu hình trước.')


@router.get('/api/management/sources')
@router.get('/api/admin/sources',dependencies=[Depends(admin)],include_in_schema=False)
def list_sources(q:str=Query(default='',max_length=100),user=Depends(permit('sources.manage')),db=Depends(get_db)):
    import re
    query=allowed_query(user)
    if q:query['name']={'$regex':re.escape(q),'$options':'i'}
    return [source_data(s) for s in db.find(DataSource,query,sort=[('id',1)],limit=200)]


@router.post('/api/management/sources',status_code=201)
@router.post('/api/admin/sources',status_code=201,dependencies=[Depends(admin)],include_in_schema=False)
def create_source(body:SourceInput,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    road(db,body.segment_id,body.direction,user);url_valid(body.url);validate_credentials(body)
    row=DataSource(**body.model_dump(),created_by=user.id,signature=signature(body),history=[event(user,'source_created')],
                   versions=[{'version':1,**body.model_dump()}])
    db.add(row);db.commit();return source_data(row)


@router.patch('/api/management/sources/{ident}')
@router.patch('/api/admin/sources/{ident}',dependencies=[Depends(admin)],include_in_schema=False)
def edit_source(ident:int,body:SourceEdit,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    source=managed_source(db,ident,user);road(db,body.segment_id,body.direction,user);url_valid(body.url);validate_credentials(body,source)
    fields=body.model_dump(exclude={'revision'})
    version=source.version+1
    updates={**fields,'signature':signature(body),'active':False,'tested':False,'connection_state':'unknown',
             'version':version,'versions':[*source.versions,{'version':version,**fields}], 'last_error':None,'last_received_at':None}
    return source_data(changed(db,DataSource,source,body.revision,updates,event(user,'source_reconfigured',version=version)))


def mapped_reading(source,raw):
    from .business_common import utc
    data={target:raw[field] for target,field in source.mapping.items() if field in raw and raw[field] not in ('',None)}
    if not {'observed_at','segment_id','direction'}<=data.keys():raise ValueError('Thiếu thời gian, tuyến hoặc chiều đường')
    at=utc(data['observed_at'])
    if at>now():raise ValueError('Thời gian quan sát nằm ở tương lai')
    if int(data['segment_id'])!=source.segment_id or data['direction']!=source.direction:raise ValueError('Dữ liệu khác tuyến hoặc chiều đường')
    metrics={}
    for field,maximum in (('count',100000),('speed_kmh',200),('score',1)):
        if field not in data:continue
        value=float(data[field])
        if field=='speed_kmh':
            unit=source.units.get(field,'km/h')
            if unit=='m/s':value*=3.6
            elif unit!='km/h':raise ValueError('Đơn vị vận tốc không được hỗ trợ')
        if not math.isfinite(value) or not 0<=value<=maximum:raise ValueError('Chỉ số ngoài giới hạn hợp lệ')
        if field=='count' and value!=int(value):raise ValueError('Số phương tiện phải là số nguyên')
        if field=='speed_kmh' and not source.speed_verified:continue
        metrics[field]=int(value) if field=='count' else value
    if 'state' in data:
        if data['state'] not in ('FREE','SLOW','JAM'):raise ValueError('Trạng thái giao thông không hợp lệ')
        if source.state_verified:metrics['state']=data['state']
    if 'density' in data:
        if data['density'] not in ('LOW','NORMAL','HIGH'):raise ValueError('Mật độ không hợp lệ')
        metrics['density']=data['density']
    if 'count' in metrics and source.count_method=='crossings':
        metrics['count_kind']='crossings'
        if 'interval_seconds' in data:
            interval=float(data['interval_seconds'])
            if not math.isfinite(interval) or not 1<=interval<=86400:raise ValueError('Khoảng đếm phương tiện không hợp lệ')
            metrics.update(interval_seconds=interval,flow_per_minute=metrics['count']*60/interval)
    elif 'count' in metrics:metrics['count_kind']='occupancy'
    if not metrics:raise ValueError('Chưa có chỉ số hợp lệ sau ánh xạ và kiểm tra phương pháp đo')
    return {'observed_at':at.isoformat(),'segment_id':source.segment_id,'direction':source.direction,'metrics':metrics}


@router.put('/api/management/sources/{ident}/mapping')
@router.put('/api/admin/sources/{ident}/mapping',dependencies=[Depends(admin)],include_in_schema=False)
def mapping(ident:int,body:MappingInput,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    source=managed_source(db,ident,user)
    if source.kind=='camera':raise HTTPException(422,'Nguồn hình ảnh không có bảng ánh xạ số liệu.')
    units=body.units
    if units.get('speed_kmh','km/h') not in ('km/h','m/s'):raise HTTPException(422,'Đơn vị vận tốc không được hỗ trợ.')
    candidate=replace(source,mapping=body.mapping,units=units)
    preview=None
    if body.sample is not None:
        try:preview=mapped_reading(candidate,body.sample)
        except (ValueError,TypeError,HTTPException,OverflowError):raise HTTPException(422,'Bản ghi mẫu không đạt. Kiểm tra thời gian, tuyến, chiều, đơn vị và chỉ số.') from None
    if not body.confirmed:return {'preview':preview,'saved':False,'revision':source.revision}
    version=source.version+1
    value=changed(db,DataSource,source,body.revision,{'mapping':body.mapping,'units':units,'active':False,'tested':False,
        'connection_state':'unknown','last_received_at':None,'last_error':None,
        'version':version,'versions':[*source.versions,{'version':version,'mapping':body.mapping,'units':units}]},event(user,'source_mapping_changed',version=version))
    return {**source_data(value),'preview':preview,'saved':True}


class SourceTest(Revision):
    sample: dict | None = None


@router.post('/api/management/sources/{ident}/test')
@router.post('/api/admin/sources/{ident}/test',dependencies=[Depends(admin)],include_in_schema=False)
async def test_source(ident:int,body:SourceTest,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    source=managed_source(db,ident,user);road(db,source.segment_id,source.direction)
    if not source.authorized:raise HTTPException(409,'Nguồn dữ liệu chưa đủ điều kiện hoạt động.')
    preview=None
    if source.kind=='file':
        if not source.mapping or body.sample is None:raise HTTPException(422,'Cần ánh xạ và một bản ghi mẫu để kiểm tra nguồn tệp.')
        try:preview=mapped_reading(source,body.sample)
        except (ValueError,TypeError,HTTPException,OverflowError):raise HTTPException(422,'Bản ghi mẫu chưa đúng ánh xạ hoặc không có chỉ số hợp lệ.') from None
    else:
        raw,mime=await source_request(source,head=source.kind=='camera')
        if source.kind=='camera':
            if mime not in CAMERA_TYPES[source.format]:raise HTTPException(422,'Nguồn camera chưa trả định dạng ảnh hoặc video được hỗ trợ.')
        else:
            rows=decode_rows(raw,source.format)
            if not rows:raise HTTPException(422,'Nguồn chưa có bản ghi mẫu để kiểm tra ánh xạ.')
            try:preview=mapped_reading(source,rows[0])
            except (ValueError,TypeError,HTTPException,OverflowError):raise HTTPException(422,'Dữ liệu nguồn chưa phù hợp ánh xạ.') from None
    value=changed(db,DataSource,source,body.revision,{'tested':True,'connection_state':'ready','checked_at':stamp(),'last_error':None},event(user,'source_tested'))
    return {**source_data(value),'preview':preview}


@router.post('/api/management/sources/{ident}/toggle')
@router.post('/api/admin/sources/{ident}/toggle',dependencies=[Depends(admin)],include_in_schema=False)
def toggle_source(ident:int,body:Toggle,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    source=managed_source(db,ident,user)
    if body.active:
        road(db,source.segment_id,source.direction)
        if not source.authorized or not source.tested or source.kind!='camera' and not source.mapping:
            raise HTTPException(409,'Nguồn dữ liệu chưa đủ điều kiện hoạt động. Kiểm tra kết nối và ánh xạ trước.')
    value=changed(db,DataSource,source,body.revision,{'active':body.active,'next_poll_at':None},event(user,'source_enabled' if body.active else 'source_disabled'))
    return source_data(value)


def decode_rows(raw,format):
    try:
        text=raw.decode('utf-8-sig')
        rows=json.loads(text) if format=='json' else list(csv.DictReader(io.StringIO(text)))
        if isinstance(rows,dict):rows=rows.get('records',[])
        if not isinstance(rows,list) or len(rows)>5000 or any(not isinstance(row,dict) for row in rows):raise ValueError()
        return rows
    except (UnicodeError,ValueError,csv.Error):raise HTTPException(422,'Tệp cần UTF-8, đúng định dạng JSON/CSV và tối đa 5.000 dòng.') from None


def mirror_forecast_sample(db,record):
    # Only feed measured features for the direction supported by the existing models.
    if record.direction!='forward' or not {'score','count','density'}<=record.metrics.keys():return
    key=f'source:{record.sample_key}'
    if db.find_one(TrafficSample,{'sample_key':key}):return
    sample=TrafficSample(sample_key=key,segment_id=record.segment_id,observed_at=record.observed_at,
        score=record.metrics['score'],count=record.metrics['count'],density=record.metrics['density'],source='source')
    try:db.add(sample);db.commit()
    except DuplicateKeyError:db.rollback()


def receive(db,source,rows):
    from .managed_rules import evaluate_rules
    current=get_record(db,DataSource,source.id)
    if not current.active or not current.tested or current.version!=source.version:
        raise HTTPException(409,'Nguồn đã tắt hoặc cấu hình đã thay đổi. Dữ liệu chưa được tiếp nhận.')
    road(db,source.segment_id,source.direction)
    accepted=rejected=duplicates=0;errors=[];last=None
    for number,raw in enumerate(rows,1):
        try:data=mapped_reading(source,raw)
        except (ValueError,TypeError,HTTPException,OverflowError):
            rejected+=1
            if len(errors)<20:errors.append({'row':number,'reason':'Sai thời gian, tuyến/chiều, đơn vị hoặc chỉ số không hợp lệ.'})
            continue
        key=fingerprint([source.id,data['segment_id'],data['direction'],data['observed_at']])
        record=db.find_one(RoadReading,{'sample_key':key})
        if record:
            duplicates+=1
        else:
            record=RoadReading(**data,sample_key=key,source_id=source.id,source_version=source.version)
            try:db.add(record);db.commit()
            except DuplicateKeyError:
                db.rollback()
                record=db.find_one(RoadReading,{'sample_key':key})
                if record is None:raise
                duplicates+=1
            else:accepted+=1
        mirror_forecast_sample(db,record)
        if record.source_version==source.version:
            last=max(last or record.observed_at,record.observed_at)
    receipt=SourceReceipt(source_id=source.id,source_version=source.version,accepted=accepted,rejected=rejected,duplicates=duplicates,errors=errors)
    db.add(receipt);db.commit()
    updates={'connection_state':'receiving' if last else 'error','checked_at':stamp(),
             'last_error':None if last else 'Không có bản ghi hợp lệ cho cấu hình hiện tại.'}
    db.database.data_sources.update_one({'_id':source.id,'version':source.version},{'$set':updates})
    if last:
        db.database.data_sources.update_one({'_id':source.id,'version':source.version,
            '$or':[{'last_received_at':None},{'last_received_at':{'$lt':last}}]}, {'$set':{'last_received_at':last}})
    if last:
        latest=db.find_one(RoadReading,{'source_id':source.id,'observed_at':last})
        if latest:evaluate_rules(db,latest)
    if rejected or not last:
        log_event(db,None,'source_rows_rejected',f'data_sources:{source.id}; receipt:{receipt.id}',
                  level='warning',service='ingestion')
    return serialize(receipt)


class RowsInput(Input):
    rows: list[dict] = Field(max_length=5000)


@router.post('/api/management/sources/{ident}/receive')
@router.post('/api/admin/sources/{ident}/receive',dependencies=[Depends(admin)],include_in_schema=False)
def receive_json(ident:int,body:RowsInput,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    return receive(db,managed_source(db,ident,user),body.rows)


@router.post('/api/management/sources/{ident}/upload')
@router.post('/api/admin/sources/{ident}/upload',dependencies=[Depends(admin)],include_in_schema=False)
async def receive_file(ident:int,file:UploadFile=File(...),user=Depends(permit('sources.manage')),db=Depends(get_db)):
    source=managed_source(db,ident,user)
    if source.kind!='file':raise HTTPException(422,'Chỉ nhập tệp cho nguồn có loại Tệp lịch sử.')
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise HTTPException(413,'Tệp vượt giới hạn 2 MB.')
    return receive(db,source,decode_rows(raw,source.format))


@router.get('/api/management/sources/{ident}/receipts')
@router.get('/api/admin/sources/{ident}/receipts',dependencies=[Depends(admin)],include_in_schema=False)
def receipts(ident:int,start:str|None=None,end:str|None=None,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    managed_source(db,ident,user);query={'source_id':ident};dates=period(start,end)
    if dates:query['received_at']=dates
    return [serialize(r) for r in db.find(SourceReceipt,query,sort=[('id',-1)],limit=200)]


@router.post('/api/management/sources/{ident}/poll')
@router.post('/api/admin/sources/{ident}/poll',dependencies=[Depends(admin)],include_in_schema=False)
async def poll(ident:int,user=Depends(permit('sources.manage')),db=Depends(get_db)):
    source=managed_source(db,ident,user)
    if source.kind!='api' or not source.active:raise HTTPException(409,'Chỉ nhận trực tiếp từ nguồn dịch vụ đang bật.')
    try:
        raw,_=await source_request(source)
        return receive(db,source,decode_rows(raw,source.format))
    except HTTPException:
        db.database.data_sources.update_one({'_id':source.id},{'$set':{'connection_state':'error','last_error':'Mất kết nối hoặc dữ liệu nguồn chưa hợp lệ.','checked_at':stamp()}})
        raise


@router.get('/api/management/cameras/{ident}/preview')
async def camera_preview(ident:int,user=Depends(permit('monitor.camera')),db=Depends(get_db)):
    from fastapi.responses import Response
    source=managed_source(db,ident,user)
    road(db,source.segment_id,source.direction,user)
    if source.kind!='camera' or not source.active or not source.tested:
        raise HTTPException(404,'Chưa có nguồn camera phù hợp.')
    raw,mime=await source_request(source)
    if mime not in CAMERA_TYPES[source.format] or not raw:raise HTTPException(502,'Mất kết nối nguồn dữ liệu hoặc định dạng hình ảnh chưa phù hợp.')
    return Response(raw,media_type=mime,headers={'Cache-Control':'private, no-store'})
