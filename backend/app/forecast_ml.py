"""Real CPU XGBoost/GRU training, chronological evaluation and private artifacts."""
import json
import hashlib
import logging
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from .config import DATA
from .db import get_database, now, stamp
from .forecast_data import prepare, features, load_series, CLASSES, HORIZONS, LOOKBACK, STEP, DataNotReady

ARTIFACTS=DATA/'forecasts'
executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='smarteye-forecast')
_cache={}
_lock=threading.Lock()
logger=logging.getLogger('smarteye.forecast')


def artifact_folder(run_id):
    return ARTIFACTS/str(uuid.UUID(run_id))


def gru_network(input_size):
    import torch
    from torch import nn
    class TrafficGRU(nn.Module):
        def __init__(self):
            super().__init__()
            self.recurrent=nn.GRU(input_size,32,batch_first=True)
            self.output=nn.Linear(32,3)
        def forward(self,x):
            sequence,_=self.recurrent(x)
            return self.output(sequence[:,-1])
    return TrafficGRU()


def metrics(y,pred):
    from sklearn.metrics import accuracy_score, f1_score, recall_score, confusion_matrix
    return {'samples':len(y),'macro_f1':round(float(f1_score(y,pred,labels=[0,1,2],average='macro',zero_division=0)),4),
        'accuracy':round(float(accuracy_score(y,pred)),4),
        'high_recall':round(float(recall_score(y,pred,labels=[2],average='macro',zero_division=0)),4),
        'class_counts':[int(np.sum(y==i)) for i in range(3)],
        'confusion_matrix':confusion_matrix(y,pred,labels=[0,1,2]).tolist()}


def train_pair(data,folder,horizon,epochs,check=lambda message:None):
    import torch
    from xgboost import XGBClassifier
    torch.set_num_threads(1)
    torch.manual_seed(42)
    np.random.seed(42)
    train,validation,test=data['indices']
    mean=data['x'][train].mean(axis=(0,1));std=data['x'][train].std(axis=(0,1))
    std=np.maximum(std,.001)
    x=((data['x']-mean)/std).astype(np.float32);y=data['y']
    class_weights=len(train)/(3*np.maximum(np.bincount(y[train],minlength=3),1))
    tree=XGBClassifier(n_estimators=180,max_depth=4,learning_rate=.05,subsample=.9,
        colsample_bytree=.9,objective='multi:softprob',num_class=3,eval_metric='mlogloss',
        early_stopping_rounds=12,tree_method='hist',n_jobs=1,random_state=42)
    check(f'Đang huấn luyện XGBoost cho mốc {horizon} phút')
    tree.fit(x[train].reshape(len(train),-1),y[train],sample_weight=class_weights[y[train]],
        eval_set=[(x[validation].reshape(len(validation),-1),y[validation])],verbose=False)
    tree.save_model(folder/f'xgb-{horizon}.json')
    model=gru_network(x.shape[2]);optimizer=torch.optim.Adam(model.parameters(),lr=.002)
    criterion=torch.nn.CrossEntropyLoss(weight=torch.tensor(class_weights,dtype=torch.float32))
    tx=torch.from_numpy(x);ty=torch.from_numpy(y)
    generator=np.random.default_rng(42)
    best=float('inf');best_state=None;stale=0;completed_epochs=0
    for epoch in range(epochs):
        check(f'GRU {horizon} phút · epoch {epoch+1}/{epochs}')
        model.train()
        for batch in np.array_split(generator.permutation(train),max(1,int(np.ceil(len(train)/64)))):
            optimizer.zero_grad();loss=criterion(model(tx[batch]),ty[batch]);loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        model.eval()
        with torch.no_grad(): value=float(criterion(model(tx[validation]),ty[validation]))
        completed_epochs=epoch+1
        if value<best-1e-5:
            best=value;best_state={k:v.detach().clone() for k,v in model.state_dict().items()};stale=0
        else:
            stale+=1
            if stale>=5: break
    model.load_state_dict(best_state);model.eval()
    torch.save(best_state,folder/f'gru-{horizon}.pt')
    results={}
    predictions={}
    for split,indices in [('validation',validation),('test',test)]:
        with torch.no_grad(): gp=model(tx[indices]).argmax(1).numpy()
        xp=tree.predict(x[indices].reshape(len(indices),-1)).astype(int)
        predictions[split]={'XGBoost':xp,'GRU':gp,'Persistence':data['baseline'][indices]}
        results[split]={name:metrics(y[indices],pred) for name,pred in predictions[split].items()}
    # Choose on validation only. The held-out test never selects the winner.
    selected=max(('XGBoost','GRU'),key=lambda name:results['validation'][name]['macro_f1'])
    val=results['validation'];test_result=results['test'];candidate=test_result[selected]
    eligible=(val[selected]['macro_f1']>=val['Persistence']['macro_f1']+.01
        and candidate['macro_f1']>=max(.45,test_result['Persistence']['macro_f1'])
        and candidate['high_recall']>=.5 and min(candidate['class_counts'])>=5)
    per_road={};supported=[]
    for sid in np.unique(data['roads'][test]):
        mask=data['roads'][test]==sid
        per_road[str(sid)]={name:metrics(y[test][mask],pred[mask]) for name,pred in predictions['test'].items()}
        local=per_road[str(sid)]
        vm=data['roads'][validation]==sid
        if (eligible and np.sum(data['roads'][train]==sid)>=25 and np.sum(vm)>=25
            and min(local[selected]['class_counts'])>=5
            and local[selected]['macro_f1']>=max(.45,local['Persistence']['macro_f1'])
            and local[selected]['high_recall']>=.5
            and metrics(y[validation][vm],predictions['validation'][selected][vm])['macro_f1']>=
                metrics(y[validation][vm],data['baseline'][validation][vm])['macro_f1']+.01):
            supported.append(int(sid))
    return {'selected':selected,'deployable':bool(eligible and supported),'supported_segment_ids':supported,'validation':val,'test':test_result,
        'per_road_test':per_road,'gru_epochs':completed_epochs,
        'split':{name:{'samples':len(idx),'first_issue':datetime.fromtimestamp(float(data['times'][idx[0]]),timezone.utc).isoformat(),
            'last_label':datetime.fromtimestamp(float(data['times'][idx[-1]]+horizon*60),timezone.utc).isoformat()}
            for name,idx in zip(('train','validation','test'),(train,validation,test))},
        'scaler':{'mean':mean.tolist(),'std':std.tolist()},'features':int(x.shape[2])}


