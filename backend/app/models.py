"""MongoDB documents. Public IDs stay integers/UUIDs for the existing API."""
from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import ClassVar
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


@dataclass(kw_only=True)
class Document:
    collection: ClassVar[str]
    primary: ClassVar[str] = 'id'
    id: int | str | None = None

    def values(self):
        return {f.name:deepcopy(getattr(self, f.name)) for f in fields(self)
                if f.name != 'id' or self.primary == 'id'}

    @classmethod
    def from_mongo(cls, value):
        value = dict(value)
        value[cls.primary] = value.pop('_id')
        allowed = {f.name for f in fields(cls)}
        return cls(**{k:v for k,v in value.items() if k in allowed})


@dataclass(kw_only=True)
class User(Document):
    collection: ClassVar[str] = 'users'
    email: str
    name: str
    password: str
    role: str = 'user'
    active: bool = True
    auth_version: int = 0
    created_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class LoginSession(Document):
    collection: ClassVar[str] = 'sessions'
    primary: ClassVar[str] = 'token_hash'
    token_hash: str
    user_id: int
    expires_at: str
    auth_version: int = 0


@dataclass(kw_only=True)
class ResetToken(Document):
    collection: ClassVar[str] = 'reset_tokens'
    primary: ClassVar[str] = 'token_hash'
    token_hash: str
    user_id: int
    expires_at: str
    auth_version: int = 0


@dataclass(kw_only=True)
class Segment(Document):
    collection: ClassVar[str] = 'segments'
    name: str
    start_node: str
    end_node: str
    distance_km: float
    geometry: list
    is_demo: bool = True
    active: bool = True
    one_way: bool = False


@dataclass(kw_only=True)
class Camera(Document):
    collection: ClassVar[str] = 'cameras'
    name: str
    segment_id: int
    active: bool = True
    capacity: int = 30
    low_threshold: float = .25
    high_threshold: float = .6
    roi: list = field(default_factory=lambda:[0,0,1,1])
    preview_public: bool = False
    preview_at: str | None = None
    preview_source: str | None = None
    preview_job_id: str | None = None
    preview_mime: str | None = None


@dataclass(kw_only=True)
class TrafficSample(Document):
    collection: ClassVar[str] = 'traffic_samples'
    sample_key: str
    segment_id: int
    observed_at: str
    score: float
    density: str
    count: int
    source: str
    camera_id: int | None = None
    observation_id: int | None = None
    job_id: str | None = None
    occupancy: float | None = None
    vehicle_counts: dict = field(default_factory=dict)


@dataclass(kw_only=True)
class Observation(Document):
    collection: ClassVar[str] = 'observations'
    segment_id: int
    user_id: int
    density: str
    score: float
    observed_at: str
    camera_id: int | None = None
    job_id: str | None = None
    count: int = 0
    source: str = 'manual'
    note: str = ''
    created_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class VideoJob(Document):
    collection: ClassVar[str] = 'video_jobs'
    user_id: int
    camera_id: int
    filename: str
    camera_config: dict
    status: str = 'queued'
    progress: int = 0
    error: str | None = None
    result: dict | None = None
    observed_at: str | None = None
    created_at: str = field(default_factory=timestamp)
    retain_video: bool = False
    history_published: bool = False


@dataclass(kw_only=True)
class Favorite(Document):
    collection: ClassVar[str] = 'favorites'
    user_id: int
    name: str
    request: dict
    created_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class AlertRule(Document):
    collection: ClassVar[str] = 'alert_rules'
    user_id: int
    segment_id: int
    density: str = 'HIGH'
    active: bool = True
    last_sent: str | None = None


@dataclass(kw_only=True)
class Notification(Document):
    collection: ClassVar[str] = 'notifications'
    user_id: int
    message: str
    read: bool = False
    created_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class Audit(Document):
    collection: ClassVar[str] = 'audit'
    action: str
    user_id: int | None = None
    detail: str = ''
    created_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class ForecastRun(Document):
    collection: ClassVar[str] = 'forecast_runs'
    user_id: int
    target: str
    segment_ids: list
    start_at: str
    end_at: str
    epochs: int = 25
    status: str = 'queued'
    running: bool = True
    lock_key: str = 'training'
    progress: int = 0
    message: str = 'Đang chờ huấn luyện'
    report: dict = field(default_factory=dict)
    created_at: str = field(default_factory=timestamp)
    finished_at: str | None = None


@dataclass(kw_only=True)
class TrafficLabel(Document):
    collection: ClassVar[str] = 'traffic_labels'
    segment_id: int
    observed_at: str
    state: str
    reviewer_id: int
    note: str
    updated_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class ForecastRegistry(Document):
    collection: ClassVar[str] = 'forecast_registry'
    run_id: str
    activated_by: int
    activated_at: str = field(default_factory=timestamp)


ALL_MODELS = (User, LoginSession, ResetToken, Segment, Camera, Observation,
              VideoJob, Favorite, AlertRule, Notification, Audit, TrafficSample,
              ForecastRun, TrafficLabel, ForecastRegistry)
