"""Route over an OSM extract, preserving street geometry and legal direction.

Each search state records the incoming arc so via-node turn restrictions can be
checked. Unsupported conditional/via-way restrictions conservatively exclude
their incoming roads rather than silently permitting an unverified movement.
"""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from .graph_search import Edge, shortest_path, yen_paths, lower_bound_heuristic, path_label, haversine
from .map_services import load_roads, road_bounds, settings
from .models import Segment

ALLOW={'yes','designated','permissive','official'}
DENY={'no','private','agricultural','forestry','delivery','customers','permit'}
SPEED={'motorway':65,'trunk':50,'primary':40,'secondary':35,'tertiary':30,
       'unclassified':25,'residential':25,'living_street':15,'service':12,'track':10,'pedestrian':8}


def permission(tags,mode):
    keys=('motorcar','motor_vehicle','vehicle','access') if mode=='DRIVE' else ('motorcycle','motor_vehicle','vehicle','access')
    return next((str(tags[k]).lower() for k in keys if k in tags),'yes')


def accessible(tags,mode):
    if permission(tags,mode) in DENY: return False
    if any(k.endswith(':conditional') and k.split(':')[0] in ('access','vehicle','motor_vehicle','motorcar','motorcycle','oneway') for k in tags): return False
    highway=tags.get('highway','')
    if tags.get('area')=='yes' or tags.get('construction') or tags.get('proposed'): return False
    if highway in ('pedestrian','track') and not any(tags.get(k) in ALLOW for k in (('motorcar','motor_vehicle') if mode=='DRIVE' else ('motorcycle','motor_vehicle'))): return False
    if mode=='TWO_WHEELER' and (highway.startswith(('motorway','trunk')) or tags.get('motorroad')=='yes'): return False
    width=number(tags.get('maxwidth:physical',tags.get('maxwidth',tags.get('width',''))))
    if width and width < (2.2 if mode=='DRIVE' else .8): return False
    return highway in SPEED or highway.removesuffix('_link') in SPEED


def number(value):
    match=re.match(r'^\s*(\d+(?:\.\d+)?)',str(value))
    return float(match[1]) if match else None


def direction(tags,mode):
    value=tags.get('oneway:motorcar' if mode=='DRIVE' else 'oneway:motorcycle',tags.get('oneway:motor_vehicle',tags.get('oneway:vehicle',tags.get('oneway'))))
    if value in ('no','0','false'): return 0
    if value in ('-1','reverse'): return -1
    if value in ('yes','1','true') or value is None and (tags.get('junction') in ('roundabout','circular') or tags.get('highway')=='motorway'): return 1
    return 0


def reference_speed(tags,mode):
    speed=SPEED.get(tags.get('highway','').removesuffix('_link'),25)
    if mode=='TWO_WHEELER': speed=min(speed,35)
    limit=number(tags.get('maxspeed',''))
    if limit:
        if 'mph' in str(tags['maxspeed']): limit*=1.609344
        speed=min(speed,limit)
    return max(3,speed)


def project(point,a,b):
    # Local metric projection; snap is to a road segment, not a distant junction.
    scale=math.cos(math.radians(point[0]))
    ax=(a[1]-point[1])*scale;ay=a[0]-point[0]
    dx=(b[1]-a[1])*scale;dy=b[0]-a[0]
    t=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0.
    projected=[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]
    return haversine(point,projected),t,projected


@dataclass
class Arc:
    start: str
    end: str
    way: int
    name: str
    geometry: list
    distance: float
    speed: float
    tags: dict


