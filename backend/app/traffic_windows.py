"""Validated five-minute, per-direction traffic observations for supervised ML."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .db import now, stamp
from .traffic_metrics import quantities

STEP=timedelta(minutes=5)


class WindowInput(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    segment_id:int=Field(gt=0)
    direction:Literal['forward','reverse']='forward'
    window_end:datetime
    present_count:float=Field(ge=0,le=10000)
    crossing_count:int|None=Field(default=None,ge=0,le=10000)
    avg_speed_kmh:float|None=Field(default=None,ge=0,le=160)
    free_flow_speed_kmh:float=Field(gt=0,le=160)
    observed_length_m:float=Field(ge=5,le=5000)
    lanes:int=Field(ge=1,le=12)
    coverage_seconds:float=Field(gt=0,le=300)
    speed_calibrated:bool=False
    length_verified:bool=False
    verified_state:Literal['FREE','SLOW','JAM']|None=None
    verification_note:str=Field(default='',max_length=500)
    source:str=Field(min_length=3,max_length=160)
    training_allowed:bool=False
    rain_mm:float|None=Field(default=None,ge=0,le=300)
    visibility_km:float|None=Field(default=None,ge=0,le=100)
    accident:bool|None=None
    roadwork:bool|None=None
    obstruction:bool|None=None
    flood:bool|None=None
    @model_validator(mode='after')
    def valid(self):
        if not self.window_end.tzinfo:raise ValueError('Thời gian cần múi giờ.')
        self.window_end=self.window_end.astimezone(timezone.utc)
        if self.window_end>now() or self.window_end.minute%5 or self.window_end.second or self.window_end.microsecond:
            raise ValueError('Dùng mốc kết thúc ô 5 phút đã xảy ra, ví dụ 17:05:00+07:00.')
        if self.speed_calibrated and self.avg_speed_kmh is None:raise ValueError('Thiếu tốc độ đã đo.')
        if self.verified_state and len(self.verification_note.strip())<10:
            raise ValueError('Nhãn thực tế cần căn cứ xác minh ít nhất 10 ký tự, độc lập với kết quả dự báo.')
        return self

    def document(self,user_id):
        metrics=quantities(present_count=self.present_count,length_m=self.observed_length_m,lanes=self.lanes,
            crossings=self.crossing_count,observed_seconds=self.coverage_seconds,speed_kmh=self.avg_speed_kmh,
            free_flow_speed_kmh=self.free_flow_speed_kmh,length_verified=self.length_verified,speed_verified=self.speed_calibrated)
        data=self.model_dump(mode='json');data['window_end']=self.window_end.isoformat()
        return {**data,'metrics':metrics,'reviewer_id':user_id,'updated_at':stamp(),'is_demo':False,
            'usable':self.coverage_seconds>=240 and self.speed_calibrated and self.length_verified and self.training_allowed}


def key(row):
    return f"{row['segment_id']}:{row['direction']}:{row['window_end']}"


def save_windows(database,documents):
    # One authoritative aggregate per road/direction/time. Replacement is explicit
    # and audited by the caller; frames and multiple cameras cannot inflate it.
    for row in documents:
        database.traffic_windows.replace_one({'_id':key(row)},{'_id':key(row),**row},upsert=True)


def load(database,segment_ids,start,end,direction='forward'):
    query={'segment_id':{'$in':segment_ids},'direction':direction,'is_demo':False,
           'window_end':{'$gte':start.astimezone(timezone.utc).isoformat(),'$lte':min(end,now()).astimezone(timezone.utc).isoformat()}}
    return list(database.traffic_windows.find(query).sort('window_end',1).limit(100001))


def reconcile(database):
    """Score issued predictions only when an independent reviewed label arrives."""
    count=0
    for prediction in database.traffic_forecast_outcomes.find({'evaluated':False,'predicted_at':{'$lte':stamp()}}).limit(200):
        actual=database.traffic_windows.find_one({'_id':f"{prediction['segment_id']}:{prediction['direction']}:{prediction['predicted_at']}",
            'is_demo':False,'usable':True,'verified_state':{'$in':['FREE','SLOW','JAM']}})
        if not actual:continue
        data={'evaluated':True,'actual_state':actual['verified_state'],'correct':prediction['label']==actual['verified_state'],
              'actual_speed_kmh':actual['metrics']['avg_speed_kmh'],'evaluated_at':stamp()}
        if prediction.get('predicted_speed_kmh') is not None:
            data['speed_absolute_error']=abs(prediction['predicted_speed_kmh']-actual['metrics']['avg_speed_kmh'])
        database.traffic_forecast_outcomes.update_one({'_id':prediction['_id'],'evaluated':False},{'$set':data});count+=1
    return count
