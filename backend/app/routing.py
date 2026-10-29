import math
import os
import logging
from datetime import datetime
import httpx
from fastapi import HTTPException
from .models import Segment
from .traffic import latest_observations
from .seed import PLACES
from .db import stamp
from .db import now
from .history import historical_evidence
from types import SimpleNamespace
from dataclasses import replace
from .graph_search import Edge, shortest_path, yen_paths, lower_bound_heuristic, path_label


def route_evidence(db,req,segments):
    future = bool(req.departure_at and (req.departure_at-now()).total_seconds()>300)
    result = {} if future else latest_observations(db)
    if future:
        # Use only deployed forecasts whose actual prediction time matches departure.
        from .forecast_ml import forecast
        for segment in segments:
            for target in ('congestion','density'):
                try: output=forecast(db.database,segment.id,target)
                except Exception:
                    logging.getLogger('smarteye.forecast').warning('Forecast unavailable for routing',exc_info=True)
                    continue
                matches=[p for p in output.get('predictions',[]) if abs((req.departure_at-now()).total_seconds())<=35*60
                    and abs((req.departure_at-datetime.fromisoformat(p['predicted_at'])).total_seconds())<=150]
                if not matches: continue
                prediction=min(matches,key=lambda p:abs((req.departure_at-datetime.fromisoformat(p['predicted_at'])).total_seconds()))
                label=prediction['label'];density={'FREE':'LOW','SLOW':'NORMAL','JAM':'HIGH'}.get(label,label)
                result[segment.id]=SimpleNamespace(density=density,score={'LOW':.1,'NORMAL':.4,'HIGH':.8}[density],
                    source='forecast',model=prediction['model'],predicted_at=prediction['predicted_at'],forecast_target=target)
                break
    missing = [s.id for s in segments if s.id not in result]
    if missing:
        patterns = historical_evidence(db.database,missing,req.departure_at or now())
        result.update({sid:SimpleNamespace(**row) for sid,row in patterns.items()})
    return result

def normalized_weights(weights):
    values={key:float(weights.get(key,0)) for key in ('time','distance','density')}
    if any(not math.isfinite(value) or value<0 for value in values.values()) or sum(values.values())<=0:
        raise ValueError('Weights must be finite, nonnegative and not all zero')
    return {key:value/sum(values.values()) for key,value in values.items()}


def rank_routes(routes, weights, references=None):
    if not routes: raise HTTPException(404,'Không tìm thấy tuyến đường phù hợp.')
    w=normalized_weights(weights)
    time_ref,distance_ref=references or (max(1,min(r['duration_seconds'] for r in routes)),max(.001,min(r['distance_km'] for r in routes)))
    for route in routes:
        route.setdefault('risk_exposure_km',route['risk']*route['distance_km'])
        route.setdefault('cost_components',{'time':w['time']*route['duration_seconds']/time_ref,
            'distance':w['distance']*route['distance_km']/distance_ref,
            'density':w['density']*route['risk_exposure_km']/distance_ref})
        route['score']=route.get('optimization_cost',sum(route['cost_components'].values()))
        route['recommended']=False;route['badges']=[]
    def criteria(route):
        return route.get('raw_criteria',(route['duration_seconds'],route['distance_km'],route['risk_exposure_km']))
    for route in routes:
        route['dominated']=any(all(a<=b for a,b in zip(criteria(other),criteria(route)))
            and any(a<b for a,b in zip(criteria(other),criteria(route))) for other in routes if other is not route)
    for key,label in [('duration_seconds','Nhanh nhất'),('distance_km','Ngắn nhất'),('risk_exposure_km','Ít đoạn rủi ro nhất')]:
        value=min(route[key] for route in routes)
        for route in routes:
            if math.isclose(route[key],value,rel_tol=1e-9,abs_tol=1e-9): route['badges'].append(label)
    winner=min((route for route in routes if not route['dominated']),key=lambda route:(route['score'],*criteria(route)))
    winner['recommended']=True
    for route in routes: route.pop('raw_criteria',None)
    return sorted(routes,key=lambda route:(not route['recommended'],route['score'],route['duration_seconds'],route['distance_km']))


