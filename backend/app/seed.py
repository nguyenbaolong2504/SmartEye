import os
from sqlalchemy import select
from .models import User, Segment, Camera
from .passwords import hash_password
from .config import SEED_DEMO

PLACES = [
    {'node':'hoankiem','name':'Hồ Hoàn Kiếm','lat':21.0287,'lng':105.8524},
    {'node':'caugiay','name':'Cầu Giấy','lat':21.0333,'lng':105.7984},
    {'node':'badinh','name':'Quảng trường Ba Đình','lat':21.0368,'lng':105.8346},
    {'node':'dongda','name':'Đống Đa','lat':21.0177,'lng':105.8292},
    {'node':'tayho','name':'Tây Hồ','lat':21.0628,'lng':105.8183},
    {'node':'mydinh','name':'Mỹ Đình','lat':21.0281,'lng':105.7723},
    {'node':'kimma','name':'Kim Mã','lat':21.0309,'lng':105.8182},
    {'node':'lang','name':'Đường Láng','lat':21.0140,'lng':105.8080},
    {'node':'hai_ba_trung','name':'Hai Bà Trưng','lat':21.0080,'lng':105.8490},
]

def seed_demo_roads(db):
    """Add synthetic road/camera fixtures without reading administrator secrets."""
    if not db.scalar(select(Segment.id).limit(1)):
        places = {p['node']:p for p in PLACES}
        edges = [('Tràng Thi – Điện Biên Phủ','hoankiem','badinh',2.7),('Kim Mã','badinh','kimma',2.4),('Cầu Giấy','kimma','caugiay',2.3),('Tôn Đức Thắng','hoankiem','dongda',3.0),('La Thành – Láng','dongda','lang',2.6),('Đường Láng – Cầu Giấy','lang','caugiay',2.4),('Thanh Niên – Tây Hồ','badinh','tayho',3.6),('Võ Chí Công – Bưởi','tayho','caugiay',4.0),('Xuân Thủy – Hồ Tùng Mậu','caugiay','mydinh',3.4),('Trần Duy Hưng – Phạm Hùng','lang','mydinh',4.6),('Phố Huế','hoankiem','hai_ba_trung',2.7),('Đại Cồ Việt','hai_ba_trung','dongda',2.8),('Nguyễn Thái Học','dongda','kimma',2.5)]
        for name, start, end, distance in edges:
            a, b = places[start], places[end]
            db.add(Segment(name=name, start_node=start, end_node=end, distance_km=distance, geometry=[[a['lat'],a['lng']],[b['lat'],b['lng']]]))
        db.flush()
        for seg in db.scalars(select(Segment).limit(4)):
            db.add(Camera(name='Camera ' + seg.name, segment_id=seg.id))


def seed(db):
    email, password = os.getenv('ADMIN_EMAIL'), os.getenv('ADMIN_PASSWORD')
    if email and password and not db.scalar(select(User).where(User.email == email.lower())):
        if len(password) < 10:
            raise RuntimeError('ADMIN_PASSWORD cần ít nhất 10 ký tự')
        db.add(User(email=email.lower(), name='Quản trị SmartEye', password=hash_password(password), role='admin'))
    if SEED_DEMO:
        seed_demo_roads(db)
    db.commit()
