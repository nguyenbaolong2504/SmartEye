"""Video-conditioned density forecasts for an explicitly synthetic sandbox."""
import json
import uuid
from datetime import datetime,timedelta
import numpy as np
from .config import DATA
from .db import now,stamp
from .demo_data import require_active,rows_for,feature_row
from .forecast_data import CLASSES,examples,features,split_indices,STEP
from .history import LOCAL
from .traffic import classify
from .camera_context import FEATURES,training_row,vector

HORIZONS=(15,30,60)
VERSION=3
FOLDER=DATA/'camera-density'
_models={}


def density_row(row):
    value=dict(row)
    label=classify(value['score'],.25,.6)
    value.update(severity=CLASSES['density'].index(label),high_share=int(label=='HIGH'),low_share=int(label=='LOW'))
    return value


def model_folder(active):
    return FOLDER/str(uuid.UUID(active['run_id']))/f'v{VERSION}'


def probabilities(raw,temperature=1.):
    logits=np.log(np.clip(np.asarray(raw,dtype=float),1e-9,1))/temperature
    logits-=logits.max(axis=1,keepdims=True)
    values=np.exp(logits)
    return values/values.sum(axis=1,keepdims=True)


def negative_log_loss(y,p):
    return float(-np.log(np.clip(p[np.arange(len(y)),y],1e-9,1)).mean())


def fit_temperature(y,p):
    from scipy.optimize import minimize_scalar
    return float(minimize_scalar(lambda t:negative_log_loss(y,probabilities(p,t)),
        bounds=(.2,5.),method='bounded').x)


