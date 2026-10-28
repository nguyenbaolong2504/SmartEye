from dataclasses import replace
from datetime import timedelta
import itertools
import math
import random
import pytest
from backend.app.graph_search import Edge, shortest_path, yen_paths, lower_bound_heuristic, path_label
from backend.app.db import get_database, SessionLocal, now
from backend.app.models import Segment, Observation


def graph_of(edges):
    result={}
    for edge in edges: result.setdefault(edge.start,[]).append(edge)
    return result


def exhaustive_paths(graph,start,goal):
    output=[]
    def walk(node,seen,path):
        if node==goal: output.append(path);return
        for edge in graph.get(node,[]):
            if edge.end not in seen: walk(edge.end,seen|{edge.end},path+[edge])
    walk(start,{start},[])
    return sorted(output,key=path_label)


@pytest.mark.parametrize('seed',range(10))
def test_dijkstra_astar_and_yen_match_exhaustive_multigraph_oracle(seed):
    rng=random.Random(seed);nodes=['a','b','c','d','e']
    positions={node:[21+rng.random()/10,105.7+rng.random()/10] for node in nodes}
    edges=[]
    for a,b in itertools.permutations(nodes,2):
        if rng.random()<.45 or (a,b)==('a','e'):
            distance=rng.uniform(.01,5);seconds=rng.uniform(10,900);exposure=distance*rng.random()
            edges.append(Edge((len(edges),False),a,b,seconds,distance,exposure,.6*seconds/600+.4*distance/5))
    # Parallel edges exercise Yen's edge identity rather than only vertex paths.
    edges.append(Edge((len(edges),False),'a','e',100,3,.2,.6*100/600+.4*3/5))
    graph=graph_of(edges);expected=exhaustive_paths(graph,'a','e')
    h,info=lower_bound_heuristic(edges,positions,'e',{'time':.6,'distance':.4},600,5)
    assert h('e')==0 and 0<=info['distance_scale']<=1
    for edge in edges: assert h(edge.start)<=edge.cost+h(edge.end)+1e-9
    for algorithm in ('dijkstra','astar'):
        best,stats=shortest_path(graph,'a','e',algorithm,h)
        assert math.isclose(path_label(best)[0],path_label(expected[0])[0],abs_tol=1e-9)
        assert stats['expanded_nodes']>0
        alternatives=yen_paths(graph,'a','e',best,algorithm,h,limit=3)
        assert len(alternatives)==min(3,len(expected))
        for actual,wanted in zip(alternatives,expected):
            assert math.isclose(path_label(actual)[0],path_label(wanted)[0],abs_tol=1e-9)
            visited=['a']+[e.end for e in actual]
            assert len(visited)==len(set(visited))
        assert len({tuple(e.key for e in path) for path in alternatives})==len(alternatives)


def test_heuristic_remains_admissible_when_demo_km_understate_geometry():
    edges=[Edge((1,False),'a','b',1,.001,0,1),Edge((2,False),'b','c',1,.001,0,1),Edge((3,False),'a','c',100,1,0,100)]
    positions={'a':[21,105.7],'b':[21,105.8],'c':[21,105.9]}
    h,info=lower_bound_heuristic(edges,positions,'c',{'time':1,'distance':0},1,1)
    assert info['distance_scale']<.001 and h('a')<=2+1e-9
    best,_=shortest_path(graph_of(edges),'a','c','astar',h)
    assert [e.key[0] for e in best]==[1,2]


def test_unreachable_single_node_and_banned_edges():
    edge=Edge((1,False),'a','b',10,1,.5,1)
    graph=graph_of([edge])
    assert shortest_path(graph,'b','a')[0] is None
    assert shortest_path(graph,'a','a')[0]==[]
    assert shortest_path(graph,'a','b',banned_edges={edge.key})[0] is None
    assert shortest_path(graph,'a','b',banned_nodes={'b'})[0] is None
    assert yen_paths(graph,'b','a',None,'dijkstra')==[]
    with pytest.raises(ValueError): shortest_path(graph_of([replace(edge,cost=-1)]),'a','b')


