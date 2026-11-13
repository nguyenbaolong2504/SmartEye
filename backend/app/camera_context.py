"""As-of public road notices and regional weather, separate from demo overrides."""
import hashlib
import math
import threading
import time
from datetime import datetime, timedelta, timezone
import httpx
from .db import now
from .history import LOCAL

FEATURES=('rain_mm','visibility_km','wind_kmh','weather_known','accident','roadwork',
          'obstruction','flood','wet_surface','events_checked')
KINDS=('accident','roadwork','obstruction','flood')
_cache={}
_lock=threading.Lock()


def vector(context):
    weather=context['weather'];road=context['road']
    return [float(weather.get('rain_mm') or 0),float(weather.get('visibility_km') or 0),
            float(weather.get('wind_kmh') or 0),float(weather['known']),
            *[float(road.get(kind,False)) for kind in KINDS],
            float(road.get('wet_surface',False)),float(road['checked'])]


def synthetic_context(sid,at):
    """Repeatable two-hour conditions used ONLY to teach the synthetic sandbox."""
    day=at.astimezone(LOCAL)
    digest=hashlib.sha256(f'context-v1:{sid}:{day.date()}:{day.hour//2}'.encode()).digest()
    rain=(0,0,0,.8,4.,12.)[digest[0]%6]
    kind=(None,None,None,None,*KINDS)[digest[1]%8]
    known_weather=digest[2]%7!=0;checked=digest[3]%7!=0
    weather={'known':known_weather,'rain_mm':rain,'visibility_km':.5 if digest[4]%12==0 else 10.,
             'wind_kmh':float(5+digest[5]%30),'source':'synthetic'}
    road={'checked':checked,**{key:key==kind for key in KINDS},'wet_surface':rain>0,'source':'synthetic'}
    return {'weather':weather,'road':road,'is_demo':True}


def training_row(row,sid):
    """Generate condition-affected traffic labels; no claim of physical calibration."""
    context=synthetic_context(sid,row['at']);weather=context['weather'];road=context['road']
    impact=min(.26,weather['rain_mm']*.018)+(.12 if weather['visibility_km']<1 else 0)
    impact+=sum(road[kind]*weight for kind,weight in zip(KINDS,(.28,.18,.22,.38)))
    pressure=min(1.,row['score']+impact*.6)
    free_speed=32+sid%4*3
    ratio=max(.03,row['speed_kmh']/free_speed-impact)
    value=dict(row,score=pressure,count=max(0,round(row['count']+impact*15)),speed_kmh=ratio*free_speed)
    label='JAM' if ratio<.3 else 'SLOW' if ratio<.65 else 'FREE'
    # Missing is distinct from a known dry/unobstructed road. Labels retain true conditions.
    if not weather['known']:
        weather.update(rain_mm=None,visibility_km=None,wind_kmh=None)
    if not road['checked']:
        road.update({kind:False for kind in KINDS});road['wet_surface']=False
    return value,label,context


