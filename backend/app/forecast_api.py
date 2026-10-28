"""Forecast preparation, reviewed labels, training and explicit model activation."""
import csv
import hashlib
import importlib.util
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError
from .db import get_db, now, stamp
from .models import Segment, ForecastRun, TrafficLabel, ForecastRegistry
from .security import operator, admin, audit
from .history import parse_timestamp
from .forecast_data import prepare, CLASSES, DataNotReady, STEP
from . import forecast_ml

router=APIRouter()
Target=Literal['density','congestion']


class TrainInput(BaseModel):
    segment_ids:list[int]=Field(min_length=1,max_length=20)
    target:Target='density'
    start_at:datetime
    end_at:datetime
    epochs:int=Field(default=25,ge=5,le=80)
    @model_validator(mode='after')
    def valid(self):
        if not self.start_at.tzinfo or not self.end_at.tzinfo: raise ValueError('Thời gian cần múi giờ.')
        self.start_at=self.start_at.astimezone(timezone.utc);self.end_at=self.end_at.astimezone(timezone.utc)
        if not timedelta(days=7)<=self.end_at-self.start_at<=timedelta(days=90): raise ValueError('Chọn khoảng từ 7 đến 90 ngày.')
        if self.end_at>now()+timedelta(seconds=5): raise ValueError('Không huấn luyện bằng dữ liệu tương lai.')
        self.segment_ids=sorted(set(self.segment_ids))
        return self


class LabelInput(BaseModel):
    segment_id:int
    observed_at:datetime
    state:Literal['FREE','SLOW','JAM']
    note:str=Field(min_length=5,max_length=300)
    @model_validator(mode='after')
    def valid(self):
        if not self.observed_at.tzinfo: raise ValueError('Thời gian cần múi giờ.')
        self.observed_at=self.observed_at.astimezone(timezone.utc)
        if self.observed_at>now() or self.observed_at.minute%5 or self.observed_at.second or self.observed_at.microsecond:
            raise ValueError('Chọn mốc kết thúc ô 5 phút đã xảy ra (ví dụ 07:05).')
        return self


def valid_segments(db,ids):
    for ident in ids:
        road=db.get(Segment,ident)
        if not road or not road.active: raise HTTPException(404,'Đoạn đường không tồn tại hoặc đã ngừng.')


def public_run(run):
    return {key:run[key] for key in ('status','progress','message','target','segment_ids','start_at','end_at','created_at','report','finished_at') if key in run}|{'id':run['_id']}


@router.get('/api/forecast/status')
def status(db=Depends(get_db)):
    active=[]
    for registry in db.database.forecast_registry.find():
        run=db.database.forecast_runs.find_one({'_id':registry['run_id'],'status':'completed'})
        if run: active.append({'target':registry['_id'],'run_id':run['_id'],'segment_ids':sorted({sid for info in run['report'].get('horizons',{}).values() if info.get('deployable') for sid in info.get('supported_segment_ids',[])}),
            'trained_until':run['end_at'],'activated_at':registry['activated_at']})
    return {'active':active,'classes':CLASSES,'slot_minutes':5,'lookback_minutes':60,
        'horizons':[15,30],'notice':'Dự báo mật độ và dự báo ùn tắc là hai mục tiêu riêng.'}


@router.get('/api/forecast/predict')
def predict(segment_id:int,target:Target='density',db=Depends(get_db)):
    valid_segments(db,[segment_id])
    try: return forecast_ml.forecast(db.database,segment_id,target)
    except Exception:
        logging.getLogger('smarteye.forecast').exception('Forecast inference unavailable')
        return {'state':'unavailable','segment_id':segment_id,'target':target,'predictions':[],
            'message':'Mô hình chưa phục vụ được. Liên hệ Admin kiểm tra tệp mô hình và thư viện backend.'}


