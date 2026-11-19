from datetime import timedelta
import uuid
from backend.app.db import get_database,now
from backend.app.traffic_aggregation import aggregate_sources
from backend.tests.test_physical_forecast import real_road


def source(database,sid,ident):
    value={'_id':ident,'name':'Nguồn quan trắc đã xác minh','kind':'api','segment_id':sid,'direction':'forward','authorized':True,
        'speed_verified':True,'state_verified':True,'active':True,'tested':True,'version':1,'revision':1,'created_by':1,'signature':f'test-source-{ident}',
        'traffic_profile':{'interval_averages':True,'length_verified':True,'training_allowed':True,
            'free_flow_speed_kmh':40,'observed_length_m':100,'lanes':2}}
    database.data_sources.insert_one(value)


def reading(database,sid,at,ident,source_id=99,seconds=60,**changes):
    database.road_readings.insert_one({'_id':ident,'sample_key':str(uuid.uuid4()),'source_id':source_id,'source_version':1,
        'segment_id':sid,'direction':'forward','observed_at':at.isoformat(),
        'metrics':{'interval_seconds':seconds,'present_count':10,'crossing_count':30,'speed_kmh':20,'state':'SLOW',**changes}})


def test_aggregate_intervals_preserves_units_and_avoids_duplicated_sources(analyst_client):
    database=get_database();sid=real_road();source(database,sid,99)
    end=(now()-timedelta(minutes=10)).replace(minute=0,second=0,microsecond=0)
    for i in range(5):reading(database,sid,end-timedelta(minutes=4-i),100+i)
    assert aggregate_sources(database)==1
    row=database.traffic_windows.find_one({'segment_id':sid})
    assert row['coverage_seconds']==300 and row['crossing_count']==150 and row['present_count']==10
    assert row['metrics']['flow_veh_per_hour']==1800 and row['metrics']['density_veh_per_km']==100
    assert row['verified_state']=='SLOW' and row['usable']
    source(database,sid,98)
    database.traffic_windows.delete_many({})
    assert aggregate_sources(database)==0 and database.traffic_windows.count_documents({})==0


def test_aggregate_keeps_confirmed_weather_and_road_conditions(analyst_client):
    database=get_database();sid=real_road();source(database,sid,99)
    end=(now()-timedelta(minutes=10)).replace(minute=0,second=0,microsecond=0)
    for i in range(5):
        reading(database,sid,end-timedelta(minutes=4-i),100+i,rain_mm=4,visibility_km=3,
                stopped_share=.4,accident=i==2,roadwork=False,obstruction=False,flood=False)
    assert aggregate_sources(database)==1
    row=database.traffic_windows.find_one({'segment_id':sid})
    assert row['rain_mm']==4 and row['visibility_km']==3
    assert row['stopped_share']==.4 and row['motion_known'] is True
    assert row['accident'] is True and row['roadwork'] is False
    assert row['obstruction'] is False and row['flood'] is False


def test_aggregate_rejects_overlap_and_point_samples(analyst_client):
    database=get_database();sid=real_road();source(database,sid,99)
    end=(now()-timedelta(minutes=10)).replace(minute=0,second=0,microsecond=0)
    for i in range(5):reading(database,sid,end-timedelta(seconds=(4-i)*50),100+i)
    assert aggregate_sources(database)==0
    database.road_readings.delete_many({})
    for i in range(5):reading(database,sid,end-timedelta(minutes=4-i),100+i,seconds=1)
    assert aggregate_sources(database)==0
