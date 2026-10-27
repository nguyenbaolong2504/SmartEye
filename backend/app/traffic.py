from datetime import datetime, timedelta
from .db import now
from .models import Observation, AlertRule, Notification, Segment, Camera
from .config import TTL_MINUTES

LABELS = {'LOW':'Thấp','NORMAL':'Bình thường','HIGH':'Cao'}

def classify(score, low=.25, high=.6):
    return 'LOW' if score < low else 'NORMAL' if score < high else 'HIGH'

def latest_observations(db):
    cutoff = (now() - timedelta(minutes=TTL_MINUTES)).isoformat()
    rows = db.find(Observation,{'observed_at':{'$gte':cutoff,'$lte':now().isoformat()}},sort=[('observed_at',-1),('id',-1)])
    candidates = {}
    cameras = {c.id:c for c in db.find(Camera)}
    for row in rows:
        camera=cameras.get(row.camera_id) if row.camera_id is not None else None
        if row.camera_id is not None and (not camera or not camera.active or camera.segment_id!=row.segment_id): continue
        candidates.setdefault((row.segment_id,row.camera_id),row)
    pipeline = [{'$match':{'observed_at':{'$gte':cutoff,'$lte':now().isoformat()}}},
                {'$sort':{'observed_at':-1,'_id':-1}},
                {'$group':{'_id':'$camera_id','sample':{'$first':'$$ROOT'}}}]
    for item in db.database.traffic_samples.aggregate(pipeline):
        row=item['sample'];camera=cameras.get(row.get('camera_id'))
        if not camera or not camera.active or camera.segment_id!=row['segment_id']: continue
        previous=candidates.get((row['segment_id'],camera.id))
        if previous and previous.observed_at>=row['observed_at']: continue
        candidates[(row['segment_id'],camera.id)]=Observation(id=row.get('observation_id') or row['_id'],
            segment_id=row['segment_id'],user_id=0,camera_id=camera.id,job_id=row.get('job_id'),
            density=row['density'],score=row['score'],count=row['count'],source=row['source'],
            observed_at=row['observed_at'],note='Khung hình từ video đã công bố.')
    result = {}
    severity={'LOW':0,'NORMAL':1,'HIGH':2}
    for row in candidates.values():
        previous=result.get(row.segment_id)
        if not previous or (severity[row.density],row.score,row.observed_at)>(severity[previous.density],previous.score,previous.observed_at): result[row.segment_id]=row
    return result

def observation_dict(row):
    return {key:getattr(row,key) for key in ('id','segment_id','camera_id','density','score','count','source','note','observed_at','created_at')}

def emit_alerts(db, observation):
    # Only a latest, fresh observation can trigger an alert. Ten-minute cooldown.
    latest = latest_observations(db).get(observation.segment_id)
    if not latest or latest.id != observation.id:
        return
    observation = latest
    segment = db.get(Segment, observation.segment_id)
    for rule in db.find(AlertRule,{'active':True,'segment_id':observation.segment_id,'density':observation.density}):
        cutoff=(now()-timedelta(minutes=10)).isoformat()
        claimed=db.update(AlertRule,rule.id,{'last_sent':now().isoformat()},condition={'$or':[{'last_sent':None},{'last_sent':{'$lte':cutoff}}]})
        if not claimed: continue
        db.add(Notification(user_id=rule.user_id, message=f'{segment.name}: mật độ {LABELS[observation.density].lower()} lúc {observation.observed_at}. Nguồn: {observation.source}.'))
