import math
import httpx
import pytest
from fastapi import HTTPException
from backend.app import map_services, osm_routing
from backend.app.graph_search import haversine


def network():
    points={1:[21.03,105.82],2:[21.03,105.825],3:[21.03,105.83],4:[21.035,105.825],5:[21.035,105.83]}
    nodes=[{'type':'node','id':node,'lat':p[0],'lon':p[1]} for node,p in points.items()]
    ways=[way(10,[1,2],name='Đường Tây'),way(20,[2,3],name='Đường Đông'),way(30,[2,4,5,3],name='Đường vòng')]
    return {'elements':nodes+ways}


def way(id,nodes,**tags):
    return {'type':'way','id':id,'nodes':nodes,'tags':{'highway':'residential',**tags}}


def request(route_request,origin=(21.03,105.821),destination=(21.03,105.829)):
    route_request.update(provider='osm',algorithm='compare',weights={'time':.6,'distance':.4},
        origin={'lat':origin[0],'lng':origin[1],'name':'Địa chỉ đi'},destination={'lat':destination[0],'lng':destination[1],'name':'Địa chỉ đến'})
    return route_request


def mock_roads(monkeypatch,payload):
    async def load(bounds): return payload
    monkeypatch.setattr(osm_routing,'load_roads',load)
    monkeypatch.setenv('OSM_ENABLED','true')


def test_osm_snaps_inside_roads_and_returns_real_geometry(client,route_request,monkeypatch):
    mock_roads(monkeypatch,network())
    result=client.post('/api/routes/search',json=request(route_request))
    assert result.status_code==200,result.text
    data=result.json();best=data['routes'][0];opt=data['optimization']
    assert opt['scope']=='osm_network' and opt['agreement']
    assert best['distance_km']==pytest.approx(haversine([21.03,105.821],[21.03,105.829]),abs=.002)
    assert len(best['geometry'])>=3 and best['geometry'][0]==pytest.approx([21.03,105.821])
    assert best['geometry'][-1]==pytest.approx([21.03,105.829])
    assert best['unknown_share']==1 and all(s['source']=='osm' for s in best['segments'])
    assert sum(best['cost_components'].values())==pytest.approx(best['score'])
    assert opt['primary_search']['dijkstra']['cost']==pytest.approx(opt['primary_search']['astar']['cost'])
    assert len(data['routes'])>=2


def test_osm_one_way_does_not_allow_reverse(client,route_request,monkeypatch):
    data=network();data['elements']=[e for e in data['elements'] if e['type']=='node' or e['id']==10]
    data['elements'][-1]['tags']['oneway']='yes'
    mock_roads(monkeypatch,data)
    body=request(route_request,destination=(21.03,105.824))
    assert client.post('/api/routes/search',json=body).status_code==200
    body['origin'],body['destination']=body['destination'],body['origin']
    assert client.post('/api/routes/search',json=body).status_code==404


def test_surveyed_observation_changes_eta_but_demo_observation_does_not(client,route_request,monkeypatch):
    from backend.app.db import SessionLocal,now
    from backend.app.models import Segment,Observation
    payload=network()
    # A modest detour can beat the congested direct road; a very long one cannot.
    for element in payload['elements']:
        if element['type']=='node' and element['id'] in (4,5): element['lat']=21.031
    mock_roads(monkeypatch,payload)
    body=request(route_request);body['weights']={'time':1,'distance':0}
    first=client.post('/api/routes/search',json=body).json()['routes'][0]
    with SessionLocal() as db:
        segment=Segment(name='Surveyed test road',start_node='test_west',end_node='test_east',distance_km=1,
                        geometry=[[21.03,105.82],[21.03,105.83]],is_demo=True)
        db.add(segment);db.commit()
        db.add(Observation(segment_id=segment.id,user_id=1,density='HIGH',score=.9,observed_at=now().isoformat()));db.commit()
        sid=segment.id
    demo=client.post('/api/routes/search',json=body).json()['routes'][0]
    assert demo['duration_seconds']==first['duration_seconds'] and demo['unknown_share']==1
    with SessionLocal() as db:
        db.update(Segment,sid,{'is_demo':False});db.commit()
    surveyed=client.post('/api/routes/search',json=body).json()['routes'][0]
    assert any(s['osm_way_id']==30 for s in surveyed['segments'])
    assert surveyed['distance_km']>first['distance_km']
    assert any(s['source']=='manual' for s in surveyed['segments'])