def prepare_models(database,estimators=80):
    from xgboost import XGBClassifier
    from .forecast_ml import metrics
    active=require_active(database)
    folder=model_folder(active)
    if (folder/'metadata.json').is_file() and all((folder/f'{target}-{h}.json').is_file() for h in HORIZONS for target in CLASSES):
        return json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    today=now().astimezone(LOCAL).date()
    query={'dataset_id':active['run_id'],'segment_id':{'$in':active['segment_ids']},
           'date':{'$gte':(today-timedelta(days=8)).isoformat(),'$lt':today.isoformat()}}
    series={sid:{} for sid in active['segment_ids']};labels={};conditions={}
    for doc in database.demo_profiles.find(query):
        day=datetime.fromisoformat(doc['date']).date()
        for slot in doc['slots']:
            sid=doc['segment_id']
            adjusted,label,context=training_row(feature_row(day,slot),sid)
            row=density_row(adjusted)
            series[sid][row['at']]=row
            labels[(sid,row['at'])]=label
            conditions[(sid,row['at'])]=vector(context)
    folder.mkdir(parents=True,exist_ok=True)
    report={'version':VERSION,'is_demo':True,'target':'density_and_congestion','model':'XGBoost','run_id':active['run_id'],
            'segment_ids':active['segment_ids'],'created_at':stamp(),'horizons':{},
            'condition_features':list(FEATURES),'condition_training':'synthetic_not_real_world_validated'}
    for horizon in HORIZONS:
      report['horizons'][str(horizon)]={}
      for target in CLASSES:
        data=examples(series,labels,active['segment_ids'],target,horizon)
        train,validation,test=split_indices(data,horizon)
        midpoint=np.unique(data['times'][validation])[len(np.unique(data['times'][validation]))//2]
        early=validation[data['times'][validation]+horizon*60<midpoint]
        calibration=validation[data['times'][validation]>=midpoint]
        if min(len(early),len(calibration))<25:raise ValueError('Chưa đủ dữ liệu riêng cho hiệu chỉnh xác suất.')
        extra=np.asarray([conditions[(int(sid),datetime.fromtimestamp(at,LOCAL))]
                          for sid,at in zip(data['roads'],data['times'])],dtype=np.float32)
        raw=np.concatenate([data['x'].reshape(len(data['x']),-1),extra],axis=1)
        mean=raw[train].mean(axis=0)
        std=np.maximum(raw[train].std(axis=0),.001)
        x=((raw-mean)/std).astype(np.float32)
        model=XGBClassifier(n_estimators=estimators,max_depth=4,learning_rate=.08,subsample=.9,
            colsample_bytree=.9,objective='multi:softprob',num_class=3,tree_method='hist',
            n_jobs=1,random_state=42,eval_metric='mlogloss',early_stopping_rounds=10)
        model.fit(x[train],data['y'][train],eval_set=[(x[early],data['y'][early])],verbose=False)
        temperature=fit_temperature(data['y'][calibration],model.predict_proba(x[calibration]))
        test_prob=probabilities(model.predict_proba(x[test]),temperature)
        pending=folder/f'{target}-{horizon}.pending.json'
        model.save_model(pending);pending.replace(folder/f'{target}-{horizon}.json')
        report['horizons'][str(horizon)][target]={'mean':mean.tolist(),'std':std.tolist(),'temperature':temperature,
            'validation':metrics(data['y'][early],model.predict(x[early])),
            'test':metrics(data['y'][test],model.predict(x[test])),
            'baseline':metrics(data['y'][test],data['baseline'][test]),
            'test_log_loss':negative_log_loss(data['y'][test],test_prob),
            'test_high_brier':float(np.mean((test_prob[:,2]-(data['y'][test]==2))**2)),
            'train_label_end':float((data['times'][train]+horizon*60).max()),
            'validation_issue_start':float(data['times'][early].min()),
            'validation_label_end':float((data['times'][early]+horizon*60).max()),
            'calibration_issue_start':float(data['times'][calibration].min()),
            'calibration_label_end':float((data['times'][calibration]+horizon*60).max()),
            'test_issue_start':float(data['times'][test].min())}
    pending=folder/'metadata.pending'
    pending.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    pending.replace(folder/'metadata.json')
    return report


def history_evidence(database,active,segment_id,issue):
    cutoff=issue.date();documents=list(database.demo_profiles.find({'dataset_id':active['run_id'],
        'segment_id':segment_id,'date':{'$gte':(cutoff-timedelta(days=100)).isoformat(),'$lt':cutoff.isoformat()}},
        {'date':1,'slots':1}))
    output={}
    for horizon in HORIZONS:
        target=issue+timedelta(minutes=horizon);minute=target.hour*60+target.minute
        values=[slot for doc in documents if datetime.fromisoformat(doc['date']).weekday()==target.weekday()
                for slot in doc['slots'] if slot['minute']==minute]
        output[horizon]={'is_demo':True,'lookback_days':100,'matching_days':len(values),
            'jam_days':sum(row['state']=='JAM' for row in values),'same_weekday':True,'hour':target.strftime('%H:%M')}
    return output


def normalized_score(score,low,high):
    if score<low:return score/max(low,.001)*.25
    if score<high:return .25+(score-low)/max(high-low,.001)*.35
    return min(1,.6+(score-high)/max(1-high,.001)*.4)


def predict_samples(database,segment_id,samples,config,issue=None,conditions=None):
    from xgboost import XGBClassifier
    active=require_active(database)
    if segment_id not in active['segment_ids']:raise ValueError('Tuyến chưa có lịch sử minh họa để chạy thử dự báo.')
    folder=model_folder(active)
    if not (folder/'metadata.json').is_file():raise ValueError('Cần chuẩn bị mô hình dự báo camera trước.')
    if active['run_id'] not in _models:
        metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        models={}
        for horizon in HORIZONS:
          for target in CLASSES:
            model=XGBClassifier(n_jobs=1);model.load_model(folder/f'{target}-{horizon}.json');models[(horizon,target)]=model
        if len(_models)>=2:_models.pop(next(iter(_models)))
        _models[active['run_id']]=(metadata,models)
    metadata,models=_models[active['run_id']]
    issue=(issue or now()).astimezone(LOCAL)
    issue=issue.replace(minute=issue.minute//5*5,second=0,microsecond=0)
    rows=[density_row(training_row(row,segment_id)[0]) for row in rows_for(database,active,segment_id,issue-timedelta(hours=2),issue)][-12:]
    if len(rows)!=12 or any(rows[i]['at']-rows[i-1]['at']!=STEP for i in range(1,12)):
        raise ValueError('Chưa đủ lịch sử minh họa cho thời điểm chạy thử.')
    # Production facts are supplied by the resolver; missing data stays explicitly unknown.
    conditions=conditions or {'weather':{'known':False},'road':{'checked':False},'is_demo':True}
    inputs=[]
    for sample in samples:
        last=dict(rows[-1],score=normalized_score(sample['score'],config['low_threshold'],config['high_threshold']),count=sample['count'])
        context=rows[:-1]+[density_row(last)]
        inputs.append(np.concatenate([features(context,active['segment_ids'],segment_id).reshape(-1),vector(conditions)]))
    raw=np.asarray(inputs,dtype=np.float32)
    evidence=history_evidence(database,active,segment_id,issue)
    output=[{'second':sample['second'],'predictions':[]} for sample in samples]
    for horizon in HORIZONS:
      predictions=[{'horizon_minutes':horizon,'history':evidence[horizon]} for _ in samples]
      for target in CLASSES:
        info=metadata['horizons'][str(horizon)][target]
        x=((raw-np.asarray(info['mean']))/np.asarray(info['std'])).astype(np.float32)
        p=probabilities(models[(horizon,target)].predict_proba(x),info['temperature'])
        for row,values in zip(predictions,p):
            distribution={name:round(float(value),6) for name,value in zip(CLASSES[target],values)}
            label=CLASSES[target][int(values.argmax())]
            if target=='density':row.update(label=label,probabilities=distribution)
            else:row.update(congestion_label=label,congestion_probability=distribution['JAM'],congestion_probabilities=distribution)
      for row,prediction in zip(output,predictions):row['predictions'].append(prediction)
    return {'version':VERSION,'is_demo':True,'target':'density_and_congestion','model':'XGBoost','run_id':active['run_id'],
        'reference_at':issue.isoformat(),'context_minutes':60,'synthetic_context_slots':11,
        'probability_kind':'calibrated_synthetic','real_world_validated':False,
        'conditions':conditions,
        'message':'Xét lượng xe, lịch sử cùng giờ, sự cố, điều kiện đường và thời tiết có thông tin.','timeline':output}
