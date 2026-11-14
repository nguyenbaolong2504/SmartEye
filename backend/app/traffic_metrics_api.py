"""Measured aggregates join the existing preparation/training/activation APIs."""
import csv
import io
from typing import Literal
from fastapi import APIRouter,Depends,UploadFile,File,HTTPException
from .db import get_db
from .models import Segment
from .security import permit,audit
from .business_common import check_segment_scope
from .traffic_windows import WindowInput,save_windows,load,reconcile

router=APIRouter(prefix='/api/forecast/traffic',tags=['Traffic measurements'])


def validate_roads(db,documents,user):
    ids={row['segment_id'] for row in documents};check_segment_scope(user,*ids)
    for row in documents:
        road=db.get(Segment,row['segment_id'])
        if not road or not road.active:raise HTTPException(422,'Tuyến đường không hoạt động.')
        if road.is_demo:raise HTTPException(422,'Quan trắc thực cần tuyến đường thực; không nhập vào tuyến minh họa.')
        if road.one_way and row['direction']=='reverse':raise HTTPException(422,'Đường một chiều không có chiều về.')


@router.post('/windows',status_code=201)
def create(body:WindowInput,user=Depends(permit('models.manage')),db=Depends(get_db)):
    documents=[body.document(user.id)];validate_roads(db,documents,user)
    save_windows(db.database,documents);reconcile(db.database)
    audit(db,user.id,'traffic_window_reviewed',f'{body.segment_id}:{body.direction}:{body.window_end.isoformat()}');db.commit()
    return documents[0]


@router.post('/import')
async def import_windows(file:UploadFile=File(...),dry_run:bool=True,user=Depends(permit('models.manage')),db=Depends(get_db)):
    raw=await file.read(2_000_001)
    if len(raw)>2_000_000:raise HTTPException(413,'CSV tối đa 2 MB.')
    try:
        rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        if not 1<=len(rows)<=5000:raise ValueError('CSV cần 1–5.000 dòng.')
        docs=[];seen=set()
        for index,row in enumerate(rows,2):
            value=WindowInput.model_validate({key:value.strip() for key,value in row.items() if value is not None and value.strip()!=''})
            document=value.document(user.id)
            ident=(value.segment_id,value.direction,value.window_end)
            if ident in seen:raise ValueError(f'Dòng {index} bị trùng tuyến, chiều và thời điểm.')
            seen.add(ident);docs.append(document)
        validate_roads(db,docs,user)
    except (ValueError,TypeError,KeyError,UnicodeError) as error:
        raise HTTPException(422,'CSV ô 5 phút không hợp lệ. '+str(error)) from None
    from .traffic_windows import key
    updates=db.database.traffic_windows.count_documents({'_id':{'$in':[key(row) for row in docs]}})
    if dry_run:return {'rows':len(docs),'updates':updates,'usable':sum(row['usable'] for row in docs),'preview':docs[:5],
        'message':'Đã kiểm tra; chưa ghi. Các ô đã tồn tại sẽ được thay thế khi xác nhận.'}
    save_windows(db.database,docs);reconcile(db.database)
    audit(db,user.id,'traffic_windows_imported',f'{len(docs)} windows, {updates} replacements');db.commit()
    return {'rows':len(docs),'updates':updates,'usable':sum(row['usable'] for row in docs),'message':'Đã lưu quan trắc 5 phút; dữ liệu thiếu chất lượng không được đưa vào huấn luyện.'}


@router.get('/windows')
def windows(segment_id:int,direction:Literal['forward','reverse']='forward',user=Depends(permit('models.manage')),db=Depends(get_db)):
    check_segment_scope(user,segment_id)
    return list(db.database.traffic_windows.find({'segment_id':segment_id,'direction':direction},{'_id':0}).sort('window_end',-1).limit(50))


@router.get('/outcomes')
def outcomes(segment_id:int,direction:Literal['forward','reverse']='forward',user=Depends(permit('models.manage')),db=Depends(get_db)):
    check_segment_scope(user,segment_id);reconcile(db.database)
    rows=list(db.database.traffic_forecast_outcomes.find({'segment_id':segment_id,'direction':direction},{'_id':0}).sort('issue_at',-1).limit(500))
    scored=[row for row in rows if row.get('evaluated')]
    return {'issued':len(rows),'evaluated':len(scored),'accuracy':sum(row['correct'] for row in scored)/len(scored) if scored else None,
        'message':'Chỉ chấm khi có quan trắc và nhãn độc lập đúng mốc dự báo. Tối đa 500 lượt gần nhất.','rows':rows[:50]}
