from copy import deepcopy
import pytest
from backend.app.traffic_metrics import quantities
from backend.app.camera_measurements import measurement_frames
from backend.app.schemas import RoadProfile


def test_document_formulas_and_units():
    m=quantities(present_count=80,length_m=500,lanes=3,crossings=150,observed_seconds=300,
        speed_kmh=20,free_flow_speed_kmh=40,distance_km=1.5,length_verified=True,speed_verified=True)
    assert m['flow_veh_per_hour']==1800 and m['flow_veh_per_hour_per_lane']==600
    assert m['density_veh_per_km']==160 and m['density_veh_per_km_per_lane']==pytest.approx(160/3)
    assert m['congestion_index']==.5 and m['travel_time_index']==2 and m['travel_minutes']==4.5
    assert m['speed_loss_band']=='DENSE'


def test_missing_calibration_and_standstill_do_not_create_speed_or_eta():
    m=quantities(present_count=80,length_m=500,speed_kmh=20,free_flow_speed_kmh=40)
    assert m['density_veh_per_km'] is m['avg_speed_kmh'] is m['congestion_index'] is None
    stopped=quantities(speed_kmh=0,free_flow_speed_kmh=40,distance_km=1,speed_verified=True)
    assert stopped['congestion_index']==1 and stopped['standstill']
    assert stopped['travel_time_index'] is stopped['travel_minutes'] is None
    assert quantities(crossings=100,observed_seconds=0)['flow_veh_per_hour'] is None


def boxes(y):
    return [{'box':[x,y-8,x+5,y],'track_id':ident,'label':'car','counted_as':'car'} for x,ident in ((20,1),(60,2))]


def frames(ys):
    return [{'second':i/10,'width':100,'height':100,'count':2,'boxes':boxes(y),'score':.3} for i,y in enumerate(ys)]


def test_crossings_count_each_track_once_not_each_frame_and_ignore_line_jitter():
    rows=frames([20+i*.6 for i in range(101)])
    original=deepcopy(rows)
    result,m=measurement_frames(rows,{'roi':[0,0,1,1]},10)
    assert m['crossings']==2 and result[-1]['crossing_count']==2
    assert result[-1]['traffic_metrics']['flow_veh_per_hour']==pytest.approx(2*3600/10.1)
    assert not m['count_line_verified'] and not m['speed_calibration_available']
    assert rows==original
    assert measurement_frames(frames([49.9,50.1]*30),{'roi':[0,0,1,1]},10)[1]['crossings']==0


def test_homography_speed_requires_measured_geometry_and_matches_known_distance():
    config={'roi':[0,0,1,1],'road_profile':{'lanes':2,'road_width_m':10,'observed_length_m':100,'calibration':'measured',
        'measurement':{'verified':True,'image_points':[[0,0],[1,0],[1,1],[0,1]],
            'ground_points':[[0,0],[10,0],[10,100],[0,100]],'free_flow_speed_kmh':40}}}
    rows=frames([10+i for i in range(21)])
    result,details=measurement_frames(rows,config,10)
    m=result[-1]['traffic_metrics']
    assert details['speed_calibration_available'] and m['avg_speed_kmh']==pytest.approx(36,rel=.001)
    assert m['congestion_index']==pytest.approx(.1,abs=.001) and m['density_veh_per_km']==20
    config['road_profile']['calibration']='estimated'
    result,details=measurement_frames(rows,config,10)
    assert not details['speed_calibration_available'] and result[-1]['traffic_metrics']['avg_speed_kmh'] is None
    config['road_profile']['calibration']='measured'
    for frame in rows:frame['camera_shift']=[.1,0]
    moved,_=measurement_frames(rows,config,10)
    assert moved[-1]['traffic_metrics']['avg_speed_kmh'] is None
    assert not moved[-1]['traffic_metrics']['quality']['camera_stable']


def test_calibration_rejects_degenerate_points_and_unverified_survey():
    with pytest.raises(ValueError):RoadProfile(measurement={'count_line':[[.5,.5],[.5,.5]]})
    with pytest.raises(ValueError):RoadProfile(calibration='measured',measurement={'verified':True,'note':'measured reference',
        'image_points':[[0,0],[.5,0],[1,0],[.2,0]],'ground_points':[[0,0],[10,0],[10,100],[0,100]]})
    with pytest.raises(ValueError):RoadProfile(measurement={'verified':True})