@pytest.mark.parametrize('kind',['no_right_turn','only_left_turn'])
def test_via_node_restriction_forces_legal_detour(client,route_request,monkeypatch,kind):
    data=network();target=20 if kind.startswith('no_') else 30
    data['elements'].append({'type':'relation','id':900,'tags':{'type':'restriction','restriction':kind},
        'members':[{'type':'way','ref':10,'role':'from'},{'type':'node','ref':2,'role':'via'},{'type':'way','ref':target,'role':'to'}]})
    mock_roads(monkeypatch,data)
    result=client.post('/api/routes/search',json=request(route_request))
    assert result.status_code==200,result.text
    ways=[s['osm_way_id'] for s in result.json()['routes'][0]['segments']]
    assert 30 in ways and result.json()['optimization']['turn_restrictions']==1


def test_no_u_turn_does_not_block_continuation_on_same_way(client,route_request,monkeypatch):
    data=network();data['elements']=[e for e in data['elements'] if e['type']=='node']+[way(10,[1,2,3])]
    data['elements'].append({'type':'relation','id':900,'tags':{'type':'restriction','restriction':'no_u_turn'},
        'members':[{'type':'way','ref':10,'role':'from'},{'type':'node','ref':2,'role':'via'},{'type':'way','ref':10,'role':'to'}]})
    mock_roads(monkeypatch,data)
    assert client.post('/api/routes/search',json=request(route_request)).status_code==200


def test_unsupported_turn_condition_excludes_incoming_road(client,route_request,monkeypatch):
    data=network();data['elements'].append({'type':'relation','id':900,
        'tags':{'type':'restriction','restriction:conditional':'no_right_turn @ (08:00-09:00)'},
        'members':[{'type':'way','ref':10,'role':'from'},{'type':'node','ref':2,'role':'via'},{'type':'way','ref':20,'role':'to'}]})
    mock_roads(monkeypatch,data)
    # Origin is now >200 m from any permitted road; never use the restricted way.
    assert client.post('/api/routes/search',json=request(route_request,origin=(21.03,105.82))).status_code==422


@pytest.mark.parametrize('tags,mode,expected',[
    ({'highway':'residential','access':'private'},'DRIVE',False),
    ({'highway':'residential','access':'no','motorcar':'yes'},'DRIVE',True),
    ({'highway':'service','width':'1.5'},'DRIVE',False),
    ({'highway':'service','width':'1.5'},'TWO_WHEELER',True),
    ({'highway':'motorway'},'TWO_WHEELER',False),
    ({'highway':'pedestrian'},'DRIVE',False),
    ({'highway':'pedestrian','motorcycle':'yes'},'TWO_WHEELER',True),
    ({'highway':'residential','motor_vehicle:conditional':'no @ (08:00-09:00)'},'DRIVE',False),
])
def test_vehicle_access(tags,mode,expected):
    assert osm_routing.accessible(tags,mode)==expected


def test_roundabout_reverse_and_speed_limit():
    assert osm_routing.direction({'junction':'roundabout'},'DRIVE')==1
    assert osm_routing.direction({'oneway':'-1'},'DRIVE')==-1
    assert osm_routing.direction({'oneway':'yes','oneway:motorcycle':'no'},'TWO_WHEELER')==0
    assert osm_routing.reference_speed({'highway':'primary','maxspeed':'20 mph'},'DRIVE')==pytest.approx(32.18688)


