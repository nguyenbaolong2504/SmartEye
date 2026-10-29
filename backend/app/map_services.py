"""Bounded, cached OSM services. No public Nominatim autocomplete is used."""
import asyncio
import gzip
import hashlib
import json
import math
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from .config import DATA

router = APIRouter(prefix='/api/map', tags=['Street map'])
_cache = OrderedDict()
_lock = threading.Lock()
_reservations = {}
_roads_busy = threading.Lock()
ATTRIBUTION = '© OpenStreetMap contributors · ODbL'


def settings():
    return {
        'osm_available': os.getenv('OSM_ENABLED', 'true').lower() == 'true',
        'osm_tile_url': os.getenv('OSM_TILE_URL', 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'),
        'osm_attribution': ATTRIBUTION,
        'address_search_available': bool(os.getenv('PHOTON_URL', 'https://photon.komoot.io').strip()),
    }


async def fetch_json(url, *, params=None, data=None, service='photon'):
    # One process-wide reservation queue, rather than one limit per visitor.
    with _lock:
        clock = time.monotonic()
        ready = max(clock, _reservations.get(service, 0))
        if ready-clock > 3:
            raise HTTPException(503, 'Dịch vụ bản đồ đang bận. Vui lòng thử lại sau ít giây.')
        _reservations[service] = ready + (2 if service == 'overpass' else .6)
    await asyncio.sleep(max(0, ready-time.monotonic()))
    headers = {'User-Agent': os.getenv('OSM_USER_AGENT', 'SmartEye/1.0 (+https://github.com/nguyenbaolong2504/SmartEye)'),
               'Accept': 'application/json', 'Accept-Language': 'vi,en;q=0.7'}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(22,connect=6) if service == 'overpass' else 12, follow_redirects=False) as client:
            async with client.stream('POST' if data is not None else 'GET', url, params=params, data=data, headers=headers) as response:
                if response.status_code == 429:
                    raise HTTPException(503, 'Nguồn bản đồ đang giới hạn truy cập. Vui lòng thử lại sau.')
                if response.status_code != 200:
                    if service=='overpass':
                        raise HTTPException(503,'Nguồn mạng đường OSM đang bận hoặc chưa sẵn sàng. Giữ nguyên ghim và thử lại sau ít phút.')
                    raise HTTPException(502, 'Nguồn bản đồ chưa trả được dữ liệu. Vui lòng thử lại hoặc chọn ghim trên bản đồ.')
                chunks=[];size=0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > (28_000_000 if service == 'overpass' else 1_000_000):
                        raise HTTPException(422, 'Vùng tìm kiếm quá lớn. Hãy chọn hai điểm gần hơn.')
                    chunks.append(chunk)
                return json.loads(b''.join(chunks))
    except httpx.TimeoutException:
        raise HTTPException(504, 'Nguồn bản đồ phản hồi chậm. Vui lòng thử lại sau.') from None
    except (httpx.RequestError, ValueError, TypeError):
        raise HTTPException(502, 'Không đọc được dữ liệu từ nguồn bản đồ.') from None


def _address(feature):
    prop=feature.get('properties', {});point=feature.get('geometry', {}).get('coordinates', [])
    if len(point)<2: return None
    lng,lat=map(float,point[:2])
    if not (math.isfinite(lat) and math.isfinite(lng) and 20.5<=lat<=21.5 and 105.2<=lng<=106.2): return None
    street=' '.join(str(prop[k]) for k in ('housenumber','street') if prop.get(k))
    parts=list(dict.fromkeys(str(v) for v in [prop.get('name'),street,prop.get('locality'),prop.get('district'),prop.get('city'),prop.get('state')] if v))
    name=', '.join(parts)[:240] or f'{lat:.6f}, {lng:.6f}'
    return {'id':f"{prop.get('osm_type','')}{prop.get('osm_id','')}-{lat}-{lng}", 'name':name,
            'lat':lat,'lng':lng,'accuracy':'house' if prop.get('housenumber') else 'street' if prop.get('street') or prop.get('osm_key')=='highway' else 'place',
            'source':'photon'}


