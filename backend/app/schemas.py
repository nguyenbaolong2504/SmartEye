import re
import math
from datetime import datetime, timezone
from typing import Literal
from pydantic import AliasChoices,BaseModel,Field,field_validator,model_validator,model_serializer

class Register(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
    username: str = Field(min_length=3,max_length=40,pattern=r'^[A-Za-z0-9_.-]+$')
    password_confirmation: str = Field(min_length=10,max_length=128)
    phone: str | None = None
    @field_validator('username',mode='before')
    @classmethod
    def username_valid(cls,value):
        if not isinstance(value,str):return value
        value=value.strip().lower()
        if not 3<=len(value)<=40:raise ValueError('Tên đăng nhập cần từ 3 đến 40 ký tự')
        if '@' in value:raise ValueError('Tên đăng nhập không dùng địa chỉ email. Ví dụ: smarteye2026. Nhập email vào ô Email')
        if not re.fullmatch(r'[a-z0-9_.-]+',value):
            raise ValueError('Tên đăng nhập chỉ dùng chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang')
        return value
    @field_validator('phone')
    @classmethod
    def phone_valid(cls,value):
        if value in ('',None):return None
        value=re.sub(r'[\s().-]','',value)
        if not re.fullmatch(r'\+?[0-9]{9,15}',value):raise ValueError('Số điện thoại cần 9–15 chữ số, có thể bắt đầu bằng +')
        return value
    @model_validator(mode='after')
    def confirmation_valid(self):
        if self.password!=self.password_confirmation:raise ValueError('Mật khẩu và xác nhận không khớp')
        return self
    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Email không hợp lệ')
        return value
    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('Tên cần ít nhất hai ký tự')
        return value.strip()

class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    @field_validator('email')
    @classmethod
    def identifier_valid(cls,value):
        if not value.strip():raise ValueError('Vui lòng nhập tên đăng nhập hoặc email')
        return value.strip().lower()

class CameraMeasurement(BaseModel):
    model_config = {'extra':'forbid'}
    count_line: list[list[float]] | None = None
    crossing_direction: Literal['both','positive','negative']='both'
    image_points: list[list[float]] | None = None
    ground_points: list[list[float]] | None = None
    free_flow_speed_kmh: float | None = Field(default=None,gt=0,le=160,allow_inf_nan=False)
    verified: bool=False
    note: str=Field(default='',max_length=400)
    @model_validator(mode='after')
    def valid(self):
        import numpy as np
        def points(values,count,normalized):
            if len(values)!=count or any(len(p)!=2 or any(not math.isfinite(v) or abs(v)>1000 or normalized and not 0<=v<=1 for v in p) for p in values):
                raise ValueError('Điểm hiệu chuẩn không hợp lệ; điểm ảnh dùng tọa độ 0–1, điểm mặt đất dùng mét.')
        if self.count_line is not None:
            points(self.count_line,2,True)
            if math.dist(*self.count_line)<.02:raise ValueError('Vạch đếm quá ngắn.')
        if bool(self.image_points)!=bool(self.ground_points):raise ValueError('Cần đủ cả bốn điểm ảnh và bốn điểm mặt đất tương ứng.')
        if self.image_points:
            import cv2
            for values,normalized in ((self.image_points,True),(self.ground_points,False)):
                points(values,4,normalized)
                polygon=np.asarray(values,dtype=np.float32)
                if not cv2.isContourConvex(polygon) or abs(cv2.contourArea(polygon))<(.001 if normalized else 1):
                    raise ValueError('Bốn điểm phải tạo tứ giác lồi, theo thứ tự quanh vùng đường.')
            if not self.verified or len(self.note.strip())<10:
                raise ValueError('Đo tốc độ cần xác nhận hiệu chuẩn và ghi căn cứ đo thực địa (ít nhất 10 ký tự).')
        return self


class RoadProfile(BaseModel):
    lanes: int = Field(default=2,ge=1,le=12)
    road_width_m: float = Field(default=7,ge=2,le=60,allow_inf_nan=False)
    observed_length_m: float = Field(default=70,ge=5,le=500,allow_inf_nan=False)
    usable_fraction: float = Field(default=.85,ge=.1,le=1,allow_inf_nan=False)
    calibration: Literal['estimated','measured']='estimated'
    measurement: CameraMeasurement | None = None
    @model_serializer(mode='wrap')
    def serialized(self,handler):
        value=handler(self)
        if self.measurement is None:value.pop('measurement',None)
        return value
    @model_validator(mode='after')
    def valid(self):
        if self.measurement and self.measurement.verified and self.calibration!='measured':
            raise ValueError('Hiệu chuẩn đã xác nhận cần kích thước vùng đường đã đo.')
        return self


class CameraInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    segment_id: int
    active: bool = True
    capacity: int = Field(default=30, ge=1, le=500)
    low_threshold: float = Field(default=.25, ge=.01, le=.95)
    high_threshold: float = Field(default=.6, ge=.02, le=1)
    roi: list[float] = Field(default=[0, 0, 1, 1], min_length=4, max_length=4)
    road_profile: RoadProfile | None = None
    @model_validator(mode='after')
    def coherent(self):
        if self.low_threshold >= self.high_threshold:
            raise ValueError('Ngưỡng thấp phải nhỏ hơn ngưỡng cao')
        x1, y1, x2, y2 = self.roi
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1) or (x2-x1)*(y2-y1) < .01:
            raise ValueError('ROI phải nằm trong ảnh và chiếm ít nhất 1% khung hình')
        return self