def extract(payload,req):
    elements=payload['elements'];positions={};node_tags={};relations=[];ways=[]
    for row in elements:
        if row.get('type')=='node':
            lat,lng=float(row['lat']),float(row['lon'])
            if not (math.isfinite(lat) and math.isfinite(lng) and -90<=lat<=90 and -180<=lng<=180):
                raise ValueError('Invalid OSM coordinate')
            positions[str(row['id'])]=[lat,lng]
            node_tags[str(row['id'])]=row.get('tags',{})
        elif row.get('type')=='relation': relations.append(row)
        elif row.get('type')=='way' and accessible(row.get('tags',{}),req.mode): ways.append(row)
    restrictions=defaultdict(list);excluded=set();restriction_count=0
    mode_key='motorcar' if req.mode=='DRIVE' else 'motorcycle'
    for relation in relations:
        tags=relation.get('tags',{})
        if tags.get('type')!='restriction': continue
        exceptions=set(tags.get('except','').split(';'))
        if mode_key in exceptions or 'motor_vehicle' in exceptions or 'vehicle' in exceptions: continue
        kind=tags.get('restriction:'+mode_key,tags.get('restriction:motor_vehicle',tags.get('restriction','')))
        members=relation.get('members',[])
        incoming=[m['ref'] for m in members if m.get('role')=='from' and m.get('type')=='way']
        outgoing=[m['ref'] for m in members if m.get('role')=='to' and m.get('type')=='way']
        via=[str(m['ref']) for m in members if m.get('role')=='via' and m.get('type')=='node']
        if any(k.startswith('restriction') and k.endswith(':conditional') for k in tags) or len(via)!=1 or not kind.startswith(('no_','only_')):
            if kind or any(k.startswith('restriction') for k in tags): excluded.update(incoming)
            continue
        for source in incoming:
            restrictions[(via[0],source)].append((kind,set(outgoing)))
            restriction_count+=1
    ways=[dict(way,nodes=[str(n) for n in way['nodes']]) for way in ways if way['id'] not in excluded]
    # Conservative handling of barriers, with explicit vehicle permissions taking precedence.
    blocked=set()
    for node,tags in node_tags.items():
        explicit=any(tags.get(k) in ALLOW for k in (mode_key,'motor_vehicle','vehicle','access'))
        if permission(tags,req.mode) in DENY or (tags.get('barrier') not in (None,'no','cattle_grid','toll_booth','border_control') and not explicit): blocked.add(node)
    for way in ways:
        if any(node not in positions for node in way['nodes']):
            raise HTTPException(502,'Dữ liệu mạng đường chưa đầy đủ. Vui lòng tải lại vùng đường.')
    if not ways: raise HTTPException(404,'Không có đường phù hợp với phương tiện trong vùng đã chọn.')
    snaps=[]
    for label,waypoint in (('origin',req.origin),('destination',req.destination)):
        point=[waypoint.lat,waypoint.lng];best=None
        for way in ways:
            for index,(a,b) in enumerate(zip(way['nodes'],way['nodes'][1:])):
                if a in blocked or b in blocked: continue
                distance,t,coordinate=project(point,positions[a],positions[b])
                if best is None or distance<best['distance_km']:
                    best={'way_id':way['id'],'index':index,'fraction':t,'point':coordinate,'distance_km':distance,'label':label}
        if best is None or best['distance_km']>.2:
            raise HTTPException(422,'Điểm '+('xuất phát' if label=='origin' else 'đến')+' cách đường phù hợp quá 200 m. Hãy kiểm tra và đặt ghim gần lối ra vào.')
        snaps.append(best)
    if haversine(snaps[0]['point'],snaps[1]['point'])<.001:
        raise HTTPException(422,'Hai ghim nối vào cùng vị trí trên đường. Hãy chọn hai điểm cách nhau xa hơn.')
    inserts=defaultdict(list)
    for snap in snaps:
        way=next(w for w in ways if w['id']==snap['way_id']);a,b=way['nodes'][snap['index']:snap['index']+2]
        if snap['fraction']<1e-7: snap['node']=a;snap['point']=positions[a]
        elif snap['fraction']>1-1e-7: snap['node']=b;snap['point']=positions[b]
        else:
            snap['node']='pin_'+snap['label'];positions[snap['node']]=snap['point']
            inserts[(snap['way_id'],snap['index'])].append(snap)
    for way in ways:
        updated=[]
        for index,node in enumerate(way['nodes']):
            updated.append(node)
            for snap in sorted(inserts.get((way['id'],index),[]),key=lambda row:row['fraction']): updated.append(snap['node'])
        way['nodes']=updated
    # Keep intersections/way ends/turn nodes/pins; compress only interior shape nodes.
    uses=Counter(node for way in ways for node in way['nodes'])
    boundaries={node for node,count in uses.items() if count>1}|blocked|{s['node'] for s in snaps}|{key[0] for key in restrictions}
    arcs=[];endpoint_ways={snap['way_id'] for snap in snaps}
    for way in ways:
        tags=way['tags']
        if permission(tags,req.mode)=='destination' and way['id'] not in endpoint_ways: continue
        nodes=way['nodes'];cut=0
        for index in range(1,len(nodes)):
            if index!=len(nodes)-1 and nodes[index] not in boundaries: continue
            chain=nodes[cut:index+1];cut=index
            if chain[0] in blocked or chain[-1] in blocked or chain[0]==chain[-1]: continue
            geometry=[positions[n] for n in chain]
            distance=sum(haversine(a,b) for a,b in zip(geometry,geometry[1:]))
            if distance<1e-8: continue
            name=tags.get('name') or tags.get('ref') or ('Ngõ / đường nội bộ' if tags.get('highway') in ('service','living_street') else 'Đường chưa có tên')
            direct=direction(tags,req.mode)
            if direct!=-1: arcs.append(Arc(chain[0],chain[-1],way['id'],name,geometry,distance,reference_speed(tags,req.mode),tags))
            if direct!=1: arcs.append(Arc(chain[-1],chain[0],way['id'],name,list(reversed(geometry)),distance,reference_speed(tags,req.mode),tags))
    return arcs,positions,snaps,restrictions,{'turn_restrictions':restriction_count,'conservatively_excluded_ways':len(excluded)}


