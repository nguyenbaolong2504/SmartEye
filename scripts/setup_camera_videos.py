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


def setup(ids=None,refresh=False):
    from backend.app.camera_forecast import prepare_models
    initialize_database()
    if not MODEL_PATH.is_file():raise ValueError('Cần tải mô hình bằng python scripts/download_model.py trước.')
    manifest=json.loads((ROOT/'database'/'camera-video-sources.json').read_text(encoding='utf-8'))
    assets=[]
    for source in manifest:
        print(f'Chuẩn bị video {source["title"]}',flush=True)
        path,digest=sample_video(source)
        assets.append((source,path,digest))
    print('Chuẩn bị mô hình mật độ cho 15, 30 và 60 phút trên lịch sử minh họa',flush=True)
    report=prepare_models(get_database())
    with SessionLocal() as db:
        owner=db.find_one(User,{'role':'admin','active':True})
        if not owner:raise ValueError('Cần ít nhất một tài khoản Admin hoạt động.')
        cameras=db.find(Camera,{'id':{'$in':ids}} if ids else {'id':{'$in':[1,2,3,4]}},sort=[('id',1)])
        for camera in cameras:
            segment=db.get(Segment,camera.segment_id)
            if not segment or not segment.active:continue
            source,path,digest=assets[(camera.id-1)%len(assets)]
            previous=db.get(VideoJob,camera.analysis_job_id) if camera.analysis_job_id else None
            if not previous and camera.roi==[0,0,1,1] and camera.capacity==30:
                db.update(Camera,camera.id,{'roi':source['roi'],'capacity':source['capacity']})
                camera.roi=source['roi'];camera.capacity=source['capacity']
            if (not refresh and previous and previous.status=='completed' and previous.source_metadata.get('sha256')==digest
                and all(previous.camera_config.get(key)==getattr(camera,key) for key in ('segment_id','roi','capacity','low_threshold','high_threshold'))
                and previous.result and previous.result.get('detection_version')==2
                and previous.result.get('camera_forecast',{}).get('version')==report.get('version')
                and previous.result.get('camera_forecast',{}).get('run_id')==report['run_id']
                and (UPLOADS/f'{previous.id}.retained').is_file() and camera.preview_public and camera.preview_job_id==previous.id):
                if not camera.active:db.update(Camera,camera.id,{'active':True})
                print(f'Đã có kết quả cho {camera.name}',flush=True)
                continue
            metadata={key:value for key,value in source.items() if key!='download_url'}
            metadata.update(is_demo=True,sha256=digest,transformation='Nén H.264, tối đa 960px, 15fps, bỏ âm thanh',
                calibration_note='Vùng mặt đường và sức chứa được ước lượng để chạy thử, cần hiệu chỉnh bằng dữ liệu thực tế.',
                location_note='Video minh họa từ Hà Nội. Chưa xác minh video quay tại tuyến đang chọn.')
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
    args=parser.parse_args()
    setup(args.ids,args.refresh)
