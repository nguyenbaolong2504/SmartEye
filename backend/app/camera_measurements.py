"""Line crossings and calibrated ground-plane motion from frozen tracked boxes.

No model inference here: cached YOLO/ByteTrack results can be reprocessed cheaply.
Bottom-centre points approximate tyre contact with the measured road plane.
"""
from collections import Counter, deque
import math
import numpy as np
from .traffic_metrics import quantities

VERSION=2


def measurement_frames(frames, config, fps):
    profile = config.get('road_profile') or {}
    calibration = profile.get('measurement') or {}
    line = calibration.get('count_line')
    # A default virtual line is a demo counter, never a verified survey boundary.
    if not line:
        x1,y1,x2,y2 = config.get('roi', [0,0,1,1])
        line = [[x1,(y1+y2)/2], [x2,(y1+y2)/2]]
    a,b = np.asarray(line, dtype=float)
    ab = b-a; norm = float(np.linalg.norm(ab))
    ground = calibration.get('ground_points')
    measured = calibration.get('verified', False) and profile.get('calibration') == 'measured'
    matrix = None
    if measured and ground:
        import cv2
        image = np.asarray(calibration['image_points'], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(image, np.asarray(ground,dtype=np.float32))
    histories = {}; sides = {}; counted = set(); totals = Counter(); events=[]; output=[]
    direction = calibration.get('crossing_direction','both')
    start = frames[0]['second'] if frames else 0
    camera_offset=np.zeros(2);unstable=False
    for frame in frames:
        at = frame['second']; speeds=[]; distances=[]; times=[]
        width,height = frame['width'],frame['height']
        shift=np.asarray(frame.get('camera_shift',[0,0]),dtype=float)
        camera_offset+=shift
        if np.linalg.norm(shift/np.asarray([width,height]))>=.003 or np.linalg.norm(camera_offset/np.asarray([width,height]))>=.01:
            unstable=True
        polygon=np.asarray(calibration['image_points'],dtype=np.float32) if matrix is not None else None
        present=frame['count']
        if polygon is not None:
            import cv2
            present=sum(cv2.pointPolygonTest(polygon,((box['box'][0]+box['box'][2])/2/width,box['box'][3]/height),False)>=0 for box in frame.get('boxes',[]))
        for box in frame.get('boxes',[]):
            ident = box.get('track_id')
            if ident is None: continue
            x1,y1,x2,y2 = box['box']; point = np.asarray([(x1+x2)/2/width,y2/height])
            side = float((ab[0]*(point-a)[1]-ab[1]*(point-a)[0])/norm)
            previous = sides.get(ident)
            # Hysteresis rejects jitter on the line; count a confirmed ID once.
            if abs(side) >= .005:
                sign = 1 if side>0 else -1
                if previous and previous[0] != sign and at-previous[2] <= 2 and ident not in counted:
                    old_sign,old_point,_ = previous
                    travel=point-old_point
                    denominator = float(travel[0]*ab[1]-travel[1]*ab[0])
                    if abs(denominator)>1e-10:
                        delta=a-old_point
                        u=float((delta[0]*travel[1]-delta[1]*travel[0])/denominator)
                        permitted=direction=='both' or (direction=='positive' and sign>0) or (direction=='negative' and sign<0)
                        if 0<=u<=1 and permitted:
                            counted.add(ident); label=box.get('counted_as') or box['label'];totals[label]+=1
                            events.append({'second':at,'track_id':ident,'label':label,'direction':'positive' if sign>0 else 'negative'})
                sides[ident]=(sign,point,at)
            if matrix is None: continue
            import cv2
            if cv2.pointPolygonTest(polygon,tuple(point),False)<0:continue
            position=cv2.perspectiveTransform(np.asarray([[point]],dtype=np.float32),matrix)[0,0]
            trail=histories.setdefault(ident,deque())
            if trail and at-trail[-1][0]>.5:trail.clear()
            trail.append((at,position))
            while trail and at-trail[0][0]>1.5:trail.popleft()
            if len(trail)<3 or at-trail[0][0]<.75:continue
            elapsed=at-trail[0][0];distance=float(np.linalg.norm(position-trail[0][1]));speed=distance/elapsed*3.6
            if not math.isfinite(speed) or speed>160:continue
            speeds.append(speed);distances.append(distance);times.append(elapsed)
        # A moving source invalidates a fixed homography. Relative motion remains
        # available elsewhere but it cannot silently become calibrated km/h.
        known=bool(matrix is not None and not unstable and len(speeds)>=max(2,math.ceil(present*.3)))
        speed=3.6*sum(distances)/sum(times) if known else None
        elapsed=max(1/fps,at-start+1/fps)
        metrics=quantities(present_count=present,length_m=profile.get('observed_length_m'),
            lanes=profile.get('lanes'),crossings=sum(totals.values()) if elapsed>=10 and not unstable else None,
            observed_seconds=elapsed,speed_kmh=speed,free_flow_speed_kmh=calibration.get('free_flow_speed_kmh'),
            length_verified=profile.get('calibration')=='measured' and not unstable,speed_verified=known)
        metrics['quality'].update(count_line_verified=bool(calibration.get('count_line') and measured and not unstable),camera_stable=not unstable,
            speed_tracks=len(speeds),speed_coverage=len(speeds)/max(1,present),
            observation_seconds=elapsed,short_window=elapsed<300)
        output.append({**frame,'traffic_metrics':metrics,'crossing_count':sum(totals.values()),
            'crossing_vehicle_counts':dict(totals)})
        if len(histories)>500:histories={key:trail for key,trail in histories.items() if trail and at-trail[-1][0]<3}
    return output, {'version':VERSION,'count_line':line,'crossing_direction':direction,
        'count_line_verified':bool(calibration.get('count_line') and measured and not unstable),'events':events,'camera_stable':not unstable,
        'crossings':sum(totals.values()),'vehicle_counts':dict(totals),
        'speed_calibration_available':matrix is not None and not unstable,
        'note':'Mỗi mã xe qua vạch được cộng một lần; clip ngắn chỉ cung cấp lưu lượng quy đổi, không phải quan trắc đủ 5 phút.'}


def attach(result, config):
    if result.get('measurement_version')==VERSION:return result
    source=result.get('frames') or result.get('samples') or []
    if not source or not all(row.get('width') and row.get('height') for row in source):return result
    frames,details=measurement_frames(source,config,result.get('fps',1))
    return {**result,'frames':frames,'measurements':details,'measurement_version':VERSION}
