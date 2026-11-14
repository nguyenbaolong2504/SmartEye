from datetime import datetime
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .business_common import Input, Revision, Direction, utc


class IncidentInput(Input):
    segment_id: int = Field(ge=1)
    direction: Direction = 'forward'
    kind: Literal['congestion','accident','obstruction','roadwork','flood','other']
    position: list[float] = Field(min_length=2,max_length=2)
    occurred_at: datetime
    content: str = Field(min_length=10,max_length=2000)
    submission_key: str = Field(min_length=8,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('occurred_at')
    @classmethod
    def time_valid(cls,value):
        from .db import now
        value=utc(value)
        if value>now():raise ValueError('Thời điểm xảy ra không được ở tương lai')
        return value


class IncidentEdit(Revision):
    kind: Literal['congestion','accident','obstruction','roadwork','flood','other']
    position: list[float] = Field(min_length=2,max_length=2)
    occurred_at: datetime
    content: str = Field(min_length=10,max_length=2000)
    _time = field_validator('occurred_at')(IncidentInput.time_valid.__func__)


class WarningInput(Input):
    segment_id: int = Field(ge=1)
    direction: Direction = 'forward'
    kind: Literal['congestion','accident','obstruction','roadwork','flood','other']
    position: list[float] = Field(min_length=2,max_length=2)
    severity: Literal['low','medium','high'] = 'medium'
    content: str = Field(min_length=10,max_length=2000)
    start_at: datetime
    end_at: datetime | None = None
    incident_id: int | None = None
    duplicate_reason: str = Field(default='',max_length=1000)
    @field_validator('start_at','end_at')
    @classmethod
    def time_valid(cls,value):return utc(value) if value else None
    @model_validator(mode='after')
    def coherent(self):
        if self.end_at and self.end_at<=self.start_at:raise ValueError('Thời gian kết thúc phải sau thời gian bắt đầu')
        return self


class WarningEdit(WarningInput):
    revision: int = Field(ge=1)


class RuleInput(Input):
    name: str = Field(min_length=3,max_length=120)
    segment_id: int = Field(ge=1)
    direction: Direction = 'forward'
    metric: Literal['score','speed_kmh','flow_per_minute']
    operator: Literal['gt','gte','lt','lte']
    threshold: float = Field(ge=0)
    unit: str
    window_minutes: int = Field(ge=1,le=60)
    start_hour: int = Field(default=0,ge=0,le=23)
    end_hour: int = Field(default=24,ge=1,le=24)
    severity: Literal['low','medium','high'] = 'medium'
    @model_validator(mode='after')
    def coherent(self):
        units={'score':'ratio','speed_kmh':'km/h','flow_per_minute':'vehicles/min'}
        limits={'score':1,'speed_kmh':200,'flow_per_minute':10000}
        if self.unit!=units[self.metric] or self.threshold>limits[self.metric]:raise ValueError('Ngưỡng hoặc đơn vị không phù hợp chỉ số')
        if self.start_hour>=self.end_hour:raise ValueError('Khung giờ bắt đầu phải trước giờ kết thúc')
        return self


class RuleEdit(RuleInput):
    revision: int = Field(ge=1)


class Toggle(Revision):
    active: bool
    confirmed: bool
    @model_validator(mode='after')
    def coherent(self):
        if not self.confirmed:raise ValueError('Cần xác nhận thay đổi')
        return self


class TrafficSourceProfile(Input):
    observed_length_m:float=Field(ge=5,le=5000)
    lanes:int=Field(ge=1,le=12)
    free_flow_speed_kmh:float=Field(gt=0,le=160)
    length_verified:bool=False
    training_allowed:bool=False
    interval_averages:bool=False


class SourceInput(Input):
    name: str = Field(min_length=3,max_length=120)
    kind: Literal['file','api','camera']
    segment_id: int = Field(ge=1)
    direction: Direction = 'forward'
    format: Literal['json','csv','image','video'] = 'csv'
    url: str = Field(default='',max_length=1000)
    credential_env: str = Field(default='',max_length=80,pattern=r'^(TRAFFIC_SOURCE_[A-Z0-9_]+)?$')
    interval_seconds: int = Field(default=60,ge=5,le=3600)
    stale_minutes: int = Field(default=15,ge=1,le=1440)
    authorized: bool = False
    public_preview: bool = False
    location_name: str = Field(default='',max_length=160)
    position: list[float] | None = Field(default=None,min_length=2,max_length=2)
    speed_verified: bool = False
    state_verified: bool = False
    count_method: Literal['occupancy','crossings'] = 'occupancy'
    traffic_profile:TrafficSourceProfile|None=None
    @field_validator('position')
    @classmethod
    def camera_position(cls,value):
        if value is not None and not (-90<=value[0]<=90 and -180<=value[1]<=180):
            raise ValueError('Tọa độ camera chưa hợp lệ')
        return value
    @model_validator(mode='after')
    def coherent(self):
        if not self.authorized:raise ValueError('Cần xác nhận quyền sử dụng nguồn dữ liệu')
        if self.kind=='camera' and self.format not in ('image','video'):raise ValueError('Camera cần định dạng ảnh hoặc video')
        if self.kind!='camera' and self.format not in ('json','csv'):raise ValueError('Nguồn số liệu cần JSON hoặc CSV')
        if self.kind!='file' and not self.url:raise ValueError('Cần địa chỉ kết nối của nguồn')
        if self.kind=='file' and self.url:raise ValueError('Nguồn tệp được nhập trực tiếp, không dùng địa chỉ kết nối')
        if self.public_preview and self.kind!='camera':raise ValueError('Chỉ chia sẻ hình ảnh từ nguồn camera')
        if self.public_preview and self.format=='video' and self.credential_env:
            raise ValueError('Video chia sẻ cần địa chỉ phát công khai không chứa mã truy cập')
        return self


class SourceEdit(SourceInput):
    revision: int = Field(ge=1)


class MappingInput(Revision):
    mapping: dict[str,str]
    units: dict[str,str] = Field(default_factory=dict)
    sample: dict | None = None
    confirmed: bool = False
    @field_validator('mapping')
    @classmethod
    def mapping_valid(cls,value):
        supported={'observed_at','segment_id','direction','count','speed_kmh','score','density','state','interval_seconds',
                   'present_count','crossing_count','rain_mm','visibility_km'}
        if not {'observed_at','segment_id','direction'}<=set(value) or set(value)-supported:raise ValueError('Ánh xạ cần thời gian, tuyến, chiều và chỉ số được hỗ trợ')
        if len(set(value.values()))!=len(value) or any(not v or len(v)>80 for v in value.values()):raise ValueError('Mỗi trường nguồn chỉ được ánh xạ một lần')
        return value
