from datetime import datetime, timedelta
from .db import now
from .models import Observation, AlertRule, Notification, Segment
from .config import TTL_MINUTES

LABELS = {'LOW':'Thấp','NORMAL':'Bình thường','HIGH':'Cao'}

def classify(score, low=.25, high=.6):
    return 'LOW' if score < low else 'NORMAL' if score < high else 'HIGH'

def latest_observations(db):
    cutoff = (now() - timedelta(minutes=TTL_MINUTES)).isoformat()
    rows = db.find(Observation,{'observed_at':{'$gte':cutoff,'$lte':now().isoformat()}},sort=[('observed_at',-1),('id',-1)])
    result = {}
    for row in rows:
        result.setdefault(row.segment_id, row)
    return result

def observation_dict(row):
    return {key:getattr(row,key) for key in ('id','segment_id','camera_id','density','score','count','source','note','observed_at','created_at')}

def emit_alerts(db, observation):
    # Only a latest, fresh observation can trigger an alert. Ten-minute cooldown.
    latest = latest_observations(db).get(observation.segment_id)
    if not latest or latest.id != observation.id:
        return
    segment = db.get(Segment, observation.segment_id)
    for rule in db.find(AlertRule,{'active':True,'segment_id':observation.segment_id,'density':observation.density}):
        cutoff=(now()-timedelta(minutes=10)).isoformat()
        claimed=db.update(AlertRule,rule.id,{'last_sent':now().isoformat()},condition={'$or':[{'last_sent':None},{'last_sent':{'$lte':cutoff}}]})
        if not claimed: continue
        db.add(Notification(user_id=rule.user_id, message=f'{segment.name}: mật độ {LABELS[observation.density].lower()} lúc {observation.observed_at}. Nguồn: {observation.source}.'))
