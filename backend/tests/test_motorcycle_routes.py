import asyncio
import copy
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from backend.app import motorcycle_routes as service
from backend.app.schemas import RouteRequest


def encode(points):
    result, previous = '', [0, 0]
    for point in points:
        for axis, value in enumerate(point):
            number = round(value*1e6)
            delta = number-previous[axis]
            previous[axis] = number
            delta = ~(delta << 1) if delta < 0 else delta << 1
            while delta >= 32:
                result += chr((32 | (delta & 31))+63)
                delta >>= 5
            result += chr(delta+63)
    return result


def payload():
    def trip(name, seconds, km, offset):
        points = [[21.03, 105.821], [21.031+offset, 105.825], [21.03, 105.829]]
        summary = {'time':seconds, 'length':km, 'has_highway':False}
        return {'status':0, 'units':'kilometers', 'summary':summary,
                'legs':[{'summary':copy.deepcopy(summary), 'shape':encode(points), 'maneuvers':[
                    {'street_names':[name], 'time':seconds, 'length':km, 'travel_type':'motorcycle',
                     'travel_mode':'drive', 'begin_shape_index':0, 'end_shape_index':2}]}]}
    return {'trip':trip('Kim Mã', 600, 4, 0),
            'alternates':[{'trip':trip('Đường tránh', 900, 2, .001)}]}


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    for state in (service._cache, service._inflight, service._next_request, service._backoff):
        state.clear()
    monkeypatch.setenv('MOTORCYCLE_ROUTING_URL', 'https://motorcycle.example.invalid')
    monkeypatch.setattr(service, 'REQUEST_SPACING', 0)
    yield
    for state in (service._cache, service._inflight, service._next_request, service._backoff):
        state.clear()


@pytest.fixture
def body():
    return {'origin':{'lat':21.03, 'lng':105.821}, 'destination':{'lat':21.03, 'lng':105.829},
            'mode':'TWO_WHEELER', 'provider':'auto', 'weights':{'time':1, 'distance':0}}


def mock_upstream(monkeypatch, data=None, status=200, handler=None):
    calls, real = [], httpx.AsyncClient
    async def handle(request):
        calls.append(request)
        if handler:
            return await handler(request)
        return httpx.Response(status, json=data if data is not None else payload())
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs:real(transport=transport, **kwargs))
    return calls


def test_motorcycle_fast_path_precise_geometry_access_and_cached_reranking(client, monkeypatch, body):
    calls = mock_upstream(monkeypatch)
    first = client.post('/api/routes/search', json=body)
    assert first.status_code == 200
    data = first.json()
    assert data['optimization']['scope'] == 'valhalla_candidates'
    assert data['optimization']['algorithm'] is None
    assert data['routes'][0]['name'] == 'Kim Mã'
    assert data['routes'][0]['geometry'] == [[21.03,105.821],[21.031,105.825],[21.03,105.829]]
    assert not data['is_demo'] and data['routes'][0]['unknown_share'] == 1
    assert all(snap['distance_km'] < .001 for snap in data['optimization']['snaps'])
    assert 'xe máy' in data['notice'] and 'Google' not in data['notice']
    second = client.post('/api/routes/search', json={**body,'weights':{'time':0,'distance':1}}).json()
    assert second['routes'][0]['name'] == 'Đường tránh'
    assert len(calls) == 1  # No Overpass download, OSRM driving, or bicycle request.
    sent = json.loads(calls[0].content)
    assert str(calls[0].url) == 'https://motorcycle.example.invalid/route'
    assert sent['costing'] == 'motorcycle'
    options = sent['costing_options']['motorcycle']
    assert options['exclude_highways'] is True
    assert all(options[k] is False for k in ('ignore_restrictions','ignore_oneways','ignore_access'))
    assert all(p['search_filter']['max_road_class'] == 'primary' and p['radius'] == 200 for p in sent['locations'])
    assert sent['alternates'] == 2 and sent['units'] == 'kilometers'
    assert 'departure_at' not in sent and 'name' not in sent['locations'][0]


@pytest.mark.parametrize('case,status', [('highway',502),('unknown',502),('wrong_vehicle',502),
                                        ('malformed',502),('null_summary',502),('null_leg',502),('no_trip',502),
                                        ('warnings',502),('distant',422),
                                        ('throttled',429),('no_route',404)])
