"""User-requested comparison of at most three departure times. Google data is not persisted."""
import asyncio
from datetime import timedelta
from fastapi import APIRouter,Depends
from .db import get_db,now
from .schemas import RouteRequest
from .routing import search_routes

router=APIRouter()


@router.post('/api/routes/departures')
async def compare_departures(body:RouteRequest,db=Depends(get_db)):
    start=body.departure_at or now();gate=asyncio.Semaphore(2)
    async def compare(at):
        async with gate:
            result=await search_routes(db,body.model_copy(update={'departure_at':at}))
        best=result['routes'][0]
        label='Dễ gặp đoạn ùn tắc' if best['high_share']>0 else 'Có đoạn di chuyển chậm' if any(s['speed']=='SLOW' for s in best['traffic_intervals']) else 'Tương đối thông thoáng' if best['unknown_share']<.1 else 'Chưa đủ thông tin về mức độ giao thông'
        return {'departure_at':at.isoformat(),'duration_seconds':best['duration_seconds'],'distance_km':best['distance_km'],
                'label':label,'provider':result['provider'],'is_demo':result['is_demo']}
    candidates=[start+timedelta(hours=offset) for offset in (-1,0,1)
                if now()-timedelta(seconds=30)<=start+timedelta(hours=offset)<=now()+timedelta(days=7)]
    options=await asyncio.gather(*(compare(at) for at in candidates))
    selected=min(options,key=lambda row:row['duration_seconds'])
    return {'options':options,'recommended_departure':selected['departure_at'],
            'notice':'So sánh các giờ khởi hành liền kề. Thời gian dự kiến có thể thay đổi; kiểm tra lại trước khi đi.'}