def _parse(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('Timestamp must include timezone')
    return at


def public_conditions(database,sid,issue,direction='forward'):
    road={'checked':True,**{key:False for key in KINDS},'wet_surface':False,
          'source':'published_warnings','notice_count':0,'as_of':issue.isoformat()}
    # Read the immutable, redacted publication, never private incident reports or draft fields.
    query={'public_snapshot.segment_id':sid,'public_snapshot':{'$ne':None},'status':{'$ne':'cancelled'}}
    for doc in database.traffic_warnings.find(query,{'public_snapshot':1}):
        snap=doc['public_snapshot']
        try:
            published=_parse(snap['published_at']);start=_parse(snap['start_at'])
            end=_parse(snap['end_at']) if snap.get('end_at') else max(start,published)+timedelta(hours=2)
            if published>issue or not start<=issue<end or snap.get('direction')!=direction:continue
        except (KeyError,ValueError,TypeError):continue
        kind=snap.get('kind')
        if kind in KINDS:road[kind]=True;road['notice_count']+=1
    return road


def weather_at(position,issue):
    unknown={'known':False,'source':'Open-Meteo','source_url':'https://open-meteo.com/',
             'rain_mm':None,'visibility_km':None,'wind_kmh':None,'at':None,
             'message':'Chưa lấy được thời tiết cho khu vực và mốc chạy thử này.'}
    if not position or not now()-timedelta(days=7)<=issue<=now()+timedelta(days=7):return unknown
    utc_issue=issue.astimezone(timezone.utc)
    key=(round(position[0],3),round(position[1],3),utc_issue.date().isoformat(),utc_issue.hour)
    with _lock:
        cached=_cache.get(key)
        if cached and cached[0]>time.monotonic():return dict(cached[1])
    result=unknown
    try:
        response=httpx.get('https://api.open-meteo.com/v1/forecast',params={
            'latitude':key[0],'longitude':key[1],'start_date':key[2],
            'end_date':key[2],'hourly':'precipitation,visibility,wind_speed_10m',
            'timezone':'GMT','timeformat':'unixtime'},timeout=httpx.Timeout(5.,connect=2.),follow_redirects=False)
        response.raise_for_status()
        hourly=response.json()['hourly']
        indices=[i for i,at in enumerate(hourly['time']) if issue.timestamp()-3600<at<=issue.timestamp()]
        if indices:
            i=indices[-1];rain,visibility,wind=[hourly[key][i] for key in ('precipitation','visibility','wind_speed_10m')]
            if all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in (rain,visibility,wind)):
                result={**unknown,'known':True,'rain_mm':round(rain,2),'visibility_km':round(visibility/1000,2),
                    'wind_kmh':round(wind,1),'at':datetime.fromtimestamp(hourly['time'][i],timezone.utc).isoformat(),
                    'retrieved_at':now().isoformat(),'position':list(key[:2]),
                    'message':'Thời tiết theo mô hình khu vực, không đo trực tiếp từ camera.'}
    except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError):pass
    with _lock:
        if len(_cache)>256:_cache.clear()
        _cache[key]=(time.monotonic()+(600 if result['known'] else 60),dict(result))
    return result


def resolve(database,segment,issue,overrides=None):
    """Unknown road coverage is not evidence of no incident; overrides never persist."""
    overrides=overrides or {}
    geometry=segment.geometry
    position=geometry[len(geometry)//2] if geometry else None
    road=public_conditions(database,segment.id,issue)
    weather_choice=overrides.get('weather','auto')
    if weather_choice=='auto':weather=weather_at(position,issue)
    else:
        rain,visibility={'dry':(0,10),'light':(1,8),'heavy':(12,2),'fog':(0,.3)}[weather_choice]
        weather={'known':True,'rain_mm':rain,'visibility_km':visibility,'wind_kmh':10.,
                 'source':'demo_override','at':issue.isoformat(),'message':'Thời tiết giả định do bạn chọn.'}
    road_choice=overrides.get('road_condition','auto');incident=overrides.get('incident','auto')
    if road_choice!='auto':
        for kind in ('roadwork','obstruction','flood'):road[kind]=kind==road_choice
    if incident!='auto':road['accident']=incident=='accident'
    road['wet_surface']=bool(weather['known'] and weather['rain_mm']>0) or road['flood']
    road['message']='Chỉ xét cảnh báo đã xác minh, đã công bố và có hiệu lực tại mốc chạy thử; không có cảnh báo chưa chắc không có sự cố.'
    if road_choice!='auto' or incident!='auto':
        road['source']='published_warnings_and_demo_override'
        road['message']='Kết hợp cảnh báo đã công bố với điều kiện giả định bạn chọn. Không phát hành cảnh báo mới.'
    return {'weather':weather,'road':road,'is_demo':True,'overrides':overrides,
            'reference_at':issue.isoformat(),'location_note':'Thời tiết và cảnh báo theo tuyến đang chọn; chưa xác minh cùng địa điểm, thời điểm với video minh họa.'}
