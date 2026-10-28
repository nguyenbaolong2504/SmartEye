import heapq
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

def rank_routes(routes, weights):
    total = sum(weights.values())
    w = {k:v/total for k,v in weights.items()}
    max_time = max(r['duration_seconds'] for r in routes) or 1
    max_km = max(r['distance_km'] for r in routes) or 1
    for r in routes:
        r['score'] = round(w['time']*r['duration_seconds']/max_time + w['distance']*r['distance_km']/max_km + w['density']*r['risk'], 5)
        r['badges'] = []
        r['dominated'] = any(all(o[k] <= r[k] for k in ('duration_seconds','distance_km','risk')) and any(o[k] < r[k] for k in ('duration_seconds','distance_km','risk')) for o in routes if o is not r)
    for key, label in [('duration_seconds','Nhanh nhất'),('distance_km','Ngắn nhất'),('risk','Ít rủi ro nhất')]:
        best = min(r[key] for r in routes)
        for r in routes:
            if abs(r[key] - best) < .00001:
                r['badges'].append(label)
    # Exclude dominated routes so zero weights cannot select a strictly worse route.
    candidates = [r for r in routes if not r['dominated']]
    selected = min(candidates, key=lambda r:(r['score'], r['duration_seconds'], r['distance_km']))
    selected['recommended'] = True
    for r in routes:
        r.setdefault('recommended', False)
    return sorted(routes, key=lambda r:(not r['recommended'],r['score']))

def demo_routes(db, req):
    valid_nodes = {p['node'] for p in PLACES}
    if req.origin.node not in valid_nodes or req.destination.node not in valid_nodes:
        raise HTTPException(422, 'Chế độ minh họa chỉ hỗ trợ các địa điểm có sẵn trong danh sách.')
    if req.origin.node == req.destination.node:
        raise HTTPException(422, 'Điểm đi và điểm đến phải khác nhau.')
    segments = db.find(Segment,{'active':True})
    latest = route_evidence(db,req,segments)
    adjacency = {}
    speeds = {'LOW':35 if req.mode == 'DRIVE' else 30,'NORMAL':22 if req.mode == 'DRIVE' else 24,'HIGH':9 if req.mode == 'DRIVE' else 12,None:25}
    for seg in segments:
        ob = latest.get(seg.id)
        density = ob.density if ob else None
        minutes = seg.distance_km/speeds[density]*60
        adjacency.setdefault(seg.start_node, []).append((seg.end_node, seg, minutes, False))
        adjacency.setdefault(seg.end_node, []).append((seg.start_node, seg, minutes, True))
    queue = [(0, 0, req.origin.node, [req.origin.node], [])]
    serial = 1
    paths = []
    while queue and len(paths) < 3:
        elapsed, _, node, visited, edges = heapq.heappop(queue)
        if node == req.destination.node:
            paths.append((elapsed, edges))
            continue
        for nxt, seg, minutes, reverse in adjacency.get(node, []):
            if nxt in visited:
                continue
            heapq.heappush(queue,(elapsed+minutes,serial,nxt,visited+[nxt],edges+[(seg,reverse)]))
            serial += 1
    if not paths:
        raise HTTPException(404, 'Không tìm thấy tuyến trong mạng đường minh họa.')
    routes = []
    for index, (minutes, edges) in enumerate(paths):
        details, geometry = [], []
        distance = sum(s.distance_km for s,_ in edges)
        risk, high_km, unknown_km = 0., 0., 0.
        for seg, reverse in edges:
            ob = latest.get(seg.id)
            density = ob.density if ob else None
            points = list(reversed(seg.geometry)) if reverse else seg.geometry
            geometry += points if not geometry else points[1:]
            risk += seg.distance_km*({'LOW':.05,'NORMAL':.35,'HIGH':1,None:.5}[density])
            high_km += seg.distance_km if density == 'HIGH' else 0
            unknown_km += seg.distance_km if density is None else 0
            details.append({'id':seg.id,'name':seg.name,'distance_km':seg.distance_km,'density':density,'source':ob.source if ob else None,'geometry':points,'evidence_days':getattr(ob,'evidence_days',None)})
        routes.append({'id':f'demo-{index}','name':' → '.join(s.name for s,_ in edges),'duration_seconds':round(minutes*60),'distance_km':round(distance,2),'risk':round(risk/distance,3),'high_share':round(high_km/distance,3),'unknown_share':round(unknown_km/distance,3),'geometry':geometry,'segments':details,'traffic_intervals':[]})
    return routes

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
    routes = await google_routes(db,req) if req.provider == 'google' else demo_routes(db,req)
    routes = rank_routes(routes,req.weights)
    best = routes[0]
    reason = f'Tuyến được chọn có ETA {round(best["duration_seconds"]/60)} phút, dài {best["distance_km"]} km; điểm tổng hợp {best["score"]:.3f} theo trọng số của bạn.'
    if best['unknown_share']:
        reason += f' {round(best["unknown_share"]*100)}% tuyến chưa có dữ liệu giao thông; chưa thể khẳng định không tắc.'
    if any(s.get('source')=='forecast' for s in best['segments']):
        reason += ' Có sử dụng mô hình dự báo đã được kích hoạt, tại mốc gần giờ khởi hành.'
    if any(s.get('source')=='historical' for s in best['segments']):
        reason += ' Có sử dụng thống kê 28 ngày gần nhất cùng thứ và giờ; đây là tham khảo lịch sử.'
    return {'provider':req.provider,'generated_at':stamp(),'routes':routes,'recommendation':{'route_id':best['id'],'reason':reason},'notice':'Mạng đường, khoảng cách và ETA minh họa; không dùng để dẫn đường thực tế.' if req.provider == 'demo' else 'ETA do Google cung cấp. Dữ liệu camera bổ sung rủi ro theo vị trí; mật độ cao không đồng nghĩa chắc chắn ùn tắc.','future_notice':'Với giờ khởi hành cách hiện tại trên 5 phút, camera chỉ đóng góp thống kê lịch sử đủ dữ liệu cùng thứ/giờ; chưa phải dự báo chắc chắn.' if req.departure_at else None}