def demo_routes(db, req):
    segments=db.find(Segment,{'active':True},sort=[('id',1)])
    valid_nodes={node for segment in segments for node in (segment.start_node,segment.end_node)}
    if req.origin.node not in valid_nodes or req.destination.node not in valid_nodes:
        raise HTTPException(422,'Chọn điểm đi và điểm đến thuộc mạng đường SmartEye đang hoạt động.')
    if req.origin.node==req.destination.node:
        raise HTTPException(422,'Điểm đi và điểm đến phải khác nhau.')
    latest=route_evidence(db,req,segments)
    speeds={'LOW':35 if req.mode=='DRIVE' else 30,'NORMAL':22 if req.mode=='DRIVE' else 24,'HIGH':9 if req.mode=='DRIVE' else 12,None:25}
    risks={'LOW':.05,'NORMAL':.35,'HIGH':1.,None:.5}
    positions={p['node']:[p['lat'],p['lng']] for p in PLACES}
    edges=[];details={}
    for segment in segments:
        density=latest[segment.id].density if segment.id in latest else None
        seconds=segment.distance_km/speeds[density]*3600
        positions.setdefault(segment.start_node,segment.geometry[0]);positions.setdefault(segment.end_node,segment.geometry[-1])
        for reverse in ((False,) if segment.one_way else (False,True)):
            a,b=(segment.end_node,segment.start_node) if reverse else (segment.start_node,segment.end_node)
            edge=Edge((segment.id,reverse),a,b,seconds,segment.distance_km,segment.distance_km*risks[density])
            edges.append(edge);details[edge.key]=(segment,reverse)
    def adjacency(items):
        graph={}
        for edge in items: graph.setdefault(edge.start,[]).append(edge)
        return graph
    start,goal=req.origin.node,req.destination.node
    fastest,_=shortest_path(adjacency([replace(e,cost=e.seconds) for e in edges]),start,goal)
    shortest,_=shortest_path(adjacency([replace(e,cost=e.distance_km) for e in edges]),start,goal)
    if fastest is None or shortest is None: raise HTTPException(404,'Không có tuyến đi được theo chiều đường đã cấu hình.')
    time_ref=sum(e.seconds for e in fastest);distance_ref=sum(e.distance_km for e in shortest)
    w=normalized_weights(req.weights)
    edges=[replace(e,cost=w['time']*e.seconds/time_ref+w['distance']*e.distance_km/distance_ref+w['density']*e.exposure_km/distance_ref) for e in edges]
    graph=adjacency(edges)
    heuristic,heuristic_info=lower_bound_heuristic(edges,positions,goal,w,time_ref,distance_ref)
    outputs={};stats={}
    for algorithm in (('dijkstra','astar') if req.algorithm=='compare' else (req.algorithm,)):
        path,info=shortest_path(graph,start,goal,algorithm,heuristic)
        outputs[algorithm]=path
        stats[algorithm]={**info,'cost':path_label(path)[0] if path is not None else None,
            'segment_ids':[e.key[0] for e in path] if path is not None else []}
    agreement=None
    if req.algorithm=='compare':
        agreement=outputs['dijkstra'] is not None and outputs['astar'] is not None and math.isclose(stats['dijkstra']['cost'],stats['astar']['cost'],rel_tol=1e-9,abs_tol=1e-9)
        if not agreement: raise HTTPException(500,'Không xác nhận được tính nhất quán giữa Dijkstra và A*.')
    chosen='astar' if req.algorithm=='compare' else req.algorithm
    paths=yen_paths(graph,start,goal,outputs[chosen],chosen,heuristic,limit=3)
    routes=[]
    for index,path in enumerate(paths):
        cost,seconds,distance=path_label(path)
        exposure=sum(e.exposure_km for e in path)
        geometry=[];items=[];high_km=unknown_km=0.
        for edge in path:
            segment,reverse=details[edge.key];ob=latest.get(segment.id);density=ob.density if ob else None
            points=list(reversed(segment.geometry)) if reverse else segment.geometry
            geometry+=points if not geometry or geometry[-1]!=points[0] else points[1:]
            high_km+=edge.distance_km if density=='HIGH' else 0
            unknown_km+=edge.distance_km if density is None else 0
            items.append({'id':segment.id,'name':segment.name,'distance_km':edge.distance_km,'density':density,
                'source':ob.source if ob else None,'geometry':points,'one_way':segment.one_way,
                'evidence_days':getattr(ob,'evidence_days',None)})
        routes.append({'id':f'demo-{index}','name':' → '.join(item['name'] for item in items),
            'duration_seconds':round(seconds),'distance_km':round(distance,2),'risk':round(exposure/distance,3),
            'risk_exposure_km':exposure,'optimization_cost':cost,'raw_criteria':(seconds,distance,exposure),
            'cost_components':{'time':w['time']*seconds/time_ref,'distance':w['distance']*distance/distance_ref,'density':w['density']*exposure/distance_ref},
            'high_share':round(high_km/distance,3),'unknown_share':round(unknown_km/distance,3),
            'geometry':geometry,'segments':items,'traffic_intervals':[]})
    metadata={'scope':'configured_network','requested_algorithm':req.algorithm,'algorithm':chosen,
        'agreement':agreement,'primary_search':stats,'normalized_weights':w,'references':{'time_seconds':time_ref,'distance_km':distance_ref},
        'heuristic':heuristic_info,'objective':'weighted_time_distance_exposure',
        'contains_demo_roads':any(details[e.key][0].is_demo for path in paths for e in path),
        'note':'Hai thuật toán dùng cùng snapshot và hàm chi phí. Số nút/thời gian chỉ đo lượt tìm tuyến chính, chưa gồm chuẩn hóa và tuyến thay thế.'}
    return rank_routes(routes,req.weights,(time_ref,distance_ref)),metadata


