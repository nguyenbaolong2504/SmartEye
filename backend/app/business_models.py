"""Workflow records: observations, forecasts and published warnings stay separate."""
from dataclasses import dataclass, field
from typing import ClassVar
from .models import Document, timestamp


@dataclass(kw_only=True)
class Incident(Document):
    collection: ClassVar[str] = 'incidents'
    user_id: int
    segment_id: int
    direction: str
    kind: str
    position: list
    occurred_at: str
    content: str
    submission_key: str
    status: str = 'pending'
    assignee_id: int | None = None
    verification: str | None = None
    attachments: list = field(default_factory=list)
    history: list = field(default_factory=list)
    revision: int = 1
    created_at: str = field(default_factory=timestamp)
    updated_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class Warning(Document):
    collection: ClassVar[str] = 'traffic_warnings'
    segment_id: int
    direction: str
    kind: str
    position: list
    severity: str
    content: str
    start_at: str
    end_at: str | None
    created_by: int
    origin: str = 'manual'
    origin_key: str | None = None
    rule_id: int | None = None
    rule_version: int | None = None
    incident_id: int | None = None
    status: str = 'pending_verification'
    verification: str | None = None
    public_snapshot: dict | None = None
    notification_state: str = 'none'
    notification_queue: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    history: list = field(default_factory=list)
    content_version: int = 1
    revision: int = 1
    created_at: str = field(default_factory=timestamp)
    updated_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class ManagedRule(Document):
    collection: ClassVar[str] = 'managed_alert_rules'
    name: str
    segment_id: int
    direction: str
    metric: str
    operator: str
    threshold: float
    unit: str
    window_minutes: int
    start_hour: int
    end_hour: int
    severity: str
    created_by: int
    active: bool = False
    tested: bool = False
    deleted: bool = False
    signature: str = ''
    name_key: str = ''
    content_version: int = 1
    revision: int = 1
    history: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    created_at: str = field(default_factory=timestamp)
    updated_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class DataSource(Document):
    collection: ClassVar[str] = 'data_sources'
    name: str
    kind: str
    segment_id: int
    direction: str
    format: str
    created_by: int
    url: str = ''
    credential_env: str = ''
    interval_seconds: int = 60
    stale_minutes: int = 15
    authorized: bool = False
    public_preview: bool = False
    location_name: str = ''
    position: list | None = None
    speed_verified: bool = False
    state_verified: bool = False
    count_method: str = 'occupancy'
    traffic_profile: dict | None = None
    mapping: dict = field(default_factory=dict)
    units: dict = field(default_factory=dict)
    active: bool = False
    tested: bool = False
    connection_state: str = 'unknown'
    checked_at: str | None = None
    last_received_at: str | None = None
    next_poll_at: str | None = None
    last_error: str | None = None
    signature: str = ''
    version: int = 1
    revision: int = 1
    history: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    created_at: str = field(default_factory=timestamp)
    updated_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class RoadReading(Document):
    collection: ClassVar[str] = 'road_readings'
    sample_key: str
    source_id: int
    source_version: int
    segment_id: int
    direction: str
    observed_at: str
    metrics: dict
    created_at: str = field(default_factory=timestamp)


@dataclass(kw_only=True)
class SourceReceipt(Document):
    collection: ClassVar[str] = 'source_receipts'
    source_id: int
    source_version: int
    accepted: int
    rejected: int
    duplicates: int = 0
    errors: list = field(default_factory=list)
    received_at: str = field(default_factory=timestamp)


BUSINESS_MODELS = (Incident, Warning, ManagedRule, DataSource, RoadReading, SourceReceipt)
