from copy import deepcopy
import numpy as np
import pytest
from pydantic import ValidationError
from backend.app import road_capacity,camera_forecast
from backend.app.schemas import CameraInput


def config(width=7,length=60):
    return {'high_threshold':.6,'road_profile':{'lanes':2,'road_width_m':width,
        'observed_length_m':length,'usable_fraction':1.,'calibration':'estimated'}}


def test_same_vehicles_use_more_of_narrow_road_and_longer_visible_area_has_more_storage():
    cars={'car':10}
    narrow=road_capacity.frame_load(cars,config(3.5,50))
    wide=road_capacity.frame_load(cars,config(14,50))
    longer=road_capacity.frame_load(cars,config(3.5,100))
    assert narrow['load_ratio']==pytest.approx(wide['load_ratio']*4,abs=.001)
    assert narrow['load_ratio']==pytest.approx(longer['load_ratio']*2,abs=.001)
    assert narrow['load_ratio']>1 and wide['load_ratio']<.4


def test_vehicle_types_use_different_storage_and_only_current_count_is_used():
    cars=road_capacity.frame_load({'car':12},config())
    bikes=road_capacity.frame_load({'motorcycle':12},config())
    buses=road_capacity.frame_load({'bus':12},config())
    assert cars['equivalent_count']==bikes['equivalent_count']*4
    assert buses['equivalent_count']==cars['equivalent_count']*3
    assert road_capacity.frame_load({'car':12,'cumulative_count':1000},config())==cars


def frames(seconds=40,moving=False,load=.8,camera_pan=False):
    output=[]
    for i in range(seconds*10):
        shift=i*2 if camera_pan else 0
        movement=i*2 if moving else 0
        output.append({'second':i/10,'count':2,'score':load,'load_ratio':load,
            'camera_shift':[2 if i and camera_pan else 0,0],
            'boxes':[{'track_id':ident,'box':[20+ident*80+shift+movement,40,50+ident*80+shift+movement,60]}
                     for ident in (1,2)]})
    return output


def test_busy_stopped_vehicles_need_sustained_observation_not_a_single_red_light_frame():
    rows=road_capacity.motion_evidence(frames())
    assert not rows[0]['motion_known']
    assert rows[100]['stopped_share']==1 and not rows[100]['persistent_queue']
    assert rows[-1]['persistent_queue'] and rows[-1]['queue_seconds']>=30
    assert not road_capacity.motion_evidence(frames(5))[-1]['persistent_queue']


def test_moving_vehicles_or_low_load_are_not_a_persistent_queue():
    moving=road_capacity.motion_evidence(frames(moving=True))
    assert moving[-1]['motion_known'] and moving[-1]['stopped_share']==0
    assert not any(row['persistent_queue'] for row in moving)
    assert not any(row['persistent_queue'] for row in road_capacity.motion_evidence(frames(load=.2)))


def test_camera_pan_is_removed_from_relative_track_displacement():
    rows=road_capacity.motion_evidence(frames(camera_pan=True))
    assert rows[-1]['motion_known'] and rows[-1]['stopped_share']==1


@pytest.mark.parametrize('field,value',[('road_width_m',0),('road_width_m',float('nan')),
    ('observed_length_m',float('inf')),('usable_fraction',0),('lanes',20)])
def test_invalid_geometry_is_rejected(field,value):
    profile=config()['road_profile'];profile[field]=value
    with pytest.raises(ValidationError):CameraInput(name='Camera test',segment_id=1,road_profile=profile)


def test_demo_region_setup_is_idempotent_and_does_not_reassign_existing_cameras(client):
    from scripts.setup_camera_videos import region_cameras,assign_sources
    from backend.app.db import SessionLocal
    from backend.app.models import Camera,Segment
    with SessionLocal() as db:before=deepcopy(db.get(Camera,1).values())
    first=region_cameras();assert region_cameras()==first and len(first)==2
    with SessionLocal() as db:
        assert db.get(Camera,1).values()==before
        assert {db.get(Segment,sid).area for _,sid in first}=={'TP. Hồ Chí Minh','Đà Nẵng'}
        cameras=[db.get(Camera,1),db.get(Camera,2)]
        with pytest.raises(ValueError,match='khác nhau'):
            assign_sources(cameras,[({'camera_slot':1},'a','same'),({'camera_slot':2},'b','same')],{})
        assigned=assign_sources(cameras,[({'camera_slot':1},'a','one'),({'camera_slot':2},'b','two')],{})
        assert [row[-1] for row in assigned]==['one','two']


def test_probabilities_and_calibration_metrics_do_not_force_eighty_or_ninety_percent():
    p=np.array([[.8,.1,.1],[.1,.2,.7],[.3,.5,.2]])
    calibrated=camera_forecast.probabilities(p,1.5)
    assert calibrated.sum(axis=1)==pytest.approx([1,1,1])
    assert calibrated[0,2]<.2 and calibrated[1,2]>.2
    assert 0<=camera_forecast.calibration_error(np.array([0,2,1]),calibrated)<=1
    assert camera_forecast.calibration_error(np.array([0,2]),np.array([[1,0,0],[0,0,1]]))==0


def test_saving_camera_geometry_invalidates_old_analysis(admin_client):
    from backend.tests.test_camera_video import published_video
    from backend.app.camera_video import matches
    from backend.app.db import SessionLocal
    from backend.app.models import Camera
    job=published_video()
    with SessionLocal() as db:
        camera=db.get(Camera,1)
        body={key:getattr(camera,key) for key in ('name','segment_id','active','capacity','low_threshold','high_threshold','roi')}
    body['road_profile']=config()['road_profile']
    saved=admin_client.put('/api/cameras/1',json=body)
    assert saved.status_code==200
    assert saved.json()['road_profile']==body['road_profile']
    with SessionLocal() as db:assert not matches(db.get(Camera,1),job)