def train_run(run_id,database=None):
    database=database if database is not None else get_database()
    run=database.forecast_runs.find_one({'_id':run_id})
    if not run or run['status']!='queued': return
    database.forecast_runs.update_one({'_id':run_id,'status':'queued'},{'$set':{'status':'training','progress':5}})
    def check(message):
        if not database.forecast_runs.find_one({'_id':run_id,'running':True}):
            raise InterruptedError('Huấn luyện đã hủy.')
        database.forecast_runs.update_one({'_id':run_id,'running':True},{'$set':{'message':message}})
    try:
        start=datetime.fromisoformat(run['start_at']);end=datetime.fromisoformat(run['end_at'])
        readiness,datasets=prepare(database,run['segment_ids'],start,end,run['target'])
        if not readiness['ready']:
            raise DataNotReady('Chưa đủ dữ liệu: '+'; '.join(h['reason'] for h in readiness['horizons'].values() if h['reason']))
        if shutil.disk_usage(DATA).free<256*1024*1024:
            raise DataNotReady('Ổ lưu dữ liệu cần ít nhất 256 MB trống để lưu bộ dữ liệu và mô hình.')
        folder=artifact_folder(run_id);folder.mkdir(parents=True,exist_ok=True)
        report={'target':run['target'],'classes':CLASSES[run['target']],'segment_ids':run['segment_ids'],
            'readiness':readiness,'seed':42,'lookback_slots':LOOKBACK,'slot_minutes':5,
            'trained_until':run['end_at'],'horizons':{},
            'quality_policy':'Chọn bằng validation; F1 validation hơn Persistence >=0.01; test F1 >=0.45 và >=baseline, recall lớp cao >=0.5, mỗi lớp test >=5 mẫu.'}
        for i,horizon in enumerate(HORIZONS):
            data=datasets[horizon]
            if len(data['y'])>40_000: raise DataNotReady('Tối đa 40.000 cửa sổ mỗi mốc. Hãy rút ngắn khoảng huấn luyện.')
            check(f'Chuẩn bị mốc {horizon} phút')
            np.savez_compressed(folder/f'dataset-{horizon}.npz',**{k:v for k,v in data.items() if k!='indices'})
            report['horizons'][str(horizon)]=train_pair(data,folder,horizon,run['epochs'],check)
            report['horizons'][str(horizon)]['dataset_sha256']=hashlib.sha256((folder/f'dataset-{horizon}.npz').read_bytes()).hexdigest()
            database.forecast_runs.update_one({'_id':run_id,'running':True},{'$set':{'progress':45+i*40}})
        check('Đang lưu báo cáo đánh giá')
        pending=folder/'metadata.pending';pending.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        pending.replace(folder/'metadata.json')
        database.forecast_runs.update_one({'_id':run_id,'running':True},{'$set':{
            'status':'completed','running':False,'progress':100,'message':'Đã huấn luyện và đánh giá XGBoost / GRU.',
            'report':report,'finished_at':stamp()}})
    except InterruptedError:
        pass
    except Exception as exc:
        logger.exception('Forecast training failed')
        message=str(exc) if isinstance(exc,DataNotReady) else 'Huấn luyện thất bại. Kiểm tra thư viện XGBoost/PyTorch, bộ nhớ và log backend.'
        database.forecast_runs.update_one({'_id':run_id,'running':True},{'$set':{
            'status':'failed','running':False,'message':message,'finished_at':stamp()}})


