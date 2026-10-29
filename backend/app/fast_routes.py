"""Bounded, cached OSRM candidates. No live-traffic or global A* claims."""
import asyncio
import copy
import os
import time
import unicodedata

import httpx
from fastapi import HTTPException
from .models import Segment

_cache={}
_locks={}


def clean(name):
    text=''.join(c for c in unicodedata.normalize('NFD',name.lower().replace('đ','d')) if not unicodedata.combining(c))
    return text.removeprefix('pho ').removeprefix('duong ').strip()


async def candidates(req):
    # Motorcycle access differs from driving; never substitute a bicycle profile.
    if req.mode!='DRIVE': raise HTTPException(422,'Nguồn tìm nhanh hiện hỗ trợ ô tô. Xe máy cần mạng OSM có quyền phương tiện.')
    base=os.getenv('OSRM_URL','https://router.project-osrm.org').rstrip('/')
    coords=f'{req.origin.lng:.6f},{req.origin.lat:.6f};{req.destination.lng:.6f},{req.destination.lat:.6f}'
    key=(base,coords)
    cached=_cache.get(key)
    if cached and time.monotonic()-cached[0]<600:return copy.deepcopy(cached[1])
    # Single flight for repeated identical requests. Locks are removed after use.
    lock=_locks.setdefault(key,asyncio.Lock())
    try:
        async with lock:
            cached=_cache.get(key)
            if cached and time.monotonic()-cached[0]<600:return copy.deepcopy(cached[1])
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(9,connect=4),headers={'User-Agent':'SmartEye/1.0 (educational routing)'}) as client:
                    response=await client.get(f'{base}/route/v1/driving/{coords}',params={
                        'overview':'full','geometries':'geojson','alternatives':'true','steps':'true','radiuses':'200;200'})
                if response.status_code==429:raise HTTPException(429,'Nguồn bản đồ đang giới hạn lượt tìm. Vui lòng chờ rồi thử lại.')
                if response.status_code>=400:raise HTTPException(502,'Nguồn tìm đường chưa sẵn sàng. Vui lòng thử lại.')
                raw=response.json()
            except httpx.TimeoutException:raise HTTPException(504,'Nguồn tìm đường phản hồi chậm. Vui lòng thử lại sau vài giây.') from None
            except (httpx.RequestError,ValueError):raise HTTPException(502,'Không kết nối được nguồn tìm đường.') from None
            if raw.get('code')!='Ok' or not raw.get('routes'):raise HTTPException(404,'Không tìm thấy đường cho hai ghim này. Thử đặt ghim sát lối vào đường.')
            if any(p.get('distance',201)>200 for p in raw.get('waypoints',[])):raise HTTPException(422,'Ghim cách đường ô tô quá xa. Chọn lại lối vào đường, trong 200 m.')
            if len(_cache)>=128:_cache.pop(next(iter(_cache)))
            _cache[key]=(time.monotonic(),raw)
            return copy.deepcopy(raw)
    finally:
        if not lock.locked():_locks.pop(key,None)


async def fast_routes(db,req):
    from .routing import route_evidence,rank_routes,normalized_weights
    raw=await candidates(req)
    roads=db.find(Segment,{'active':True})
    # Demo names intentionally map only to the user's selected simulated mode.
    eligible=roads if req.traffic_mode=='demo' else [s for s in roads if not s.is_demo]
    evidence=route_evidence(db,req,eligible)
    routes=[]
    for index,item in enumerate(raw['routes'][:3]):
        geometry=[[p[1],p[0]] for p in item['geometry']['coordinates']]
        steps=[s for leg in item.get('legs',[]) for s in leg.get('steps',[])]
        names=list(dict.fromkeys(s.get('name','') for s in steps if s.get('name')))
        seconds=float(item['duration']);distance=float(item['distance'])/1000
        known_km=high_km=exposure=0.;matches={}
        for step in steps:
            name=clean(step.get('name',''));length=float(step.get('distance',0))/1000
            if not name or length<=0:continue
            match=next((r for r in eligible if any(clean(alias)==name for alias in r.name.replace('–','-').split('-'))),None)
            observation=evidence.get(match.id) if match else None
            if observation is None:continue
            density=observation.density;known_km+=length
            risk={'LOW':.05,'NORMAL':.35,'HIGH':1.}[density];exposure+=risk*length
            high_km+=length if density=='HIGH' else 0
            # Only explicit synthetic mode adjusts the provider's reference ETA.
            if req.traffic_mode=='demo':seconds+=float(step.get('duration',0))*({'LOW':1.,'NORMAL':1.5,'HIGH':3.}[density]-1)
            step_geometry=[[p[1],p[0]] for p in step.get('geometry',{}).get('coordinates',[])]
            if match.id not in matches:matches[match.id]={'id':match.id,'name':match.name,'distance_km':0.,'density':density,
                'source':observation.source,'geometry':step_geometry,'is_demo':req.traffic_mode=='demo'}
            matches[match.id]['distance_km']+=length
        unknown=max(0,distance-known_km);exposure+=.5*unknown
        routes.append({'id':f'osm-fast-{index}','name':' → '.join(names[:5]) or f'Tuyến {index+1}',
            'duration_seconds':max(1,round(seconds)),'distance_km':round(distance,2),'risk':round(min(1,exposure/max(distance,.001)),3),
            'risk_exposure_km':exposure,'high_share':high_km/max(distance,.001),'unknown_share':min(1,unknown/max(distance,.001)),
            'geometry':geometry,'segments':list(matches.values()),'traffic_intervals':[]})
    routes=rank_routes(routes,req.weights)
    snaps=[{'label':label,'point':[p['location'][1],p['location'][0]],'distance_km':p['distance']/1000,'way_id':0}
           for label,p in zip(('origin','destination'),raw.get('waypoints',[]))]
    return routes,{'scope':'osrm_candidates','algorithm':None,'agreement':None,'primary_search':{},
        'normalized_weights':normalized_weights(req.weights),'references':{'time_seconds':min(r['duration_seconds'] for r in routes),
        'distance_km':min(r['distance_km'] for r in routes)},'snaps':snaps,
        'note':'Xếp hạng các tuyến OSRM cung cấp theo thời gian và khoảng cách; không chạy A* trên đồ thị nội bộ của OSRM.'}
