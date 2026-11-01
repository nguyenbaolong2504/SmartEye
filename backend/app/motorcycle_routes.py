"""Motorcycle candidates on a preprocessed OSM network, with bounded I/O.

Never substitute driving/bicycle routing for motorcycle access. Cache only
reference geometry/ETA; user weights and traffic estimates are applied afresh.
"""
import asyncio
import copy
import math
import os
import threading
import time

import httpx
from fastapi import HTTPException

_cache = {}
_inflight = {}
_next_request = {}
_backoff = {}
_guard = threading.Lock()
CACHE_SECONDS = 600
REQUEST_SECONDS = 9
REQUEST_SPACING = 1.
MAX_QUEUE_SECONDS = 2.


def _distance_m(a, b):
    lat1, lat2 = map(math.radians, (a[0], b[0]))
    dlat, dlon = lat2-lat1, math.radians(b[1]-a[1])
    value = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 12742000*math.asin(min(1, math.sqrt(value)))


def _positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError('invalid route metric')
    return number


def _normalize_trip(trip, req):
    from .routing import decode_polyline
    if not isinstance(trip, dict):
        raise ValueError('missing trip')
    # A server can ignore hard exclusions. Verify its returned highway flags,
    # including endpoints (which the exclusion option alone does not protect).
    if trip.get('status') != 0 or trip.get('units') != 'kilometers':
        raise ValueError('invalid trip')
    if trip['summary'].get('has_highway') is not False:
        raise ValueError('highway not excluded')
    seconds = _positive(trip['summary']['time'])
    meters = _positive(trip['summary']['length'])*1000
    geometry, steps = [], []
    for leg in trip['legs']:
        if leg['summary'].get('has_highway') is not False:
            raise ValueError('highway not excluded')
        if not isinstance(leg['shape'], str) or len(leg['shape']) > 500000:
            raise ValueError('invalid shape')
        points = decode_polyline(leg['shape'], precision=6)
        if len(points) < 2 or len(points) > 50000:
            raise ValueError('invalid shape')
        if any(not (-90 <= p[0] <= 90 and -180 <= p[1] <= 180) for p in points):
            raise ValueError('invalid coordinates')
        geometry.extend(points if not geometry or geometry[-1] != points[0] else points[1:])
        for maneuver in leg['maneuvers']:
            if maneuver.get('travel_type') != 'motorcycle':
                raise ValueError('wrong vehicle profile')
            start, end = maneuver['begin_shape_index'], maneuver['end_shape_index']
            if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end < len(points):
                raise ValueError('invalid maneuver geometry')
            length, duration = float(maneuver['length'])*1000, float(maneuver['time'])
            if not math.isfinite(length+duration) or min(length, duration) < 0:
                raise ValueError('invalid maneuver metric')
            steps.append({'name':next(iter(maneuver.get('street_names', [])), ''),
                          'duration':duration, 'distance':length,
                          'geometry':{'coordinates':[[p[1], p[0]] for p in points[start:end+1]]}})
    if not geometry or not steps:
        raise ValueError('empty route')
    snaps = [{'location':[p[1], p[0]], 'distance':_distance_m([pin.lat, pin.lng], p)}
             for pin, p in zip((req.origin, req.destination), (geometry[0], geometry[-1]))]
    # Valhalla's locations echo the input pins, not the snapped route endpoints.
    if any(p['distance'] > 200 for p in snaps):
        raise HTTPException(422, 'Ghim cách đường xe máy quá xa. Chọn lại lối vào đường, trong 200 m.')
    return {'duration':seconds, 'distance':meters,
            'geometry':{'coordinates':[[p[1], p[0]] for p in geometry]},
            'legs':[{'steps':steps}], 'waypoints':snaps}


def _normalize(raw, req):
    routes, seen = [], set()
    distant = False
    # Fail closed when the upstream reports ignored/unsupported options.
    if not isinstance(raw, dict) or raw.get('warnings'):
        raise HTTPException(502, 'Nguồn bản đồ chưa xác nhận được đường phù hợp cho xe máy. Vui lòng thử lại sau.')
    alternates = raw.get('alternates') or []
    if not isinstance(alternates, list):
        raise HTTPException(502, 'Nguồn tìm đường trả kết quả chưa đầy đủ. Vui lòng thử lại.')
    trips = [raw.get('trip'), *(a.get('trip') for a in alternates[:2] if isinstance(a, dict))]
    for trip in trips:
        try:
            route = _normalize_trip(trip, req)
            shape = tuple(tuple(p) for p in route['geometry']['coordinates'])
            if shape not in seen:
                seen.add(shape)
                routes.append(route)
        except HTTPException:
            distant = True
        except (KeyError, TypeError, ValueError, IndexError, OverflowError, AttributeError):
            continue
    if not routes:
        if distant:
            raise HTTPException(422, 'Ghim cách đường xe máy quá xa. Chọn lại lối vào đường, trong 200 m.')
        raise HTTPException(502, 'Chưa xác nhận được tuyến xe máy tránh cao tốc. Hãy kiểm tra lại ghim hoặc thử lại sau.')
    return {'code':'Ok', 'routes':routes, 'waypoints':routes[0]['waypoints']}