def test_reject_unsafe_unverified_or_missing_motorcycle_routes(client, monkeypatch, body, case, status):
    data = payload()
    data['alternates'] = []
    trip = data['trip']
    if case == 'highway':trip['legs'][0]['summary']['has_highway'] = True
    if case == 'unknown':trip['summary'].pop('has_highway')
    if case == 'wrong_vehicle':trip['legs'][0]['maneuvers'][0]['travel_type'] = 'car'
    if case == 'malformed':trip['legs'][0]['shape'] = 'broken'
    if case == 'null_summary':trip['summary'] = None
    if case == 'null_leg':trip['legs'][0] = None
    if case == 'no_trip':data.pop('trip')
    if case == 'warnings':data['warnings'] = [{'code':208,'description':'Hard exclusions ignored'}]
    if case == 'distant':trip['legs'][0]['shape'] = encode([[21.05,105.821],[21.04,105.825],[21.03,105.829]])
    calls = mock_upstream(monkeypatch, data=data, status=429 if case == 'throttled' else 400 if case == 'no_route' else 200)
    response = client.post('/api/routes/search', json=body)
    assert response.status_code == status
    assert 'routes' not in response.json() and len(calls) == 1
    assert not service._cache


def test_unsafe_alternative_is_removed_without_inventing_another(client, monkeypatch, body):
    data = payload()
    data['alternates'][0]['trip']['summary']['has_highway'] = True
    mock_upstream(monkeypatch, data=data)
    response = client.post('/api/routes/search', json=body)
    assert response.status_code == 200
    assert len(response.json()['routes']) == 1


def test_future_traffic_is_recomputed_after_source_geometry_cache_hit(client, monkeypatch, body):
    from backend.app import routing
    calls = mock_upstream(monkeypatch)
    seen = []
    at = datetime.now(timezone.utc)+timedelta(days=1)
    def evidence(db, req, roads):
        seen.append(req.departure_at)
        return {road.id:SimpleNamespace(density='HIGH' if req.departure_at == at else 'LOW',source='forecast') for road in roads}
    monkeypatch.setattr(routing, 'route_evidence', evidence)
    peak = client.post('/api/routes/search', json={**body,'traffic_mode':'demo','departure_at':at.isoformat()})
    later = client.post('/api/routes/search', json={**body,'traffic_mode':'demo','departure_at':(at+timedelta(hours=1)).isoformat()})
    assert peak.status_code == later.status_code == 200
    assert peak.json()['routes'][0]['name'] == 'Đường tránh'
    assert later.json()['routes'][0]['name'] == 'Kim Mã'
    assert len(calls) == 1 and seen == [at,at+timedelta(hours=1)]


def test_simultaneous_searches_share_one_fetch_and_cache_is_not_mutable(monkeypatch, body):
    async def handler(request):
        await asyncio.sleep(.02)
        return httpx.Response(200, json=payload())
    calls = mock_upstream(monkeypatch, handler=handler)
    async def run():
        req = RouteRequest(**body)
        results = await asyncio.gather(*(service.candidates(req) for _ in range(3)))
        results[0]['routes'][0]['duration'] = 99999
        assert results[1]['routes'][0]['duration'] == 600
        assert (await service.candidates(req))['routes'][0]['duration'] == 600
    asyncio.run(run())
    assert len(calls) == 1 and not service._inflight


def test_absolute_deadline_and_short_backoff_prevent_repeat_long_waits(monkeypatch, body):
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=payload())
    calls = mock_upstream(monkeypatch, handler=handler)
    monkeypatch.setattr(service, 'REQUEST_SECONDS', .02)
    async def run():
        req = RouteRequest(**body)
        started = time.monotonic()
        with pytest.raises(HTTPException) as first:
            await service.candidates(req)
        assert first.value.status_code == 504 and time.monotonic()-started < .5
        with pytest.raises(HTTPException) as second:
            await service.candidates(req)
        assert second.value.status_code == 503
    asyncio.run(run())
    assert len(calls) == 1 and not service._cache and not service._inflight


def test_expired_geometry_is_refetched_and_public_request_queue_is_bounded(monkeypatch, body):
    calls = mock_upstream(monkeypatch)
    req = RouteRequest(**body)
    asyncio.run(service.candidates(req))
    key = next(iter(service._cache))
    service._cache[key] = (time.monotonic()-601, service._cache[key][1])
    asyncio.run(service.candidates(req))
    assert len(calls) == 2
    service._cache.clear()
    service._next_request[key[0]] = time.monotonic()+3
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.candidates(req))
    assert exc.value.status_code == 503 and len(calls) == 2


def test_departure_comparison_shares_motorcycle_geometry(client, monkeypatch, body):
    calls = mock_upstream(monkeypatch)
    at = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    result = client.post('/api/routes/departures', json={**body,'departure_at':at})
    assert result.status_code == 200 and len(result.json()['options']) == 3
    assert len(calls) == 1