def turn_allowed(previous,outgoing,restrictions):
    uturn=previous.start==outgoing.end
    for kind,targets in restrictions.get((previous.end,previous.way),[]):
        match=outgoing.way in targets
        if kind=='no_u_turn':
            if match and uturn: return False
        elif kind=='only_u_turn':
            if not match or not uturn: return False
        elif kind.startswith('no_'):
            if match: return False
        elif not match or kind=='only_straight_on' and uturn: return False
    return True


def compute_routes(db,req,payload,bounds):
    from .routing import route_evidence, normalized_weights, rank_routes, point_distance_to_line
    try:
        arcs,positions,snaps,restrictions,restriction_info=extract(payload,req)
    except (KeyError,ValueError,TypeError,AttributeError,IndexError):
        raise HTTPException(502,'Nguồn mạng đường trả dữ liệu không hợp lệ. Vui lòng thử lại.') from None
    segments=db.find(Segment,{'active':True,'is_demo':False})
    observations=route_evidence(db,req,segments)
    traffic={};metrics={}
    for index,arc in enumerate(arcs):
        matches=[s for s in segments if s.id in observations and all(point_distance_to_line(point,s.geometry)<=40 for point in (arc.geometry[0],arc.geometry[len(arc.geometry)//2],arc.geometry[-1]))]
        if matches:
            segment=max(matches,key=lambda s:{'LOW':0,'NORMAL':1,'HIGH':2}[observations[s.id].density])
            traffic[index]=(segment,observations[segment.id])
        density=traffic[index][1].density if index in traffic else None
        factor={'LOW':1.,'NORMAL':.65,'HIGH':.3,None:1.}[density]
        metrics[index]=(arc.distance/(arc.speed*factor)*3600,arc.distance*{'LOW':.05,'NORMAL':.35,'HIGH':1.,None:.5}[density])
    outgoing=defaultdict(list)
    for index,arc in enumerate(arcs): outgoing[arc.start].append(index)
    state_positions={'start':positions[snaps[0]['node']],'goal':positions[snaps[1]['node']]}
    edges=[];details={}
    def add(start,end,index):
        seconds,exposure=metrics[index];arc=arcs[index]
        edge=Edge((index,start),start,end,seconds,arc.distance,exposure)
        edges.append(edge);details[edge.key]=index
    for index in outgoing[snaps[0]['node']]: add('start',f'arc_{index}',index)
    for index,arc in enumerate(arcs):
        state=f'arc_{index}';state_positions[state]=positions[arc.end]
        if arc.end==snaps[1]['node']:
            edge=Edge(('end',index),state,'goal',0,0,0);edges.append(edge);details[edge.key]=None
            continue
        if arc.end==snaps[0]['node']: continue
        for next_index in outgoing[arc.end]:
            if turn_allowed(arc,arcs[next_index],restrictions): add(state,f'arc_{next_index}',next_index)
    if len(edges)>100000: raise HTTPException(422,'Mạng đường quá phức tạp. Hãy chọn hai điểm gần hơn.')
    def adjacency(items):
        graph=defaultdict(list)
        for edge in items: graph[edge.start].append(edge)
        return graph
    fastest,_=shortest_path(adjacency([replace(e,cost=e.seconds) for e in edges]),'start','goal')
    shortest,_=shortest_path(adjacency([replace(e,cost=e.distance_km) for e in edges]),'start','goal')
    if fastest is None or shortest is None: raise HTTPException(404,'Chưa tìm được tuyến hợp lệ trong vùng đường đã tải. Hãy kiểm tra phương tiện hoặc đổi ghim gần lối ra vào; hệ thống không nối đường thẳng thay tuyến.')
    time_ref=sum(e.seconds for e in fastest);distance_ref=sum(e.distance_km for e in shortest)
    if distance_ref<.001: raise HTTPException(422,'Hai ghim nối vào cùng vị trí trên đường. Hãy chọn hai điểm cách nhau xa hơn.')
    w=normalized_weights(req.weights)
    edges=[replace(e,cost=w['time']*e.seconds/time_ref+w['distance']*e.distance_km/distance_ref+w['density']*e.exposure_km/distance_ref) for e in edges]
    graph=adjacency(edges);heuristic,info=lower_bound_heuristic(edges,state_positions,'goal',w,time_ref,distance_ref)
    searches={};paths={}
    for algorithm in (('dijkstra','astar') if req.algorithm=='compare' else (req.algorithm,)):
        path,stats=shortest_path(graph,'start','goal',algorithm,heuristic)
        paths[algorithm]=path
        searches[algorithm]={**stats,'cost':path_label(path)[0] if path else None,'segment_ids':[arcs[details[e.key]].way for e in path if details[e.key] is not None] if path else []}
    agreement=None
    if req.algorithm=='compare':
        agreement=math.isclose(searches['dijkstra']['cost'],searches['astar']['cost'],rel_tol=1e-9,abs_tol=1e-9)
        if not agreement: raise HTTPException(500,'Không xác nhận được tính nhất quán giữa Dijkstra và A*.')
    chosen='astar' if req.algorithm=='compare' else req.algorithm
    candidates=yen_paths(graph,'start','goal',paths[chosen],chosen,heuristic,limit=6,max_searches=48)
    alternatives=[]
    for path in candidates:
        physical=[arcs[details[e.key]] for e in path if details[e.key] is not None]
        nodes=[physical[0].start]+[arc.end for arc in physical]
        # Keep the proven optimum even when a legal turn detour revisits a
        # junction, but suppress redundant loops in optional alternatives.
        if alternatives and len(nodes)!=len(set(nodes)): continue
        alternatives.append(path)
        if len(alternatives)==3: break
    routes=[]
    for index,path in enumerate(alternatives):
        cost,seconds,distance=path_label(path);exposure=sum(e.exposure_km for e in path)
        geometry=[];items=[];names=[];high=unknown=0.
        for edge in path:
            arc_index=details[edge.key]
            if arc_index is None: continue
            arc=arcs[arc_index];matched=traffic.get(arc_index);ob=matched[1] if matched else None
            density=ob.density if ob else None
            geometry.extend(arc.geometry if not geometry else arc.geometry[1:])
            if not names or names[-1]!=arc.name: names.append(arc.name)
            unknown+=arc.distance if density is None else 0
            high+=arc.distance if density=='HIGH' else 0
            items.append({'id':matched[0].id if matched else -arc.way,'osm_way_id':arc.way,'name':arc.name,'distance_km':round(arc.distance,4),
                          'density':density,'source':ob.source if ob else 'osm','geometry':arc.geometry,'evidence_days':getattr(ob,'evidence_days',None)})
        routes.append({'id':f'osm-{index}','name':' → '.join(names[:6])+(' → …' if len(names)>6 else ''),
                       'geometry':geometry,'segments':items,'duration_seconds':round(seconds),'distance_km':round(distance,3),
                       'risk':exposure/distance,'risk_exposure_km':exposure,'high_share':high/distance,'unknown_share':unknown/distance,
                       'optimization_cost':cost,'raw_criteria':(seconds,distance,exposure),'traffic_intervals':[],
                       'cost_components':{'time':w['time']*seconds/time_ref,'distance':w['distance']*distance/distance_ref,'density':w['density']*exposure/distance_ref}})
    metadata={'scope':'osm_network','requested_algorithm':req.algorithm,'algorithm':chosen,'agreement':agreement,
              'primary_search':searches,'references':{'time_seconds':time_ref,'distance_km':distance_ref},'normalized_weights':w,
              'heuristic':info,'bounds':bounds,'network_edges':len(edges),'contains_demo_roads':False,
              **restriction_info,'snaps':[{key:s[key] for key in ('label','point','distance_km','way_id')} for s in snaps],
              'note':'Tối ưu trên mạng OSM trong vùng đã tải, cùng snapshot. ETA từ loại đường/giới hạn tốc độ và quan sát nếu có; chưa phải thời gian thực. Tuyến thay thế giới hạn 48 lượt tìm nhánh. Thống kê chỉ đo lượt chính.'}
    return rank_routes(routes,req.weights,(time_ref,distance_ref)),metadata


async def osm_routes(db,req):
    if not settings()['osm_available']: raise HTTPException(503,'Nguồn OpenStreetMap đang tắt.')
    bounds=road_bounds([req.origin.lat,req.origin.lng],[req.destination.lat,req.destination.lng])
    payload=await load_roads(bounds)
    return await run_in_threadpool(compute_routes,db,req,payload,bounds)