async def _fetch(base, req):
    with _guard:
        now = time.monotonic()
        if _backoff.get(base, 0) > now:
            raise HTTPException(503, 'Nguồn tìm đường đang bận. Vui lòng thử lại sau vài giây.')
        wait = max(0., _next_request.get(base, 0)-now)
        if wait > MAX_QUEUE_SECONDS:
            raise HTTPException(503, 'Có nhiều lượt tìm đường. Vui lòng thử lại sau vài giây.')
        _next_request[base] = now+wait+REQUEST_SPACING
    if wait:
        await asyncio.sleep(wait)
    body = {'locations':[{'lat':p.lat, 'lon':p.lng, 'radius':200,
                          'search_filter':{'max_road_class':'primary'}} for p in (req.origin, req.destination)],
            'costing':'motorcycle', 'costing_options':{'motorcycle':{
                'exclude_highways':True, 'use_highways':0, 'use_tolls':0, 'use_trails':0,
                'ignore_restrictions':False, 'ignore_oneways':False, 'ignore_access':False}},
            'alternates':2, 'units':'kilometers', 'language':'en-US', 'shape_format':'polyline6'}
    try:
        # Absolute deadline also bounds a server that trickles response chunks.
        async def request():
            async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3),
                                         headers={'User-Agent':'SmartEye/1.0 (educational routing)'}) as client:
                return await client.post(f'{base}/route', json=body)
        response = await asyncio.wait_for(request(), timeout=REQUEST_SECONDS)
        if response.status_code in (400, 404):
            raise HTTPException(404, 'Không tìm thấy tuyến xe máy cho hai ghim này. Thử đặt ghim sát lối vào đường.')
        if response.status_code == 429:
            raise HTTPException(429, 'Nguồn bản đồ đang giới hạn lượt tìm. Vui lòng chờ vài giây rồi thử lại.')
        if response.status_code >= 400:
            raise HTTPException(502, 'Nguồn tìm đường xe máy chưa sẵn sàng. Vui lòng thử lại sau.')
        raw = response.json()
    except (httpx.TimeoutException, asyncio.TimeoutError):
        with _guard:
            _backoff[base] = time.monotonic()+10
        raise HTTPException(504, 'Chưa nhận được tuyến xe máy. Vui lòng thử lại sau vài giây.') from None
    except (httpx.RequestError, ValueError):
        with _guard:
            _backoff[base] = time.monotonic()+10
        raise HTTPException(502, 'Không kết nối được nguồn tìm đường xe máy. Vui lòng thử lại sau.') from None
    except HTTPException as exc:
        if exc.status_code in (429, 502):
            with _guard:
                _backoff[base] = time.monotonic()+10
        raise
    return _normalize(raw, req)


async def candidates(req):
    base = os.getenv('MOTORCYCLE_ROUTING_URL', 'https://valhalla1.openstreetmap.de').rstrip('/')
    coords = tuple(round(v, 6) for p in (req.origin, req.destination) for v in (p.lat, p.lng))
    key = (base, coords)
    flight_key = (asyncio.get_running_loop(), key)
    with _guard:
        cached = _cache.get(key)
        if cached and time.monotonic()-cached[0] < CACHE_SECONDS:
            return copy.deepcopy(cached[1])
        task = _inflight.get(flight_key)
        if task is None:
            async def load():
                try:
                    raw = await _fetch(base, req)
                    with _guard:
                        if len(_cache) >= 128:
                            _cache.pop(next(iter(_cache)))
                        _cache[key] = (time.monotonic(), raw)
                    return raw
                finally:
                    with _guard:
                        _inflight.pop(flight_key, None)
            task = asyncio.create_task(load())
            # Retrieve exceptions even if all waiting clients disconnected.
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            _inflight[flight_key] = task
    return copy.deepcopy(await asyncio.shield(task))