@router.post('/api/forecast/readiness')
def readiness(body:TrainInput,user=Depends(operator),db=Depends(get_db)):
    valid_segments(db,body.segment_ids)
    try: result,_=prepare(db.database,body.segment_ids,body.start_at,body.end_at,body.target)
    except DataNotReady as exc: raise HTTPException(422,str(exc))
    result['dependencies']={name:importlib.util.find_spec(name) is not None for name in ('xgboost','sklearn','torch')}
    return result


@router.get('/api/forecast/runs')
def runs(user=Depends(operator),db=Depends(get_db)):
    return [public_run(row) for row in db.database.forecast_runs.find().sort('created_at',-1).limit(20)]


@router.post('/api/forecast/runs',status_code=202)
def start_training(body:TrainInput,user=Depends(operator),db=Depends(get_db)):
    valid_segments(db,body.segment_ids)
    if any(importlib.util.find_spec(name) is None for name in ('xgboost','sklearn','torch')):
        raise HTTPException(503,'Thiếu thư viện dự báo. Cài backend/requirements.txt và PyTorch CPU hoặc build lại backend Docker.')
    row=ForecastRun(id=str(uuid.uuid4()),user_id=user.id,target=body.target,segment_ids=body.segment_ids,
        start_at=body.start_at.isoformat(),end_at=body.end_at.isoformat(),epochs=body.epochs)
    if db.database.forecast_runs.find_one({'running':True}): raise HTTPException(409,'Đang có tác vụ huấn luyện. Chờ hoàn tất hoặc hủy tác vụ trước.')
    db.add(row);audit(db,user.id,'forecast_training_started',row.id);db.commit()
    forecast_ml.executor.submit(forecast_ml.train_run,row.id)
    return {'id':row.id,'status':row.status}


@router.post('/api/forecast/runs/{run_id}/cancel')
def cancel(run_id:uuid.UUID,user=Depends(operator),db=Depends(get_db)):
    row=db.database.forecast_runs.find_one({'_id':str(run_id)})
    if not row: raise HTTPException(404,'Không tìm thấy lần huấn luyện.')
    if row['user_id']!=user.id and user.role!='admin': raise HTTPException(403,'Chỉ người tạo hoặc Admin được hủy.')
    changed=db.database.forecast_runs.update_one({'_id':str(run_id),'running':True},{'$set':{
        'running':False,'status':'cancelled','message':'Đã hủy huấn luyện.','finished_at':stamp()}})
    if not changed.modified_count: raise HTTPException(409,'Tác vụ đã kết thúc.')
    audit(db,user.id,'forecast_training_cancelled',str(run_id));db.commit()
    return {'message':'Đã yêu cầu hủy tác vụ.'}


@router.post('/api/forecast/runs/{run_id}/activate')
def activate(run_id:uuid.UUID,user=Depends(admin),db=Depends(get_db)):
    run=db.database.forecast_runs.find_one({'_id':str(run_id),'status':'completed'})
    if not run or not any(h.get('deployable') for h in run.get('report',{}).get('horizons',{}).values()):
        raise HTTPException(409,'Mô hình chưa đạt điều kiện đánh giá để kích hoạt.')
    folder=forecast_ml.artifact_folder(str(run_id))
    required=['metadata.json']
    for horizon,info in run['report']['horizons'].items():
        if info.get('deployable'): required.extend([f'xgb-{horizon}.json',f'gru-{horizon}.pt'])
    if any(not (folder/name).is_file() for name in required): raise HTTPException(409,'Thiếu tệp mô hình trên máy chủ.')
    db.database.forecast_registry.replace_one({'_id':run['target']},{'_id':run['target'],'run_id':str(run_id),
        'activated_by':user.id,'activated_at':stamp()},upsert=True)
    audit(db,user.id,'forecast_model_activated',str(run_id));db.commit()
    return {'message':'Đã kích hoạt các mốc dự báo đạt điều kiện.'}


@router.delete('/api/forecast/active/{target}')
def deactivate(target:Target,user=Depends(admin),db=Depends(get_db)):
    db.database.forecast_registry.delete_one({'_id':target});audit(db,user.id,'forecast_model_deactivated',target);db.commit()
    return {'message':'Đã ngừng phục vụ mô hình. Dữ liệu và báo cáo được giữ lại.'}


