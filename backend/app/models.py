from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, stamp

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default='user')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(default=stamp)

class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[str] = mapped_column(String(40))

class ResetToken(Base):
    __tablename__ = 'reset_tokens'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[str] = mapped_column(String(40))

class Segment(Base):
    __tablename__ = 'segments'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    start_node: Mapped[str] = mapped_column(String(80))
    end_node: Mapped[str] = mapped_column(String(80))
    distance_km: Mapped[float] = mapped_column(Float)
    geometry: Mapped[list] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(default=True)
    active: Mapped[bool] = mapped_column(default=True)

class Camera(Base):
    __tablename__ = 'cameras'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    segment_id: Mapped[int] = mapped_column(ForeignKey('segments.id'))
    active: Mapped[bool] = mapped_column(default=True)
    capacity: Mapped[int] = mapped_column(Integer, default=30)
    low_threshold: Mapped[float] = mapped_column(Float, default=.25)
    high_threshold: Mapped[float] = mapped_column(Float, default=.6)
    roi: Mapped[list] = mapped_column(JSON, default=lambda: [0, 0, 1, 1])

class Observation(Base):
    __tablename__ = 'observations'
    id: Mapped[int] = mapped_column(primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey('segments.id'), index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey('cameras.id'), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    density: Mapped[str] = mapped_column(String(10))
    score: Mapped[float] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(300), default='')
    observed_at: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[str] = mapped_column(default=stamp)

class VideoJob(Base):
    __tablename__ = 'video_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    camera_id: Mapped[int] = mapped_column(ForeignKey('cameras.id'))
    filename: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20), default='queued')
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    camera_config: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(default=stamp)

class Favorite(Base):
    __tablename__ = 'favorites'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    request: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=stamp)

class AlertRule(Base):
    __tablename__ = 'alert_rules'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    segment_id: Mapped[int] = mapped_column(ForeignKey('segments.id'))
    density: Mapped[str] = mapped_column(String(10), default='HIGH')
    active: Mapped[bool] = mapped_column(default=True)
    last_sent: Mapped[str | None] = mapped_column(String(40), nullable=True)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    message: Mapped[str] = mapped_column(String(400))
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=stamp)

class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(default=stamp)