@router.get('/places')
async def find_places(q: str=Query(min_length=3,max_length=240)):
    base=os.getenv('PHOTON_URL','https://photon.komoot.io').strip().rstrip('/')
    if not settings()['osm_available'] or not base:
        raise HTTPException(503,'Tìm địa chỉ chưa được bật. Bạn có thể chọn vị trí trên bản đồ.')
    key=q.strip().casefold()
    if len(key)<3: raise HTTPException(422,'Nhập ít nhất 3 ký tự địa chỉ.')
    with _lock:
        cached=_cache.get(key)
        if cached and cached[0]>time.monotonic(): return cached[1]
    output=await fetch_json(base+'/api/',params={'q':q.strip(),'limit':7,'bbox':'105.2,20.5,106.2,21.5','lat':21.03,'lon':105.82})
    if not isinstance(output,dict) or not isinstance(output.get('features'),list):
        raise HTTPException(502,'Nguồn địa chỉ trả dữ liệu không hợp lệ.')
    rows=[];seen=set()
    try:
        for feature in output['features'][:30]:
            row=_address(feature)
            if row and row['id'] not in seen: rows.append(row);seen.add(row['id'])
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(502,'Nguồn địa chỉ trả dữ liệu không hợp lệ.') from None
    result={'places':rows[:7],'attribution':ATTRIBUTION,'notice':'Chọn kết quả rồi kiểm tra ghim. Dữ liệu có thể thiếu số nhà/ngõ; ghim trên bản đồ xác định vị trí mong muốn.'}
    with _lock:
        _cache[key]=(time.monotonic()+300,result)
        _cache.move_to_end(key)
        while len(_cache)>256: _cache.popitem(last=False)
    return result


def road_bounds(origin,destination):
    from .graph_search import haversine
    if haversine(origin,destination)>20:
        raise HTTPException(422,'Bản thử nghiệm hỗ trợ hai điểm cách nhau tối đa 20 km trong khu vực Hà Nội.')
    south=max(20.5,math.floor((min(origin[0],destination[0])-.018)/.02)*.02)
    west=max(105.2,math.floor((min(origin[1],destination[1])-.018)/.02)*.02)
    north=min(21.5,math.ceil((max(origin[0],destination[0])+.018)/.02)*.02)
    east=min(106.2,math.ceil((max(origin[1],destination[1])+.018)/.02)*.02)
    if (north-south)*(east-west)>.07:
        raise HTTPException(422,'Vùng đường cần tải quá lớn. Hãy chọn hành trình ngắn hơn.')
    return tuple(round(x,5) for x in (south,west,north,east))


async def load_roads(bounds):
    endpoint=os.getenv('OVERPASS_URL','https://overpass-api.de/api/interpreter').strip()
    key=hashlib.sha256((endpoint+repr(bounds)+'v1').encode()).hexdigest()
    folder=DATA/'osm-cache';path=folder/(key+'.json.gz')
    if path.is_file() and time.time()-path.stat().st_mtime<6*3600:
        try:
            with gzip.open(path,'rt',encoding='utf-8') as stream: return json.load(stream)
        except (OSError,ValueError,EOFError): pass
    if not _roads_busy.acquire(blocking=False):
        raise HTTPException(503,'Đang tải mạng đường cho một yêu cầu khác. Vui lòng thử lại sau ít giây.')
    try:
        bbox=','.join(map(str,bounds))
        query=f'''[out:json][timeout:25][maxsize:33554432];
way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|track|pedestrian)$"]({bbox})->.roads;
rel(bw.roads)["type"="restriction"]->.restrictions;
(.roads;.restrictions;node(w.roads););out body qt;'''
        endpoints=[endpoint]
        fallback=os.getenv('OVERPASS_FALLBACK_URL','https://overpass.private.coffee/api/interpreter').strip()
        if fallback and fallback!=endpoint: endpoints.append(fallback)
        for index,url in enumerate(endpoints):
            try:
                result=await fetch_json(url,data={'data':query},service='overpass')
                break
            except HTTPException as exc:
                if index==len(endpoints)-1 or exc.status_code not in (502,503,504): raise
        if not isinstance(result,dict) or result.get('remark') or not isinstance(result.get('elements'),list):
            raise HTTPException(502,'Nguồn đường chưa hoàn tất vùng dữ liệu. Vui lòng thử lại.')
        if len(result['elements'])>120000:
            raise HTTPException(422,'Mạng đường quá lớn cho bản thử nghiệm. Hãy chọn hành trình ngắn hơn.')
        folder.mkdir(exist_ok=True)
        # Cache contains public road data/bounds, not address queries or user identity.
        try:
            with gzip.open(path,'wt',encoding='utf-8') as stream: json.dump(result,stream,separators=(',',':'))
            files=sorted(folder.glob('*.json.gz'),key=lambda file:file.stat().st_mtime)
            for old in files[:-8]: old.unlink(missing_ok=True)
        except OSError: pass  # A full/read-only disk must not invalidate a computed route.
        return result
    finally:
        _roads_busy.release()
