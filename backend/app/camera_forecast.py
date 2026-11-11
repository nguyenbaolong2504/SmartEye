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

HORIZONS=(15,30,60)
FOLDER=DATA/'camera-density'
_models={}


def density_row(row):
    value=dict(row)
    label=classify(value['score'],.25,.6)
    value.update(severity=CLASSES['density'].index(label),high_share=int(label=='HIGH'),low_share=int(label=='LOW'))
    return value


def model_folder(active):
    return FOLDER/str(uuid.UUID(active['run_id']))


def prepare_models(database,estimators=80):
    from xgboost import XGBClassifier
    from .forecast_ml import metrics
    active=require_active(database)
    folder=model_folder(active)
    if (folder/'metadata.json').is_file() and all((folder/f'xgb-{h}.json').is_file() for h in HORIZONS):
        return json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    today=now().astimezone(LOCAL).date()
    query={'dataset_id':active['run_id'],'segment_id':{'$in':active['segment_ids']},
           'date':{'$gte':(today-timedelta(days=8)).isoformat(),'$lt':today.isoformat()}}
    series={sid:{} for sid in active['segment_ids']}
    for doc in database.demo_profiles.find(query):
        day=datetime.fromisoformat(doc['date']).date()
        for slot in doc['slots']:
            row=density_row(feature_row(day,slot))
            series[doc['segment_id']][row['at']]=row
    folder.mkdir(parents=True,exist_ok=True)
    report={'is_demo':True,'target':'density','model':'XGBoost','run_id':active['run_id'],
            'segment_ids':active['segment_ids'],'created_at':stamp(),'horizons':{}}
    for horizon in HORIZONS:
        data=examples(series,{},active['segment_ids'],'density',horizon)
        train,validation,test=split_indices(data,horizon)
        raw=data['x'].reshape(len(data['x']),-1)
        mean=raw[train].mean(axis=0)
        std=np.maximum(raw[train].std(axis=0),.001)
        x=((raw-mean)/std).astype(np.float32)
        model=XGBClassifier(n_estimators=estimators,max_depth=4,learning_rate=.08,subsample=.9,
            colsample_bytree=.9,objective='multi:softprob',num_class=3,tree_method='hist',
            n_jobs=1,random_state=42,eval_metric='mlogloss',early_stopping_rounds=10)
        model.fit(x[train],data['y'][train],eval_set=[(x[validation],data['y'][validation])],verbose=False)
        pending=folder/f'xgb-{horizon}.pending.json'
        model.save_model(pending);pending.replace(folder/f'xgb-{horizon}.json')
        report['horizons'][str(horizon)]={'mean':mean.tolist(),'std':std.tolist(),
            'validation':metrics(data['y'][validation],model.predict(x[validation])),
            'test':metrics(data['y'][test],model.predict(x[test])),
            'baseline':metrics(data['y'][test],data['baseline'][test]),
            'train_label_end':float((data['times'][train]+horizon*60).max()),
            'validation_issue_start':float(data['times'][validation].min()),
            'validation_label_end':float((data['times'][validation]+horizon*60).max()),
            'test_issue_start':float(data['times'][test].min())}
    pending=folder/'metadata.pending'
    pending.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    pending.replace(folder/'metadata.json')
    return report


def normalized_score(score,low,high):
    if score<low:return score/max(low,.001)*.25
    if score<high:return .25+(score-low)/max(high-low,.001)*.35
    return min(1,.6+(score-high)/max(1-high,.001)*.4)


def predict_samples(database,segment_id,samples,config,issue=None):
    from xgboost import XGBClassifier
    active=require_active(database)
    if segment_id not in active['segment_ids']:raise ValueError('Tuyến chưa có lịch sử minh họa để chạy thử dự báo.')
    folder=model_folder(active)
    if not (folder/'metadata.json').is_file():raise ValueError('Cần chuẩn bị mô hình dự báo camera trước.')
    if active['run_id'] not in _models:
        metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        models={}
        for horizon in HORIZONS:
            model=XGBClassifier(n_jobs=1);model.load_model(folder/f'xgb-{horizon}.json');models[horizon]=model
        if len(_models)>=2:_models.pop(next(iter(_models)))
        _models[active['run_id']]=(metadata,models)
    metadata,models=_models[active['run_id']]
    issue=(issue or now()).astimezone(LOCAL)
    issue=issue.replace(minute=issue.minute//5*5,second=0,microsecond=0)
    rows=[density_row(row) for row in rows_for(database,active,segment_id,issue-timedelta(hours=2),issue)][-12:]
    if len(rows)!=12 or any(rows[i]['at']-rows[i-1]['at']!=STEP for i in range(1,12)):
        raise ValueError('Chưa đủ lịch sử minh họa cho thời điểm chạy thử.')
    inputs=[]
    for sample in samples:
        last=dict(rows[-1],score=normalized_score(sample['score'],config['low_threshold'],config['high_threshold']),count=sample['count'])
        context=rows[:-1]+[density_row(last)]
        inputs.append(features(context,active['segment_ids'],segment_id).reshape(-1))
    raw=np.asarray(inputs,dtype=np.float32)
    output=[{'second':sample['second'],'predictions':[]} for sample in samples]
    for horizon in HORIZONS:
        info=metadata['horizons'][str(horizon)]
        x=((raw-np.asarray(info['mean']))/np.asarray(info['std'])).astype(np.float32)
        labels=models[horizon].predict(x)
        for row,label in zip(output,labels):
            row['predictions'].append({'horizon_minutes':horizon,'label':CLASSES['density'][int(label)]})
    return {'is_demo':True,'target':'density','model':'XGBoost','run_id':active['run_id'],
        'reference_at':issue.isoformat(),'context_minutes':60,'synthetic_context_slots':11,
        'message':'Kết hợp mật độ trong video với lịch sử minh họa của tuyến đường.','timeline':output}