@router.get('/api/forecast/runs/{run_id}/report.csv')
def export_report(run_id:uuid.UUID,user=Depends(operator),db=Depends(get_db)):
    run=db.database.forecast_runs.find_one({'_id':str(run_id),'status':'completed'})
    if not run: raise HTTPException(404,'Chưa có báo cáo hoàn tất.')
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['target','horizon_minutes','split','model','samples','macro_f1','accuracy','high_recall','selected','deployable'])
    for horizon,info in run['report']['horizons'].items():
        for split in ('validation','test'):
            for name,values in info[split].items():
                writer.writerow([run['target'],horizon,split,name,values['samples'],values['macro_f1'],values['accuracy'],values['high_recall'],name==info['selected'],info['deployable']])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename=forecast-{run_id}.csv'})


@router.get('/api/forecast/labels')
def labels(segment_id:int,user=Depends(operator),db=Depends(get_db)):
    return [dict(row,id=row['_id']) for row in db.database.traffic_labels.find({'segment_id':segment_id}).sort('observed_at',-1).limit(50)]


@router.post('/api/forecast/labels')
def label(body:LabelInput,user=Depends(operator),db=Depends(get_db)):
    valid_segments(db,[body.segment_id])
    existing=db.find_one(TrafficLabel,{'segment_id':body.segment_id,'observed_at':body.observed_at.isoformat()})
    if existing: db.update(TrafficLabel,existing.id,{'state':body.state,'note':body.note,'reviewer_id':user.id,'updated_at':stamp()})
    else: db.add(TrafficLabel(segment_id=body.segment_id,observed_at=body.observed_at.isoformat(),state=body.state,note=body.note,reviewer_id=user.id))
    audit(db,user.id,'traffic_label_reviewed',f'{body.segment_id}:{body.observed_at.isoformat()}');db.commit()
    return {'message':'Đã lưu nhãn thực tế cho ô 5 phút.'}


@router.post('/api/forecast/import')
async def import_data(file:UploadFile=File(...),dry_run:bool=True,user=Depends(operator),db=Depends(get_db)):
    content=await file.read(2_000_001)
    if len(content)>2_000_000: raise HTTPException(413,'CSV tối đa 2 MB.')
    try:
        rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        if not 1<=len(rows)<=5000: raise ValueError('CSV cần từ 1 đến 5.000 dòng.')
        documents=[];seen=set()
        for index,row in enumerate(rows,2):
            sid=int(row['segment_id']);at=parse_timestamp(row['observed_at'])
            score=float(row['score']);count=int(row['count']);density=row['density'].strip()
            if not 0<=score<=1 or not 0<=count<=10000 or density not in CLASSES['density'] or at>now():
                raise ValueError(f'Dòng {index}: score/count/density/thời điểm không hợp lệ.')
            key=f'import:{sid}:{at.isoformat()}'
            if key in seen: raise ValueError(f'Dòng {index}: trùng tuyến và thời điểm trong CSV.')
            seen.add(key)
            documents.append({'sample_key':key,'segment_id':sid,'observed_at':at.isoformat(),
                'score':score,'count':count,'density':density,'source':'import','camera_id':None,
                'imported_by':user.id,'created_at':stamp()})
        valid_segments(db,sorted({row['segment_id'] for row in documents}))
    except (ValueError,KeyError,TypeError,UnicodeError) as exc:
        raise HTTPException(422,'CSV cần cột segment_id,observed_at,score,count,density; thời gian ISO có múi giờ. '+str(exc)) from None
    duplicates=db.database.traffic_samples.count_documents({'sample_key':{'$in':[r['sample_key'] for r in documents]}})
    if dry_run: return {'rows':len(documents),'duplicates':duplicates,'preview':[{k:r[k] for k in ('segment_id','observed_at','score','count','density')} for r in documents[:5]],'message':'Đã kiểm tra. Chưa ghi dữ liệu.'}
    counter=db.database.counters.find_one_and_update({'_id':'traffic_samples'},{'$inc':{'seq':len(documents)}},upsert=True,return_document=ReturnDocument.AFTER)
    for i,row in enumerate(documents): row['_id']=counter['seq']-len(documents)+i+1
    inserted=len(documents)
    try: db.database.traffic_samples.insert_many(documents,ordered=False)
    except BulkWriteError as exc:
        if exc.details.get('writeConcernErrors') or any(e['code']!=11000 for e in exc.details.get('writeErrors',[])): raise
        inserted=exc.details['nInserted']
    audit(db,user.id,'forecast_data_imported',f'{inserted} samples');db.commit()
    return {'rows':len(documents),'inserted':inserted,'duplicates':len(documents)-inserted,'message':'Đã nhập mẫu lịch sử. CSV không tự tạo nhãn ùn tắc.'}