def decode_polyline(encoded):
    points, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        values = []
        for _ in range(2):
            shift = value = 0
            while True:
                b = ord(encoded[index])-63
                index += 1
                value |= (b & 31) << shift
                shift += 5
                if b < 32:
                    break
            values.append(~(value >> 1) if value & 1 else value >> 1)
        lat += values[0]
        lng += values[1]
        points.append([lat/1e5,lng/1e5])
    return points

def point_distance_to_line(point, line):
    # Local equirectangular projection in metres, appropriate for Hanoi.
    def xy(p):
        return ((p[1]-point[1])*111320*math.cos(math.radians(point[0])),(p[0]-point[0])*111320)
    best = float('inf')
    for a,b in zip(line,line[1:]):
        ax,ay = xy(a); bx,by = xy(b)
        dx,dy = bx-ax,by-ay
        t = max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
        best = min(best,math.hypot(ax+t*dx,ay+t*dy))
    return best

async def google_routes(db, req):
    key = os.getenv('GOOGLE_ROUTES_API_KEY')
    if not key:
        raise HTTPException(503, 'Chưa cấu hình Google Routes API. Hãy dùng chế độ minh họa hoặc liên hệ quản trị viên.')
    def waypoint(p):
        return {'location':{'latLng':{'latitude':p.lat,'longitude':p.lng}}}
    payload = {'origin':waypoint(req.origin),'destination':waypoint(req.destination),'travelMode':req.mode,'routingPreference':'TRAFFIC_AWARE','computeAlternativeRoutes':True,'extraComputations':['TRAFFIC_ON_POLYLINE'],'polylineQuality':'HIGH_QUALITY','languageCode':'vi-VN','units':'METRIC'}
    if req.departure_at:
        payload['departureTime'] = req.departure_at.isoformat().replace('+00:00','Z')
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post('https://routes.googleapis.com/directions/v2:computeRoutes', json=payload, headers={'X-Goog-Api-Key':key,'X-Goog-FieldMask':'routes.duration,routes.staticDuration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.travelAdvisory.speedReadingIntervals,routes.description'})
    except httpx.TimeoutException:
        raise HTTPException(504, 'Google Routes phản hồi quá chậm. Vui lòng thử lại.')
    except httpx.RequestError:
        raise HTTPException(502, 'Không kết nối được Google Routes.')
    if response.status_code == 429:
        raise HTTPException(429, 'Google Routes đã hết hạn mức. Vui lòng thử lại sau.')
    if response.status_code >= 400:
        raise HTTPException(502, 'Google không tính được tuyến cho yêu cầu này. Kiểm tra phương tiện, vùng hỗ trợ hoặc cấu hình API.')
    raw_routes = response.json().get('routes', [])
    if not raw_routes:
        raise HTTPException(404, 'Google không tìm thấy tuyến đường phù hợp.')
    segments = {s.id:s for s in db.find(Segment,{'active':True,'is_demo':False})}
    latest = route_evidence(db,req,list(segments.values()))
    routes = []
    for i, raw in enumerate(raw_routes):
        geometry = decode_polyline(raw['polyline']['encodedPolyline'])
        intervals = raw.get('travelAdvisory',{}).get('speedReadingIntervals',[])
        high_fraction = slow_fraction = covered = 0
        normalized = []
        for interval in intervals:
            start = interval.get('startPolylinePointIndex',0)
            end = interval.get('endPolylinePointIndex',len(geometry)-1)
            # Distance weighting instead of vertex counts (polyline point spacing varies).
            meters = sum(math.hypot((b[0]-a[0])*111320,(b[1]-a[1])*111320*math.cos(math.radians(a[0]))) for a,b in zip(geometry[start:end+1],geometry[start+1:end+1]))
            covered += meters
            if interval['speed'] == 'TRAFFIC_JAM': high_fraction += meters
            if interval['speed'] == 'SLOW': slow_fraction += meters
            normalized.append({'start':start,'end':end,'speed':interval['speed']})
        distance = raw['distanceMeters']/1000
        denominator = max(1,raw['distanceMeters'])
        risk = (high_fraction+.35*slow_fraction+.5*max(0,denominator-covered))/denominator
        matches = []
        for sid, ob in latest.items():
            seg = segments.get(sid)
            if not seg: continue
            middle = [(seg.geometry[0][0]+seg.geometry[-1][0])/2,(seg.geometry[0][1]+seg.geometry[-1][1])/2]
            if all(point_distance_to_line(p,geometry) <= 80 for p in [*seg.geometry,middle]):
                matches.append({'id':sid,'name':seg.name,'density':ob.density,'source':ob.source,'distance_km':seg.distance_km,'geometry':seg.geometry,'evidence_days':getattr(ob,'evidence_days',None)})
        # Camera observations affect risk, never overwrite the provider's measured ETA.
        if matches:
            camera_risk = max({'LOW':.05,'NORMAL':.35,'HIGH':1}[s['density']] for s in matches)
            risk = max(risk, camera_risk*min(1,sum(s['distance_km'] for s in matches)/max(distance,.01)))
        routes.append({'id':f'google-{i}','name':raw.get('description') or f'Tuyến {i+1}','duration_seconds':round(float(raw['duration'].removesuffix('s'))),'distance_km':round(distance,2),'risk':round(min(1,risk),3),'high_share':round(high_fraction/denominator,3),'unknown_share':round(max(0,denominator-covered)/denominator,3),'geometry':geometry,'segments':matches,'traffic_intervals':normalized})
    return routes