class PublishOptions(BaseModel):
    share_preview: bool = False


class ObservationInput(BaseModel):
    segment_id: int
    score: float = Field(ge=0, le=1)
    count: int = Field(default=0, ge=0, le=10000)
    note: str = Field(min_length=5, max_length=300)
    observed_at: datetime
    @field_validator('observed_at')
    @classmethod
    def timestamp_valid(cls, value):
        if not value.tzinfo:
            raise ValueError('Cần múi giờ trong thời gian quan sát')
        return value.astimezone(timezone.utc)

class Waypoint(BaseModel):
    lat: float = Field(ge=20.5, le=21.5)
    lng: float = Field(ge=105.2, le=106.2)
    name: str = Field(default='', max_length=240)
    node: str | None = Field(default=None, max_length=80)

class RouteRequest(BaseModel):
    origin: Waypoint
    destination: Waypoint
    mode: Literal['DRIVE', 'TWO_WHEELER'] = 'DRIVE'
    provider: Literal['demo', 'google', 'osm', 'auto'] = 'demo'
    algorithm: Literal['compare','dijkstra','astar'] = 'astar'
    traffic_mode: Literal['observed','demo'] = 'observed'
    departure_at: datetime | None = None
    weights: dict[str, float] = Field(default={'time': .6, 'distance': .4, 'density': 0.})
    @model_validator(mode='after')
    def coherent(self):
        if abs(self.origin.lat - self.destination.lat) + abs(self.origin.lng - self.destination.lng) < .00005:
            raise ValueError('Điểm đi và điểm đến phải khác nhau')
        if set(self.weights) not in ({'time','distance'},{'time','distance','density'}) or any(not math.isfinite(v) or not 0 <= v <= 1 for v in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError('Trọng số phải nằm trong 0–1 và tổng lớn hơn 0')
        self.weights.setdefault('density',0.)
        if self.departure_at:
            if not self.departure_at.tzinfo:
                raise ValueError('Giờ khởi hành cần múi giờ')
            self.departure_at = self.departure_at.astimezone(timezone.utc)
            delta = (self.departure_at - datetime.now(timezone.utc)).total_seconds()
            if delta < -60 or delta > 7*86400:
                raise ValueError('Giờ khởi hành phải nằm trong 7 ngày tới')
        return self

class FavoriteInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    request: RouteRequest

class RuleInput(BaseModel):
    segment_id: int
    density: Literal['LOW', 'NORMAL', 'HIGH'] = 'HIGH'
    active: bool = True

class UserUpdate(BaseModel):
    role: Literal['user', 'analyst', 'admin']
    active: bool

class SegmentInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    start_node: str = Field(min_length=2, max_length=80, pattern=r'^[a-z0-9_]+$')
    end_node: str = Field(min_length=2, max_length=80, pattern=r'^[a-z0-9_]+$')
    distance_km: float = Field(ge=.05, le=100)
    geometry: list[list[float]] = Field(min_length=2, max_length=1000)
    active: bool = True
    is_demo: bool = False
    one_way: bool = False
    area: str = Field(default='Hà Nội',min_length=2,max_length=100)
    @model_validator(mode='after')
    def coherent(self):
        if self.start_node == self.end_node:
            raise ValueError('Mã hai đầu đoạn đường phải khác nhau')
        if any(len(p)!=2 or not (8<=p[0]<=24 and 102<=p[1]<=111) for p in self.geometry):
            raise ValueError('Cần tọa độ [vĩ độ, kinh độ] trong khu vực Việt Nam')
        if self.geometry[0]==self.geometry[-1]:
            raise ValueError('Hai đầu geometry phải khác nhau')
        return self

class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
    password_confirmation: str = Field(min_length=10,max_length=128)
    @model_validator(mode='after')
    def confirmation_valid(self):
        if self.new_password!=self.password_confirmation:raise ValueError('Mật khẩu mới và xác nhận không khớp')
        if self.new_password==self.current_password:raise ValueError('Mật khẩu mới phải khác mật khẩu hiện tại')
        return self

class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str | None = None
    phone: str | None = None
    notifications_enabled: bool | None = None
    revision: int | None = Field(default=None,ge=1)
    _name = field_validator('name')(Register.name_valid.__func__)
    _phone = field_validator('phone')(Register.phone_valid.__func__)
    @field_validator('email')
    @classmethod
    def email_valid(cls,value):return Register.email_valid(value) if value is not None else None

class ResetRequest(BaseModel):
    identifier: str = Field(min_length=3,max_length=254,validation_alias=AliasChoices('identifier','email'))
    delivery: Literal['email','sms']='email'
    @model_validator(mode='after')
    def valid_identifier(self):
        self.identifier=Register.email_valid(self.identifier) if self.delivery=='email' else Register.phone_valid(self.identifier)
        if not self.identifier:raise ValueError('Vui lòng nhập thông tin đã dùng khi đăng ký')
        return self

class VerifyResetOTP(BaseModel):
    challenge: str = Field(min_length=32,max_length=128)
    code: str = Field(pattern=r'^[0-9]{6}$')

class ResetPassword(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str | None = Field(default=None,min_length=10,max_length=128)
    @model_validator(mode='after')
    def confirmed(self):
        if self.password_confirmation is not None and self.password!=self.password_confirmation:
            raise ValueError('Mật khẩu và xác nhận không khớp')
        return self
