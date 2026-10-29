import copy
import httpx
import pytest
from backend.app import fast_routes as service


def payload():
    def route(seconds,meters,name):
        return {'duration':seconds,'distance':meters,'geometry':{'coordinates':[[105.821,21.03],[105.825,21.031],[105.829,21.03]]},
                'legs':[{'steps':[{'name':name,'duration':seconds,'distance':meters}]}]}
    return {'code':'Ok','routes':[route(600,4000,'Tuyến nhanh'),route(900,2000,'Tuyến ngắn')],
            'waypoints':[{'location':[105.821,21.03],'distance':4},{'location':[105.829,21.03],'distance':8}]}


def mock_upstream(monkeypatch,data=None,status=200):
    calls=[];real=httpx.AsyncClient
    def handle(request):calls.append(request);return httpx.Response(status,json=data if data is not None else payload())
    transport=httpx.MockTransport(handle)
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kwargs:real(transport=transport,**kwargs))
    service._cache.clear();service._locks.clear()
    return calls


def test_fast_routes_cache_geometry_and_recompute_weighting(client,monkeypatch,route_request):
    calls=mock_upstream(monkeypatch)
    body={**route_request,'provider':'auto','weights':{'time':1,'distance':0}}
    first=client.post('/api/routes/search',json=body)
    assert first.status_code==200
    data=first.json()
    assert data['optimization']['scope']=='osrm_candidates' and data['optimization']['algorithm'] is None
    assert data['routes'][0]['name']=='Tuyến nhanh'
    assert len(data['routes'][0]['geometry'])==3
    assert not data['is_demo'] and data['routes'][0]['unknown_share']==1
    body['weights']={'time':0,'distance':1}
    second=client.post('/api/routes/search',json=body).json()
    assert second['routes'][0]['name']=='Tuyến ngắn'
    assert len(calls)==1  # cached provider geometry, not cached user priorities
    assert calls[0].url.params['radiuses']=='200;200'


@pytest.mark.parametrize('case,status_code',[('throttled',429),('none',404),('distant',422)])
def test_fast_route_failures_are_explicit_not_fake_fallbacks(client,monkeypatch,route_request,case,status_code):
    data=payload()
    if case=='none':data={'code':'NoRoute','routes':[]}
    if case=='distant':data['waypoints'][0]['distance']=250
    mock_upstream(monkeypatch,data,status=429 if case=='throttled' else 200)
    response=client.post('/api/routes/search',json={**route_request,'provider':'auto'})
    assert response.status_code==status_code
    assert 'routes' not in response.json()


def test_astar_is_default_for_configured_graph(client,route_request):
    data=client.post('/api/routes/search',json=route_request).json()
    assert data['optimization']['algorithm']=='astar'
    assert list(data['optimization']['primary_search'])==['astar']
