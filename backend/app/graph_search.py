"""Dijkstra, consistent-heuristic A*, and Yen alternatives on a weighted multigraph."""
from dataclasses import dataclass
import heapq
import itertools
import math
from time import perf_counter


@dataclass(frozen=True)
class Edge:
    key: tuple
    start: str
    end: str
    seconds: float
    distance_km: float
    exposure_km: float
    cost: float = 0.


def path_label(edges):
    return (sum(e.cost for e in edges),sum(e.seconds for e in edges),sum(e.distance_km for e in edges))


def shortest_path(graph,start,goal,algorithm='dijkstra',heuristic=lambda node:0.,banned_nodes=frozenset(),banned_edges=frozenset()):
    if algorithm not in ('dijkstra','astar'): raise ValueError('Unknown graph algorithm')
    began=perf_counter();serial=itertools.count();expanded=relaxed=0
    if start in banned_nodes or goal in banned_nodes: return None,{'expanded_nodes':0,'relaxed_edges':0,'elapsed_ms':0.}
    h=heuristic if algorithm=='astar' else lambda node:0.
    best={start:(0.,0.,0.)};previous={}
    queue=[(h(start),0.,0.,0.,next(serial),start)]
    result=None
    while queue:
        _,cost,seconds,distance,_,node=heapq.heappop(queue)
        if best.get(node)!=(cost,seconds,distance): continue
        expanded+=1
        if node==goal:
            result=[];cursor=goal
            while cursor!=start:
                edge=previous[cursor];result.append(edge);cursor=edge.start
            result.reverse();break
        for edge in graph.get(node,[]):
            if edge.end in banned_nodes or edge.key in banned_edges: continue
            if not all(math.isfinite(v) and v>=0 for v in (edge.cost,edge.seconds,edge.distance_km)):
                raise ValueError('Dijkstra/A* require finite nonnegative edge costs')
            candidate=(cost+edge.cost,seconds+edge.seconds,distance+edge.distance_km)
            if candidate<best.get(edge.end,(math.inf,math.inf,math.inf)):
                best[edge.end]=candidate;previous[edge.end]=edge;relaxed+=1
                heapq.heappush(queue,(candidate[0]+h(edge.end),*candidate,next(serial),edge.end))
    return result,{'expanded_nodes':expanded,'relaxed_edges':relaxed,'elapsed_ms':round((perf_counter()-began)*1000,3)}


def yen_paths(graph,start,goal,first,algorithm,heuristic=lambda node:0.,limit=3):
    """K shortest loopless paths; bans use edge IDs, including parallel edges."""
    if first is None: return []
    accepted=[first];pending=[];serial=itertools.count()
    seen={tuple(e.key for e in first)}
    while len(accepted)<limit:
        last=accepted[-1]
        nodes=[start]+[edge.end for edge in last]
        for index in range(len(last)):
            root=last[:index];signature=tuple(e.key for e in root)
            removed={path[index].key for path in accepted if len(path)>index and tuple(e.key for e in path[:index])==signature}
            spur,_=shortest_path(graph,nodes[index],goal,algorithm,heuristic,
                banned_nodes=frozenset(nodes[:index]),banned_edges=frozenset(removed))
            if spur is None: continue
            candidate=root+spur;key=tuple(e.key for e in candidate)
            if key in seen: continue
            seen.add(key);heapq.heappush(pending,(*path_label(candidate),next(serial),candidate))
        if not pending: break
        accepted.append(heapq.heappop(pending)[-1])
    return accepted


def haversine(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b))
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1,max(0,value))))


def lower_bound_heuristic(edges,positions,goal,weights,time_reference,distance_reference):
    """Scale the metric by every stored edge, even when demo km understate geometry."""
    scale=1.
    speed=0.
    for edge in edges:
        if edge.seconds>0: speed=max(speed,edge.distance_km/edge.seconds*3600)
        elif edge.distance_km>0: speed=math.inf
        if edge.start not in positions or edge.end not in positions:
            scale=0.;continue
        direct=haversine(positions[edge.start],positions[edge.end])
        if direct>0: scale=min(scale,edge.distance_km/direct)
    scale=max(0,math.nextafter(scale,0.))
    speed=math.nextafter(speed,math.inf) if speed else 0.
    coefficient=weights['distance']/distance_reference
    if speed>0: coefficient+=weights['time']*3600/speed/time_reference
    def estimate(node):
        if node not in positions or goal not in positions: return 0.
        return scale*haversine(positions[node],positions[goal])*coefficient
    return estimate,{'distance_scale':scale,'max_speed_kmh':speed,'kind':'scaled_haversine_lower_bound'}
