import httpx
import pytest
from backend.app import routing

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
