"""Synthetic upstream used only by Playwright's isolated API servers.

Never used as a production fallback. Tests remain deterministic without calling
public address/Overpass services for each browser run.
"""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import Response

app=FastAPI()
PAYLOAD=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/osm-streets.json').read_text(encoding='utf-8'))


@app.get('/health')
def health(): return {'status':'test-fixture'}


@app.get('/api/')
def addresses(q:str=''):
    if 'không tìm thấy' in q.lower(): return {'features':[]}
    destination='84' in q
    return {'features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[105.829 if destination else 105.821,21.03]},
                         'properties':{'osm_type':'N','osm_id':2 if destination else 1,'housenumber':'84' if destination else '12',
                                       'street':'Đường kiểm thử','city':'Hà Nội'}}]}


@app.post('/interpreter')
def roads(): return PAYLOAD


@app.get('/route/v1/driving/{coordinates}')
def fast_routes(coordinates:str):
    start,end=([float(x) for x in p.split(',')] for p in coordinates.split(';'))
    def route(name,seconds,meters,offset):
        middle=[(start[0]+end[0])/2,(start[1]+end[1])/2+offset]
        return {'duration':seconds,'distance':meters,'geometry':{'coordinates':[start,middle,end]},
                'legs':[{'steps':[{'name':name,'duration':seconds,'distance':meters}]}]}
    return {'code':'Ok','routes':[route('Tuyến kiểm thử nhanh',600,4000,.001),route('Tuyến kiểm thử ngắn',900,2000,-.001)],
            'waypoints':[{'location':start,'distance':3},{'location':end,'distance':5}]}


@app.get('/tiles/{z}/{x}/{y}.svg')
def tile(z:int,x:int,y:int):
    return Response('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#edf1ef"/><path d="M0 128H256M128 0V256" stroke="white" stroke-width="12"/></svg>',
                    media_type='image/svg+xml',headers={'Cache-Control':'public, max-age=3600'})
