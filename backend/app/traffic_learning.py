"""Shared physical features and evaluated XGBoost classification/regression.

Only past windows form inputs. CI is derived from independently regressed speed;
classification probabilities are calibrated on a separate chronological partition.
"""
import numpy as np
from .history import LOCAL
from .traffic_metrics import number

STATES=('FREE','SLOW','JAM')
FIELDS=('speed_ratio','speed_known','flow_per_lane','flow_known','density_per_lane','density_known',
        'ci','ci_known','load','stopped_share','motion_known','rain_mm','rain_known',
        'visibility_km','visibility_known','accident','roadwork','obstruction','flood','events_known')


def physical_features(row):
    m=row.get('traffic_metrics') or row.get('metrics') or {}
    speed=number(m.get('avg_speed_kmh'));free=number(m.get('free_flow_speed_kmh'),.001)
    flow=number(m.get('flow_veh_per_hour_per_lane'));density=number(m.get('density_veh_per_km_per_lane'))
    ci=number(m.get('congestion_index'),0,1)
    rain=number(row.get('rain_mm'));visibility=number(row.get('visibility_km'))
    event_keys=('accident','roadwork','obstruction','flood')
    return [min(2.,speed/free) if speed is not None and free else 0.,float(speed is not None and bool(free)),
        np.log1p(flow) if flow is not None else 0.,float(flow is not None),
        np.log1p(density) if density is not None else 0.,float(density is not None),
        ci or 0.,float(ci is not None),min(3.,max(0.,row.get('load_ratio',row.get('score',0)))),
        float(row.get('stopped_share') or 0),float(row.get('motion_known',False)),
        rain or 0.,float(rain is not None),visibility or 0.,float(visibility is not None),
        *[float(bool(row.get(key))) for key in event_keys],float(all(row.get(key) is not None for key in event_keys))]


def sequence_features(rows,vocabulary,sid):
    import math
    values=[v for row in rows for v in physical_features(row)]
    at=rows[-1]['at'].astimezone(LOCAL)
    h=(at.hour+at.minute/60)*math.tau/24;w=at.weekday()*math.tau/7
    return np.asarray([*values,math.sin(h),math.cos(h),math.sin(w),math.cos(w),
        *[float(road==sid) for road in vocabulary]],dtype=np.float32)


def partition(data,horizon):
    from .forecast_data import split_indices,DataNotReady
    train,validation,test=split_indices(data,horizon)
    times=np.unique(data['times'][validation]);mid=times[len(times)//2]
    early=validation[data['times'][validation]+horizon*60<mid]
    calibration=validation[data['times'][validation]>=mid]
    if min(len(early),len(calibration))<25:raise DataNotReady('Cần ít nhất 25 cửa sổ riêng cho chọn mô hình và hiệu chỉnh xác suất.')
    return train,early,calibration,test


def fit_models(data,folder,horizon,estimators=180):
    from xgboost import XGBClassifier,XGBRegressor
    from .forecast_ml import metrics
    from .camera_forecast import fit_temperature,probabilities,negative_log_loss,calibration_error
    train,early,calibration,test=partition(data,horizon)
    x=data['x'];y=data['y'];speed=data['speed_ratio']
    model=XGBClassifier(n_estimators=estimators,max_depth=5,learning_rate=.06,subsample=.9,colsample_bytree=.9,
        objective='multi:softprob',num_class=3,tree_method='hist',n_jobs=1,random_state=42,
        eval_metric='mlogloss',early_stopping_rounds=12)
    model.fit(x[train],y[train],eval_set=[(x[early],y[early])],verbose=False)
    temperature=fit_temperature(y[calibration],model.predict_proba(x[calibration]))
    reg=XGBRegressor(n_estimators=estimators,max_depth=5,learning_rate=.06,subsample=.9,colsample_bytree=.9,
        objective='reg:squarederror',tree_method='hist',n_jobs=1,random_state=42,early_stopping_rounds=12)
    reg.fit(x[train],speed[train],eval_set=[(x[early],speed[early])],verbose=False)
    model.save_model(folder/f'traffic-{horizon}.json');reg.save_model(folder/f'speed-{horizon}.json')
    results={};predictions={}
    for name,idx in (('validation',early),('test',test)):
        p=probabilities(model.predict_proba(x[idx]),temperature)
        preds={'XGBoost':p.argmax(1),'Persistence':data['baseline'][idx],'Historical':data['historical'][idx]}
        results[name]={key:metrics(y[idx],value) for key,value in preds.items()};predictions[name]=preds
    p=probabilities(model.predict_proba(x[test]),temperature)
    actual_speed=speed[test]*data['free_speed'][test]
    predicted_speed=np.clip(reg.predict(x[test]),0,2)*data['free_speed'][test]
    candidate=results['test']['XGBoost'];val=results['validation'];test_scores=results['test']
    beats=lambda scores:scores['XGBoost']['macro_f1']>=max(scores['Persistence']['macro_f1'],scores['Historical']['macro_f1'])+.01
    ece=calibration_error(y[test],p)
    brier=float(np.mean(np.sum((p-np.eye(3)[y[test]])**2,axis=1)))
    eligible=beats(val) and beats(test_scores) and candidate['high_recall']>=.5 and min(candidate['class_counts'])>=5 and ece<=.1 and brier<2/3
    supported=[];speed_supported=[]
    for sid in np.unique(data['roads'][test]):
        tm=data['roads'][test]==sid;vm=data['roads'][early]==sid
        if not tm.any() or not vm.any():continue
        local={name:metrics(y[test][tm],pred[tm]) for name,pred in predictions['test'].items()}
        vlocal={name:metrics(y[early][vm],pred[vm]) for name,pred in predictions['validation'].items()}
        if eligible and min(local['XGBoost']['class_counts'])>=5 and beats(local) and beats(vlocal) and local['XGBoost']['high_recall']>=.5:supported.append(int(sid))
        local_speed=float(np.mean(np.abs(predicted_speed[tm]-actual_speed[tm])))
        local_baseline=float(np.mean(np.abs(data['current_speed'][test][tm]-actual_speed[tm])))
        validation_speed=np.clip(reg.predict(x[early][vm]),0,2)*data['free_speed'][early][vm]
        validation_actual=speed[early][vm]*data['free_speed'][early][vm]
        if local_speed<local_baseline and np.mean(np.abs(validation_speed-validation_actual))<np.mean(np.abs(data['current_speed'][early][vm]-validation_actual)):
            speed_supported.append(int(sid))
    return {'selected':'XGBoost','deployable':bool(supported),'supported_segment_ids':supported,
        **results,'temperature':temperature,'features':int(x.shape[1]),
        'test_log_loss':negative_log_loss(y[test],p),'test_calibration_error':ece,
        'test_brier_score':brier,
        'speed_test_mae_kmh':float(np.mean(np.abs(predicted_speed-actual_speed))),
        'speed_persistence_mae_kmh':float(np.mean(np.abs(data['current_speed'][test]-actual_speed))),
        'speed_deployable':bool(speed_supported),'speed_supported_segment_ids':speed_supported,
        'split':{name:{'samples':len(idx),'first_issue':float(data['times'][idx].min()),
            'last_label':float((data['times'][idx]+horizon*60).max())}
            for name,idx in zip(('train','validation','calibration','test'),(train,early,calibration,test))}}
