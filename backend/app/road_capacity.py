"""Camera-specific storage/density estimates, not universal congestion thresholds."""
import math
from collections import deque
import numpy as np

VERSION=1
# Demo equivalents and spacing, to be replaced by calibration on the actual road.
EQUIVALENTS={'car':1.,'motorcycle':.25,'bus':3.,'truck':2.5}
CAR_SPACE_M2=21.


def geometry(config):
    profile=config.get('road_profile')
    if not profile:return None
    area=profile['road_width_m']*profile['observed_length_m']*profile.get('usable_fraction',.85)
    capacity=area/CAR_SPACE_M2
    return {**profile,'usable_area_m2':round(area,2),'capacity_pcu':round(capacity,3),
        'car_space_m2':CAR_SPACE_M2,'equivalents':EQUIVALENTS,'version':VERSION,
        'high_density_pcu':round(capacity*config.get('high_threshold',.6),2),
        'calibration_note':'Kích thước và hệ số chạy thử; cần đo, hiệu chỉnh tại đúng vùng camera quan sát.'}


def frame_load(counts,config):
    info=geometry(config)
    if not info:return {}
    equivalent=sum(counts.get(kind,0)*weight for kind,weight in EQUIVALENTS.items())
    return {'equivalent_count':round(equivalent,3),'capacity_pcu':info['capacity_pcu'],
            'load_ratio':round(equivalent/info['capacity_pcu'],4)}


def motion_evidence(frames):
    """Relative body-length motion, not km/h. Requires a stable camera and track."""
    tracks={};output=[];camera_offset=np.zeros(2);queue_since=None
    for frame in frames:
        at=frame['second'];camera_offset+=np.asarray(frame.get('camera_shift',[0.,0.]))
        speeds=[]
        for box in frame['boxes']:
            ident=box.get('track_id')
            if ident is None:continue
            a,b,c,d=box['box'];centre=np.asarray([(a+c)/2,(b+d)/2])-camera_offset
            body=max(4.,math.hypot(c-a,d-b))
            history=tracks.setdefault(ident,deque())
            while history and at-history[0][0]>1.5:history.popleft()
            history.append((at,centre,body))
            if len(history)>=3 and at-history[0][0]>=.75:
                elapsed=at-history[0][0]
                distance=float(np.linalg.norm(centre-history[0][1]))
                speeds.append(distance/(max(body,history[0][2])*elapsed))
        if len(tracks)>500:
            tracks={ident:history for ident,history in tracks.items() if history and at-history[-1][0]<3}
        coverage=len(speeds)/max(1,frame['count'])
        known=len(speeds)>=max(2,math.ceil(frame['count']*.3)) and coverage>=.3
        stopped=sum(value<.12 for value in speeds)/len(speeds) if known else None
        slow=known and stopped>=.5 and frame.get('load_ratio',frame['score'])>=.6
        queue_since=(queue_since if queue_since is not None else at) if slow else None
        duration=at-queue_since if queue_since is not None else 0.
        output.append({**frame,'motion_known':known,'motion_coverage':round(coverage,3),
            'motion_samples':len(speeds),'stopped_share':round(stopped,3) if stopped is not None else None,
            'motion_body_lengths_per_second':round(float(np.median(speeds)),3) if known else None,
            'queue_seconds':round(duration,2),'persistent_queue':bool(slow and duration>=30)})
    return output
