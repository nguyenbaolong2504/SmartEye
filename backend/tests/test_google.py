import httpx
import pytest
from backend.app import routing
import json
from datetime import datetime,timedelta
from backend.app.db import now,get_database
from backend.app.history import LOCAL

def mock_google(monkeypatch,status=200,data=None,timeout=False):
    real_client=httpx.AsyncClient
    def handler(request):
        if timeout: raise httpx.ReadTimeout('test timeout',request=request)
        return httpx.Response(status,json=data or {})
    monkeypatch.setattr(routing.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setenv('GOOGLE_ROUTES_API_KEY','private-test-key-never-return')

def test_google_unconfigured(client,route_request,monkeypatch):
    monkeypatch.delenv('GOOGLE_ROUTES_API_KEY',raising=False);route_request['provider']='google'
    assert client.post('/api/routes/search',json=route_request).status_code==503

@pytest.mark.parametrize('status,expected',[(429,429),(403,502),(400,502)])
def test_google_errors_sanitized(client,route_request,monkeypatch,status,expected):
    mock_google(monkeypatch,status,{'error':'private-test-key-never-return'});route_request['provider']='google'
    response=client.post('/api/routes/search',json=route_request)
    assert response.status_code==expected and 'private-test-key' not in response.text

def test_google_timeout(client,route_request,monkeypatch):
    mock_google(monkeypatch,timeout=True);route_request['provider']='google'
    assert client.post('/api/routes/search',json=route_request).status_code==504

def test_google_single_route_without_traffic(client,route_request,monkeypatch):
    mock_google(monkeypatch,data={'routes':[{'duration':'600s','distanceMeters':2000,'polyline':{'encodedPolyline':'_p~iF~ps|U_ulLnnqC_mqNvxq`@'}}]});route_request['provider']='google'
    response=client.post('/api/routes/search',json=route_request)
    assert response.status_code==200
    result=response.json()
    assert len(result['routes'])==1 and result['routes'][0]['unknown_share']==1
    assert result['routes'][0]['duration_seconds']==600
    assert 'private-test-key' not in response.text


def test_google_combined_ranking_is_limited_to_provider_candidates(client,route_request,monkeypatch):
    mock_google(monkeypatch,data={'routes':[{'description':name,'duration':str(seconds)+'s','distanceMeters':km*1000,
        'polyline':{'encodedPolyline':'_p~iF~ps|U_ulLnnqC_mqNvxq`@'}} for name,seconds,km in [('Fast',100,10),('Short',300,4),('Balanced',130,5)]]})
    route_request.update(provider='google',algorithm='compare',weights={'time':.5,'distance':.5})
    result=client.post('/api/routes/search',json=route_request).json()
    assert result['routes'][0]['name']=='Balanced' and result['routes'][0]['duration_seconds']==130
    assert result['optimization']['scope']=='google_candidates'
    assert result['optimization']['algorithm'] is None and result['optimization']['primary_search']=={}


def test_google_future_departures_use_historical_traffic_without_saving_google_data(client,route_request,monkeypatch):
    calls=[];real=httpx.AsyncClient
    def handler(request):
        payload=json.loads(request.content);calls.append(payload)
        hour=datetime.fromisoformat(payload['departureTime'].replace('Z','+00:00')).astimezone(LOCAL).hour
        seconds=1800 if hour==17 else 1200
        return httpx.Response(200,json={'routes':[{'duration':f'{seconds}s','staticDuration':'900s','distanceMeters':4000,
            'polyline':{'encodedPolyline':'_p~iF~ps|U_ulLnnqC_mqNvxq`@'}}]})
    monkeypatch.setattr(routing.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setenv('GOOGLE_ROUTES_API_KEY','private-test-key-never-return')
    monkeypatch.setenv('GOOGLE_MAPS_BROWSER_KEY','public-browser-test-key')
    departure=(now().astimezone(LOCAL)+timedelta(days=1)).replace(hour=17,minute=0,second=0,microsecond=0)
    route_request.update(provider='auto',traffic_mode='demo',departure_at=departure.isoformat())
    response=client.post('/api/routes/search',json=route_request)
    assert response.status_code==200,response.text
    data=response.json();assert data['provider']=='google' and not data['is_demo']
    assert calls[0]['routingPreference']=='TRAFFIC_AWARE_OPTIMAL'
    assert datetime.fromisoformat(calls[0]['departureTime'].replace('Z','+00:00'))==departure
    calls.clear()
    comparison=client.post('/api/routes/departures',json=route_request)
    assert comparison.status_code==200,comparison.text
    result=comparison.json();assert len(calls)==3 and len(result['options'])==3
    assert {datetime.fromisoformat(row['departure_at']).astimezone(LOCAL).hour for row in result['options']}=={16,17,18}
    assert all(row['provider']=='google' and not row['is_demo'] for row in result['options'])
    assert 'private-test-key' not in comparison.text
    database=get_database()
    assert all(database[name].count_documents({})==0 for name in ('demo_profiles','traffic_samples','observations','forecast_registry'))