async def search_routes(db, req):
    if req.provider=='osm':
        from .osm_routing import osm_routes
        routes,optimization=await osm_routes(db,req)
    elif req.provider=='google':
        routes=rank_routes(await google_routes(db,req),req.weights)
        optimization={'scope':'google_candidates','algorithm':None,'agreement':None,'primary_search':{},
            'normalized_weights':normalized_weights(req.weights),
            'references':{'time_seconds':max(1,min(r['duration_seconds'] for r in routes)),
                          'distance_km':max(.001,min(r['distance_km'] for r in routes))},
            'objective':'weighted_time_distance_exposure',
            'note':'Chỉ so sánh các tuyến Google trả về. Dijkstra/A* không truy cập đồ thị đường nội bộ của Google.'}
    else:
        routes,optimization=demo_routes(db,req)
    best=routes[0]
    reason=f'Tuyến được chọn có ETA {round(best["duration_seconds"]/60)} phút, dài {best["distance_km"]} km; điểm tổng hợp {best["score"]:.3f} theo trọng số của bạn.'
    if optimization['scope'] in ('configured_network','osm_network'):
        reason+=' Tối ưu chi phí kết hợp ngay trên đồ thị bằng '+('Dijkstra và A* đã đối chiếu.' if req.algorithm=='compare' else ('Dijkstra.' if req.algorithm=='dijkstra' else 'A*.'))
    if best['unknown_share']: reason+=f' {round(best["unknown_share"]*100)}% tuyến chưa có dữ liệu giao thông; chưa thể khẳng định không tắc.'
    if any(s.get('source')=='forecast' for s in best['segments']): reason+=' Có sử dụng mô hình dự báo đã được kích hoạt, tại mốc gần giờ khởi hành.'
    if any(s.get('source')=='historical' for s in best['segments']): reason+=' Có sử dụng thống kê 28 ngày gần nhất cùng thứ và giờ; đây là tham khảo lịch sử.'
    notice=('Mạng đường, khoảng cách và ETA minh họa; không dùng để dẫn đường thực tế.' if optimization.get('contains_demo_roads') else
        'Tối ưu trong mạng đường đã cấu hình; ETA ước tính từ vận tốc tham chiếu theo mật độ, chưa phải phép đo tốc độ thực tế.') if req.provider=='demo' else 'Chọn trong các tuyến Google cung cấp, giữ ETA Google. Camera/dự báo chỉ bổ sung rủi ro theo vị trí.'
    if req.provider=='osm':
        notice='© OpenStreetMap contributors. Tuyến bám đường OSM trong vùng tải; ghim được nối vào đường phù hợp gần nhất (tối đa 200 m). Đoạn từ cửa nhà tới điểm nối chưa được xác minh và không tính vào ETA. Tôn trọng chiều đường, quyền phương tiện, giới hạn rộng đã gắn thẻ và hạn chế rẽ qua nút; đường có hạn chế điều kiện/phức tạp chưa xử lý được loại thận trọng. Dữ liệu có thể thiếu hoặc thay đổi; kiểm tra biển báo thực tế.'
    return {'provider':req.provider,'generated_at':stamp(),'routes':routes,'recommendation':{'route_id':best['id'],'reason':reason},
        'optimization':optimization,'notice':notice,'future_notice':'Dự báo hoặc lịch sử chỉ dùng khi đủ bằng chứng và phù hợp giờ khởi hành. Chi phí cạnh là snapshot tại giờ khởi hành, chưa cập nhật theo thời điểm đến từng đoạn.' if req.departure_at else None}