def tradeoff_network():
    database=get_database();database.segments.delete_many({})
    # Three fastest candidates exclude the true time+distance compromise.
    options=[('Fast 1',2.,'LOW'),('Fast 2',2.1,'LOW'),('Fast 3',2.2,'LOW'),('Compromise',1.5,'NORMAL'),('Shortest',1.,'HIGH')]
    with SessionLocal() as db:
        for i,(name,distance,density) in enumerate(options,1):
            db.add(Segment(id=i,name=name,start_node='hoankiem',end_node='caugiay',distance_km=distance,
                geometry=[[21.0287,105.8524],[21.0333,105.7984]]))
            db.add(Observation(segment_id=i,user_id=1,density=density,score={'LOW':.1,'NORMAL':.4,'HIGH':.8}[density],observed_at=now().isoformat()))
        db.commit()


@pytest.mark.parametrize('algorithm',['dijkstra','astar','compare'])
def test_combined_optimum_can_be_neither_shortest_nor_fastest(client,route_request,algorithm):
    tradeoff_network();route_request.update(algorithm=algorithm,weights={'time':.5,'distance':.5})
    response=client.post('/api/routes/search',json=route_request)
    assert response.status_code==200,response.text
    result=response.json();best=result['routes'][0]
    assert best['name']=='Compromise'
    assert best['distance_km']==1.5 and best['duration_seconds']>round(2/35*3600)
    assert len(result['routes'])==3
    opt=result['optimization']
    assert opt['references']['distance_km']==1.
    assert opt['references']['time_seconds']==pytest.approx(2/35*3600)
    assert sum(best['cost_components'].values())==pytest.approx(best['score'])
    if algorithm=='compare':
        assert opt['agreement'] and opt['primary_search']['dijkstra']['cost']==pytest.approx(opt['primary_search']['astar']['cost'])


def test_user_priority_changes_optimum_and_dominated_edge_does_not_rescale(client,route_request):
    tradeoff_network();route_request['weights']={'time':1.,'distance':0.}
    assert client.post('/api/routes/search',json=route_request).json()['routes'][0]['name']=='Fast 1'
    route_request['weights']={'time':0.,'distance':1.}
    assert client.post('/api/routes/search',json=route_request).json()['routes'][0]['name']=='Shortest'
    route_request['weights']={'time':.5,'distance':.5}
    first=client.post('/api/routes/search',json=route_request).json()
    with SessionLocal() as db:
        db.add(Segment(id=99,name='Dominated extra road',start_node='hoankiem',end_node='caugiay',distance_km=99,geometry=[[21,105.8],[21,105.9]]));db.commit()
    second=client.post('/api/routes/search',json=route_request).json()
    assert first['optimization']['references']==second['optimization']['references']
    assert first['routes'][0]['score']==second['routes'][0]['score']


def test_one_way_roads_new_places_and_favorite_algorithm(admin_client):
    payload={'name':'Surveyed one way','start_node':'new_west','end_node':'new_east','distance_km':2,
        'geometry':[[21.04,105.79],[21.04,105.81]],'is_demo':False,'active':True,'one_way':True}
    assert admin_client.post('/api/segments',json=payload).status_code==201
    places=admin_client.get('/api/places').json()
    a=next(p for p in places if p['node']=='new_west');b=next(p for p in places if p['node']=='new_east')
    request={'origin':a,'destination':b,'weights':{'time':.6,'distance':.4},'algorithm':'dijkstra'}
    result=admin_client.post('/api/routes/search',json=request)
    assert result.status_code==200 and len(result.json()['routes'])==1
    assert not result.json()['optimization']['contains_demo_roads']
    saved=admin_client.post('/api/favorites',json={'name':'Surveyed route','request':request})
    assert saved.status_code==201 and saved.json()['request']['algorithm']=='dijkstra'
    request.update(origin=b,destination=a)
    assert admin_client.post('/api/routes/search',json=request).status_code==404


@pytest.mark.parametrize('weights',[{'time':float('inf'),'distance':.5},{'time':float('nan'),'distance':.5},{'time':-.5,'distance':.5},{'time':0,'distance':0}])
def test_invalid_route_weights_rejected(client,route_request,weights):
    # Raw JSON deliberately tests nonstandard NaN/Infinity accepted by some parsers.
    import json
    route_request['weights']=weights
    assert client.post('/api/routes/search',content=json.dumps(route_request),headers={'Content-Type':'application/json'}).status_code==422


def test_invalid_algorithm_rejected(client,route_request):
    route_request['algorithm']='invented'
    assert client.post('/api/routes/search',json=route_request).status_code==422