@router.get('/api/forecast/templates/{kind}.csv')
def template(kind:Literal['observations','labels']):
    header='segment_id,observed_at,score,count,density' if kind=='observations' else 'segment_id,observed_at,state,note'
    return Response(header+'\r\n',media_type='text/csv',headers={'Content-Disposition':f'attachment; filename=traffic-{kind}.csv'})


@router.post('/api/forecast/labels/import')
async def import_labels(file:UploadFile=File(...),dry_run:bool=True,user=Depends(operator),db=Depends(get_db)):
    content=await file.read(2_000_001)
    if len(content)>2_000_000: raise HTTPException(413,'CSV tối đa 2 MB.')
    try:
        rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        if not 1<=len(rows)<=5000: raise ValueError('CSV cần từ 1 đến 5.000 dòng.')
        checked=[];seen=set()
        for row in rows:
            label=LabelInput(segment_id=int(row['segment_id']),observed_at=row['observed_at'],state=row['state'].strip(),note=row['note'])
            key=(label.segment_id,label.observed_at.isoformat())
            if key in seen: raise ValueError('Trùng tuyến và thời điểm trong CSV nhãn.')
            seen.add(key);checked.append({'segment_id':label.segment_id,'observed_at':key[1],'state':label.state,'note':label.note})
        valid_segments(db,sorted({row['segment_id'] for row in checked}))
    except (ValueError,KeyError,TypeError,UnicodeError):
        raise HTTPException(422,'CSV nhãn cần segment_id,observed_at,state,note. Mốc kết thúc ô 5 phút có múi giờ, không ở tương lai; state FREE/SLOW/JAM; căn cứ 5–300 ký tự. Không trùng tuyến/thời điểm.') from None
    existing=db.database.traffic_labels.count_documents({'$or':[{'segment_id':r['segment_id'],'observed_at':r['observed_at']} for r in checked]})
    if dry_run: return {'rows':len(checked),'updates':existing,'preview':checked[:5],'message':'Đã kiểm tra nhãn, chưa ghi dữ liệu. Các mốc đã có sẽ được cập nhật khi xác nhận.'}
    counter=db.database.counters.find_one_and_update({'_id':'traffic_labels'},{'$inc':{'seq':len(checked)}},upsert=True,return_document=ReturnDocument.AFTER)
    for index,row in enumerate(checked):
        db.database.traffic_labels.update_one({'segment_id':row['segment_id'],'observed_at':row['observed_at']},
            {'$set':{'state':row['state'],'note':row['note'],'reviewer_id':user.id,'updated_at':stamp()},
             '$setOnInsert':{'_id':counter['seq']-len(checked)+index+1}},upsert=True)
    audit(db,user.id,'traffic_labels_imported',f'{len(checked)} reviewed labels');db.commit()
    return {'rows':len(checked),'updates':existing,'message':'Đã lưu nhãn thực tế từ CSV. Người nhập chịu trách nhiệm căn cứ đã xác nhận.'}