def forecast(database,segment_id,target='density'):
    empty=lambda state,message:{'state':state,'message':message,'segment_id':segment_id,'target':target,'predictions':[]}
    registry=database.forecast_registry.find_one({'_id':target})
    if not registry: return empty('no_model','Chưa có mô hình được Admin kích hoạt.')
    run=database.forecast_runs.find_one({'_id':registry['run_id'],'status':'completed'})
    if not run or segment_id not in run['segment_ids']: return empty('unsupported','Mô hình chưa được huấn luyện cho tuyến này.')
    if not any(info.get('deployable') and segment_id in info.get('supported_segment_ids',[]) for info in run.get('report',{}).get('horizons',{}).values()):
        return empty('unsupported','Mô hình chưa đạt điều kiện đánh giá cho tuyến này.')
    if now()-datetime.fromisoformat(run['end_at'])>timedelta(days=45):
        return empty('model_stale','Mô hình đã quá 45 ngày. Cần đánh giá và huấn luyện lại.')
    folder=artifact_folder(run['_id'])
    if not (folder/'metadata.json').is_file(): return empty('unavailable','Không tìm thấy tệp mô hình. Liên hệ Admin.')
    series,_,_,_=load_series(database,[segment_id],now()-timedelta(hours=3),now())
    samples=series.get(segment_id,{})
    if not samples: return empty('no_data','Chưa có các ô quan sát hoàn chỉnh cho tuyến này.')
    issue=max(samples)
    if now()-issue>timedelta(minutes=10): return empty('stale','Quan sát mới nhất quá cũ để dự báo ngắn hạn.')
    rows=[samples.get(issue-STEP*i) for i in reversed(range(LOOKBACK))]
    if any(row is None for row in rows): return empty('insufficient','Cần 60 phút quan sát liên tiếp; mỗi ô 5 phút có mẫu ở ít nhất 3 phút.')
    with _lock:
        report=run['report'];predictions=[]
        x=features(rows,run['segment_ids'],segment_id)
        for horizon in HORIZONS:
            info=report['horizons'][str(horizon)]
            if not info['deployable'] or segment_id not in info.get('supported_segment_ids',[]): continue
            key=(str(folder),horizon,info['selected'])
            if key not in _cache:
                if len(_cache)>=8: _cache.clear()
                if info['selected']=='XGBoost':
                    from xgboost import XGBClassifier
                    model=XGBClassifier(n_jobs=1);model.load_model(folder/f'xgb-{horizon}.json')
                else:
                    import torch
                    model=gru_network(info['features'])
                    model.load_state_dict(torch.load(folder/f'gru-{horizon}.pt',map_location='cpu',weights_only=True));model.eval()
                _cache[key]=model
            model=_cache[key]
            normalized=((x-np.asarray(info['scaler']['mean']))/np.asarray(info['scaler']['std'])).astype(np.float32)
            if info['selected']=='XGBoost':
                label=int(model.predict(normalized.reshape(1,-1))[0])
            else:
                import torch
                with torch.no_grad(): label=int(model(torch.from_numpy(normalized[None])).argmax(1))
            predictions.append({'horizon_minutes':horizon,'predicted_at':(issue+timedelta(minutes=horizon)).isoformat(),
                'label':CLASSES[target][label],'model':info['selected'],'test_macro_f1':info['test'][info['selected']]['macro_f1']})
    return {'state':'ready' if predictions else 'no_model','message':'Dự báo tham khảo; chưa đo xác suất ùn tắc.',
        'segment_id':segment_id,'target':target,'issue_at':issue.isoformat(),'generated_at':stamp(),
        'run_id':run['_id'],'predictions':predictions}
