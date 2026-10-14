import re
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class Register(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
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

class CameraInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    segment_id: int
    active: bool = True
    capacity: int = Field(default=30, ge=1, le=500)
    low_threshold: float = Field(default=.25, ge=.01, le=.95)
    high_threshold: float = Field(default=.6, ge=.02, le=1)
    roi: list[float] = Field(default=[0, 0, 1, 1], min_length=4, max_length=4)
    @model_validator(mode='after')
    def coherent(self):
        if self.low_threshold >= self.high_threshold:
            raise ValueError('Ngưỡng thấp phải nhỏ hơn ngưỡng cao')
        x1, y1, x2, y2 = self.roi
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1) or (x2-x1)*(y2-y1) < .01:
            raise ValueError('ROI phải nằm trong ảnh và chiếm ít nhất 1% khung hình')
        return self

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
    name: str = Field(default='', max_length=120)
    node: str | None = Field(default=None, max_length=80)

class RouteRequest(BaseModel):
    origin: Waypoint
    destination: Waypoint
    mode: Literal['DRIVE', 'TWO_WHEELER'] = 'DRIVE'
    provider: Literal['demo', 'google'] = 'demo'
    departure_at: datetime | None = None
    weights: dict[str, float] = Field(default={'time': .45, 'distance': .2, 'density': .35})
    @model_validator(mode='after')
    def coherent(self):
        if abs(self.origin.lat - self.destination.lat) + abs(self.origin.lng - self.destination.lng) < .00005:
            raise ValueError('Điểm đi và điểm đến phải khác nhau')
        if set(self.weights) != {'time', 'distance', 'density'} or any(not 0 <= v <= 1 for v in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError('Trọng số phải nằm trong 0–1 và tổng lớn hơn 0')
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
    @model_validator(mode='after')
    def coherent(self):
        if self.start_node == self.end_node:
            raise ValueError('Mã hai đầu đoạn đường phải khác nhau')
        if any(len(p)!=2 or not (20.5<=p[0]<=21.5 and 105.2<=p[1]<=106.2) for p in self.geometry):
            raise ValueError('Geometry cần các điểm [vĩ độ, kinh độ] tại Hà Nội')
        if self.geometry[0]==self.geometry[-1]:
            raise ValueError('Hai đầu geometry phải khác nhau')
        return self

class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)

class ResetRequest(BaseModel):
    email: str = Field(max_length=254)

class ResetPassword(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=10, max_length=128)
