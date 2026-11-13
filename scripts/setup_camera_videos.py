"""Download licensed sample clips, optimize playback, analyze and share on cameras."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.config import DATA,MAX_UPLOAD,MODEL_PATH,UPLOADS
from backend.app.db import SessionLocal,initialize_database,get_database
from backend.app.models import Camera,Segment,User,VideoJob
from backend.app.camera_video import camera_config,queue_video,finish_analysis


def sample_video(source):
    import imageio_ffmpeg
    folder=DATA/'camera-clips';folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{source["id"]}.mp4'
    if not target.is_file():
        original=folder/f'{source["id"]}.original.mp4'
        if not original.is_file():
            pending=folder/f'{source["id"]}.download'
            try:
                size=0
                with httpx.stream('GET',source['download_url'],follow_redirects=True,timeout=90) as response:
                    response.raise_for_status()
                    if not response.headers.get('content-type','').lower().startswith(('video/','application/octet-stream')):
                        raise ValueError('Nguồn không trả về tệp video.')
                    with pending.open('wb') as output:
                        for chunk in response.iter_bytes(1024*1024):
                            size+=len(chunk)
                            if size>MAX_UPLOAD:raise ValueError('Video mẫu vượt giới hạn dung lượng.')
                            output.write(chunk)
                if not size:raise ValueError('Nguồn trả về video rỗng.')
                pending.replace(original)
            finally:pending.unlink(missing_ok=True)
        pending=folder/f'{source["id"]}.pending.mp4'
        try:
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y',
                '-i',str(original),'-an','-vf','scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2',
                '-r','15','-c:v','libx264','-preset','veryfast','-crf','25','-pix_fmt','yuv420p',
                '-movflags','+faststart',str(pending)],check=True,timeout=180)
            pending.replace(target)
        finally:pending.unlink(missing_ok=True)
    return target,hashlib.sha256(target.read_bytes()).hexdigest()


def rush_hour_camera():
    """One separately named synthetic location; do not rename an existing road."""
    with SessionLocal() as db:
        road=db.find_one(Segment,{'start_node':'demo-ngatuso-north','end_node':'demo-ngatuso-south','is_demo':True})
        if not road:
            road=Segment(name='Ngã Tư Sở (minh họa)',start_node='demo-ngatuso-north',end_node='demo-ngatuso-south',
                distance_km=.35,geometry=[[21.0052,105.8205],[21.0035,105.8216],[21.0019,105.8230]],is_demo=True)
            db.add(road);db.commit()
        camera=db.find_one(Camera,{'segment_id':road.id})
        if not camera:
            camera=Camera(name='Ngã Tư Sở · Tình huống 17:00',segment_id=road.id,roi=[0,.63,1,1],capacity=20)
            db.add(camera);db.commit()
        return camera.id,road.id


def region_cameras():
    """Two explicitly synthetic areas; keep existing roads and cameras unchanged."""
    definitions=[('hcm','TP. Hồ Chí Minh','Giao lộ trung tâm TP.HCM (minh họa)',[[10.789,106.697],[10.791,106.7]]),
                 ('danang','Đà Nẵng','Đường trung tâm Đà Nẵng (minh họa)',[[16.066,108.215],[16.069,108.218]])]
    output=[]
    with SessionLocal() as db:
        for key,area,name,points in definitions:
            road=db.find_one(Segment,{'start_node':f'demo-camera-{key}-a','is_demo':True})
            if not road:
                road=Segment(name=name,start_node=f'demo-camera-{key}-a',end_node=f'demo-camera-{key}-b',
                    distance_km=.4,geometry=points,area=area,is_demo=True)
                db.add(road);db.commit()
            camera=db.find_one(Camera,{'segment_id':road.id})
            if not camera:
                camera=Camera(name=f'Camera {area} · Minh họa',segment_id=road.id)
                db.add(camera);db.commit()
            output.append((camera.id,road.id))
    return output


def assign_sources(cameras,assets,slots):
    """No modulo/repeated clips: reject ambiguous IDs or duplicate content."""
    by_slot={source['camera_slot']:item for item in assets for source in [item[0]]}
    selected=[];digests=set()
    for camera in cameras:
        slot=slots.get(camera.id,camera.id if camera.id in (1,2,3,4,5) else None)
        if slot not in by_slot:raise ValueError(f'Camera {camera.id} chưa có video riêng. Cần bổ sung nguồn cho camera này.')
        item=by_slot[slot]
        if item[2] in digests:raise ValueError('Mỗi camera demo cần một nội dung video khác nhau.')
        digests.add(item[2]);selected.append((camera,*item))
    return selected


def setup(ids=None,refresh=False,rush_hour=False,regions=False):
    from backend.app.camera_forecast import prepare_models
    initialize_database()
    if not MODEL_PATH.is_file():raise ValueError('Cần tải mô hình bằng python scripts/download_model.py trước.')
    scenario_id=None;extra=region_cameras() if regions else []
    required=[sid for _,sid in extra]
    if rush_hour:
        from backend.app.demo_data import prepare_demo,status
        scenario_id,segment_id=rush_hour_camera()
        required.append(segment_id)
    if required:
        from backend.app.demo_data import prepare_demo,status
        current=status(get_database())
        if any(sid not in current['segment_ids'] for sid in required):
            print('Bổ sung lịch sử minh họa một năm cho tuyến mới và huấn luyện lại bộ mẫu',flush=True)
            if not prepare_demo(get_database(),days=current.get('history_days') or 365):
                raise ValueError('Đang có lượt chuẩn bị lịch sử khác. Vui lòng đợi rồi chạy lại.')
    manifest=json.loads((ROOT/'database'/'camera-video-sources.json').read_text(encoding='utf-8'))
    # Prefer stable overhead footage for detection; the exact real road remains unverified.
    overhead=[source for source in manifest if source.get('viewpoint')=='overhead']
    if overhead:manifest=overhead
    assets=[]
    for source in manifest:
        if source.get('scenario') and not rush_hour:continue
        print(f'Chuẩn bị video {source["title"]}',flush=True)
        if source.get('detector_model')=='yolo11s':
            from scripts.download_model import download_model
            download_model(MODEL_PATH.with_name('yolo11s.pt'),'s')
        path,digest=sample_video(source)
        assets.append((source,path,digest))
    print('Chuẩn bị mô hình mật độ cho 15, 30 và 60 phút trên lịch sử minh họa',flush=True)
    report=prepare_models(get_database())
    with SessionLocal() as db:
        owner=db.find_one(User,{'role':'admin','active':True})
        if not owner:raise ValueError('Cần ít nhất một tài khoản Admin hoạt động.')
        wanted=list(ids) if ids else [1,2,3,4]
        if scenario_id and scenario_id not in wanted:wanted.append(scenario_id)
        for ident,_ in extra:
            if ident not in wanted:wanted.append(ident)
        cameras=db.find(Camera,{'id':{'$in':wanted}},sort=[('id',1)])
        slots={ident:slot for slot,(ident,_) in enumerate(extra,6)}
        if scenario_id:slots[scenario_id]=5
        for camera,source,path,digest in assign_sources(cameras,assets,slots):
            segment=db.get(Segment,camera.segment_id)
            if not segment or not segment.active:continue
            previous=db.get(VideoJob,camera.analysis_job_id) if camera.analysis_job_id else None
            old_defaults=previous and previous.source_metadata.get('is_demo') and previous.source_metadata.get('roi')==camera.roi and previous.source_metadata.get('capacity')==camera.capacity
            if (not previous and camera.roi==[0,0,1,1] and camera.capacity==30) or old_defaults:
                db.update(Camera,camera.id,{'roi':source['roi'],'capacity':source['capacity']})
                camera.roi=source['roi'];camera.capacity=source['capacity']
            elif not previous and camera.id==scenario_id and camera.roi==[0,.63,1,1] and camera.capacity==20:
                db.update(Camera,camera.id,{'roi':source['roi'],'capacity':source['capacity']})
                camera.roi=source['roi'];camera.capacity=source['capacity']
            old_profile=previous.source_metadata.get('road_profile') if previous else None
            if camera.road_profile is None or camera.road_profile==old_profile:
                db.update(Camera,camera.id,{'road_profile':source['road_profile']})
                camera.road_profile=source['road_profile']
            if (not refresh and previous and previous.status=='completed' and previous.source_metadata.get('sha256')==digest
                and all(previous.source_metadata.get(key)==source.get(key) for key in ('detector_model','detect_full_frame'))
                and all(previous.camera_config.get(key)==getattr(camera,key) for key in ('segment_id','roi','capacity','low_threshold','high_threshold','road_profile'))
                and previous.result and previous.result.get('detection_version')==2
                and previous.result.get('counting_version')==1
                and previous.result.get('capacity_version')==1
                and previous.result.get('camera_forecast',{}).get('version')==report.get('version')
                and previous.result.get('camera_forecast',{}).get('run_id')==report['run_id']
                and (UPLOADS/f'{previous.id}.retained').is_file() and camera.preview_public and camera.preview_job_id==previous.id):
                if not camera.active:db.update(Camera,camera.id,{'active':True})
                print(f'Đã có kết quả cho {camera.name}',flush=True)
                continue
            metadata={key:value for key,value in source.items() if key!='download_url'}
            if camera.id==scenario_id:
                metadata.update(scenario='nga-tu-so-rush-hour',scenario_hour='17:00',
                    scenario_note='Giả định lúc 17:00 để thử dự báo 17:15 và 17:30, không phải địa điểm hay giờ quay thực của clip.')
            metadata.update(is_demo=True,sha256=digest,transformation='Nén H.264, tối đa 960px, 15fps, bỏ âm thanh',
                calibration_note='Vùng mặt đường và sức chứa được ước lượng để chạy thử, cần hiệu chỉnh bằng dữ liệu thực tế.',
                location_note=source.get('location_note','Video minh họa từ Hà Nội. Chưa xác minh video quay tại tuyến đang chọn.'))
            db.update(Camera,camera.id,{'active':True});camera.active=True
            job=queue_video(db,camera,owner.id,path,metadata)
            print(f'Phân tích {camera.name} · {job.id}',flush=True)
            finish_analysis(job.id)
            latest=db.get(VideoJob,job.id)
            if not latest or latest.status!='completed':raise ValueError(latest.error if latest else 'Không lưu được kết quả.')
            print(f'Hoàn tất {camera.name}: trung bình {latest.result["average_count"]} xe/khung hình, đỉnh {latest.result["peak_count"]} xe',flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-id',type=int,action='append',dest='ids')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--rush-hour',action='store_true',help='Thêm tình huống Ngã Tư Sở lúc 17:00 với clip giao lộ minh họa')
    parser.add_argument('--regions',action='store_true',help='Thêm camera minh họa TP.HCM và Đà Nẵng, mỗi camera dùng video riêng')
    args=parser.parse_args()
    setup(args.ids,args.refresh,args.rush_hour,args.regions)
