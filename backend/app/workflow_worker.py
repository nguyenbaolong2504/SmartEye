"""Recover deliveries and receive only explicitly enabled, tested API sources."""
import asyncio
import os
import time
from datetime import timedelta
from .db import SessionLocal, stamp, now
from .business_models import DataSource, SourceReceipt
from .business_common import log_event


async def work():
    from .sources import source_request, decode_rows, receive
    from .warnings import deliver_publications, expire_publications
    physical_checked=0.
    while True:
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(expire_publications,db)
                await asyncio.to_thread(deliver_publications,db.database)
                if time.monotonic()-physical_checked>=60:
                    from .traffic_aggregation import aggregate_sources
                    from .traffic_forecast import refresh_active
                    from .traffic_windows import reconcile
                    await asyncio.to_thread(aggregate_sources,db.database)
                    await asyncio.to_thread(refresh_active,db.database)
                    await asyncio.to_thread(reconcile,db.database)
                    physical_checked=time.monotonic()
                sources=db.find(DataSource,{'active':True,'tested':True,'kind':'api',
                    '$or':[{'next_poll_at':None},{'next_poll_at':{'$lte':stamp()}}]},limit=10)
                for source in sources:
                    reserved=db.database.data_sources.update_one({'_id':source.id,'version':source.version,'active':True,
                        '$or':[{'next_poll_at':None},{'next_poll_at':{'$lte':stamp()}}]},
                        {'$set':{'next_poll_at':(now()+timedelta(seconds=source.interval_seconds)).isoformat()}})
                    if not reserved.modified_count:continue
                    try:
                        raw,_=await source_request(source)
                        await asyncio.to_thread(receive,db,source,decode_rows(raw,source.format))
                    except Exception:
                        db.rollback()
                        db.database.data_sources.update_one({'_id':source.id,'version':source.version},
                            {'$set':{'connection_state':'error','last_error':'Không nhận được dữ liệu hợp lệ từ nguồn.','checked_at':stamp()}})
                        db.add(SourceReceipt(source_id=source.id,source_version=source.version,accepted=0,rejected=0,
                                             errors=[{'reason':'Mất kết nối, thay đổi cấu hình hoặc dữ liệu chưa hợp lệ.'}]))
                        db.commit()
                        log_event(db,None,'source_poll_failed',f'data_sources:{source.id}',level='error',service='ingestion')
        except asyncio.CancelledError:raise
        except Exception:pass  # Next iteration retries; never print connection secrets.
        await asyncio.sleep(10)


def start():
    return asyncio.create_task(work()) if os.getenv('WORKFLOW_WORKER_ENABLED','true').lower()=='true' else None
