"""Shared validation, explicit management permissions and optimistic writes."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ReturnDocument
from .db import now, stamp
from .models import Segment
from .security import require_user, audit

Direction = Literal['forward', 'reverse']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Revision(Input):
    revision: int = Field(ge=1)


class NoteAction(Revision):
    note: str = Field(min_length=5, max_length=2000)


class Verification(NoteAction):
    conclusion: Literal['valid', 'invalid', 'insufficient']


def manager(user=Depends(require_user)):
    # An administrative account has no implicit access to private reports.
    if user.role != 'analyst':
        raise HTTPException(403, 'Chức năng này dành cho Quản lý được phân công.')
    return user


def road(db, segment_id, direction='forward', user=None):
    segment = db.get(Segment, segment_id)
    if not segment or not segment.active:
        raise HTTPException(404, 'Chưa cấu hình tuyến đường giám sát hoặc tuyến đã ngừng hoạt động.')
    if direction == 'reverse' and segment.one_way:
        raise HTTPException(422, 'Tuyến đường này không hỗ trợ chiều ngược lại.')
    if user and user.role == 'analyst' and user.managed_segment_ids is not None and segment_id not in user.managed_segment_ids:
        raise HTTPException(403, 'Tuyến đường nằm ngoài phạm vi được phân công.')
    return segment


def allowed_query(user):
    return {'segment_id':{'$in':user.managed_segment_ids}} if user.managed_segment_ids is not None else {}


def get_record(db, model, ident):
    value = db.get(model, ident)
    if value is None:
        raise HTTPException(404, 'Đối tượng không còn tồn tại hoặc không được phép xem.')
    return value


def utc(value):
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError: raise HTTPException(422, 'Thời gian không đúng định dạng.') from None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise HTTPException(422, 'Thời gian cần ghi rõ múi giờ.')
    return value.astimezone(timezone.utc)


def period(start=None, end=None, max_days=366):
    first, last = utc(start) if start else None, utc(end) if end else None
    if first and last and (first > last or (last-first).total_seconds() > max_days*86400):
        raise HTTPException(422, 'Khoảng thời gian không hợp lệ hoặc vượt giới hạn tra cứu.')
    query = {}
    if first: query['$gte'] = first.isoformat()
    if last: query['$lte'] = last.isoformat()
    return query


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def event(user, action, note='', **details):
    return {'event_id':str(uuid.uuid4()), 'actor_id':user.id if user else None,
            'action':action, 'at':stamp(), 'note':note, **details}


def changed(db, model, record, revision, updates, entry):
    if record.revision != revision:
        raise HTTPException(409, 'Thông tin đã thay đổi. Vui lòng tải lại trước khi tiếp tục.')
    document = db.database[model.collection].find_one_and_update(
        {'_id':record.id, 'revision':revision},
        {'$set':{**updates, 'updated_at':stamp()}, '$inc':{'revision':1}, '$push':{'history':entry}},
        return_document=ReturnDocument.AFTER)
    if document is None:
        raise HTTPException(409, 'Thao tác đã được người khác thực hiện. Vui lòng tải lại.')
    # The actor, time and transition history are committed atomically with the
    # resource. Central audit is supplementary; it cannot undo committed state.
    log_event(db, entry['actor_id'], entry['action'], f'{model.collection}:{record.id}', entry['event_id'])
    return model.from_mongo(document)


def log_event(db, actor, action, detail='', event_id='', *, level='info', service='workflow'):
    from .models import Audit
    from .security import request_id
    try:
        row = Audit(user_id=actor, action=action, detail=detail[:300], event_id=event_id or str(uuid.uuid4()), request_id=request_id.get(), level=level, service=service)
        db.add(row); db.commit()
    except Exception:
        db.rollback()
        # Resource-local immutable history remains available for recovery.


def serialize(record):
    return {'id':record.id, **record.values()}


def clean_csv(value):
    text = str(value) if value is not None else ''
    return "'"+text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def position_on_road(position, segment):
    from .routing import point_distance_to_line
    if len(position) != 2 or not (8 <= position[0] <= 24 and 102 <= position[1] <= 111):
        raise HTTPException(422, 'Vị trí không hợp lệ trong khu vực hỗ trợ.')
    if point_distance_to_line(position, segment.geometry) > 500:
        raise HTTPException(422, 'Vị trí cần nằm gần tuyến đường đã chọn (trong 500 m).')