def test_far_pin_and_long_journey_rejected(client,route_request,monkeypatch):
    mock_roads(monkeypatch,network())
    assert client.post('/api/routes/search',json=request(route_request,origin=(21.08,105.82))).status_code==422
    assert client.post('/api/routes/search',json=request(route_request,origin=(21.4,105.82))).status_code==422


def test_invalid_road_coordinates_are_reported_as_upstream_failure(client,route_request,monkeypatch):
    data=network();data['elements'][0]['lat']=float('nan')
    mock_roads(monkeypatch,data)
    assert client.post('/api/routes/search',json=request(route_request)).status_code==502


def test_address_search_returns_full_house_address_and_caches(client,monkeypatch):
    calls=[];map_services._cache.clear()
    async def fetch(url,**kwargs):
        calls.append(kwargs)
        return {'features':[{'geometry':{'coordinates':[105.83,21.03]},'properties':{'osm_id':123,'osm_type':'N',
            'name':'Địa điểm công cộng','housenumber':'36','street':'Ngọc Hà','city':'Hà Nội'}}]}
    monkeypatch.setattr(map_services,'fetch_json',fetch)
    result=client.get('/api/map/places',params={'q':'36 Ngọc Hà Hà Nội'})
    assert result.status_code==200 and '36 Ngọc Hà' in result.json()['places'][0]['name']
    assert result.json()['places'][0]['accuracy']=='house'
    assert client.get('/api/map/places',params={'q':'36 Ngọc Hà Hà Nội'}).status_code==200
    assert len(calls)==1
    assert client.get('/api/map/places',params={'q':'a'}).status_code==422


def test_search_drops_out_of_area_and_malformed_response(client,monkeypatch):
    map_services._cache.clear()
    async def fetch(url,**kwargs): return {'features':[{'geometry':{'coordinates':[10,50]},'properties':{}}]}
    monkeypatch.setattr(map_services,'fetch_json',fetch)
    assert client.get('/api/map/places',params={'q':'out of area'}).json()['places']==[]
    async def malformed(url,**kwargs): return {'wrong':'data'}
    monkeypatch.setattr(map_services,'fetch_json',malformed)
    assert client.get('/api/map/places',params={'q':'malformed response'}).status_code==502


def test_osm_disabled_and_upstream_failure_are_clear(client,route_request,monkeypatch):
    monkeypatch.setenv('OSM_ENABLED','false')
    assert client.post('/api/routes/search',json=request(route_request)).status_code==503
    assert client.get('/api/config').json()['osm_available'] is False
    monkeypatch.setenv('OSM_ENABLED','true')
    async def failed(bounds): raise HTTPException(504,'Nguồn bản đồ phản hồi chậm.')
    monkeypatch.setattr(osm_routing,'load_roads',failed)
    assert client.post('/api/routes/search',json=request(route_request)).status_code==504


def test_public_geocoder_errors_never_echo_upstream_content(client,monkeypatch):
    map_services._cache.clear();map_services._reservations.clear()
    real_client=httpx.AsyncClient
    def handler(request): return httpx.Response(429,json={'secret':'private-upstream-detail'})
    monkeypatch.setattr(map_services.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    result=client.get('/api/map/places',params={'q':'test error'})
    assert result.status_code==503 and 'private-upstream-detail' not in result.text


def test_road_download_falls_back_once_and_uses_disk_cache(monkeypatch,tmp_path):
    import asyncio
    monkeypatch.setattr(map_services,'DATA',tmp_path)
    monkeypatch.setenv('OVERPASS_URL','https://primary.test/interpreter')
    monkeypatch.setenv('OVERPASS_FALLBACK_URL','https://secondary.test/interpreter')
    calls=[]
    async def fetch(url,**kwargs):
        calls.append(url)
        if 'primary' in url: raise HTTPException(503,'Busy')
        return network()
    monkeypatch.setattr(map_services,'fetch_json',fetch)
    bounds=(21.,105.8,21.04,105.84)
    assert asyncio.run(map_services.load_roads(bounds))==network()
    assert asyncio.run(map_services.load_roads(bounds))==network()
    assert len(calls)==2
