import {useEffect,useMemo,useRef,useState} from 'react';
import {ArrowRight,Camera,Expand,ExternalLink,MapPin,Minimize,Pause,Play,RefreshCw} from 'lucide-react';
import {can} from './permissions';
import {Empty,Notice,Spinner} from './components';
import {useRemote} from './business';
import {TrafficMap} from './TrafficMap';
import {type TrafficCamera,type User} from './types';
import './cameras.css';

const labels:Record<TrafficCamera['state'],string>={ready:'Sẵn sàng',stale:'Cần kiểm tra kết nối',error:'Mất kết nối',inactive:'Đã tắt',empty:'Chưa có hình ảnh',archive:'Hình ảnh đã lưu'};
const cameraTime=(value:string)=>new Date(value).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const initial={cameras:[] as TrafficCamera[],generated_at:''};

export default function CameraPage({user,tileUrl,onForecast}:{
  user:User|null;tileUrl?:string;onForecast:(id:number,direction:'forward'|'reverse')=>void;
}){
  const {data,loading,error,reload}=useRemote('/traffic/cameras',initial);
  const [area,setArea]=useState('');
  const [road,setRoad]=useState('');
  const [chosen,setChosen]=useState('');
  useEffect(()=>{
    const timer=setInterval(()=>{if(!document.hidden)reload();},30000);
    return()=>clearInterval(timer);
  },[reload]);
  const areas=[...new Set(data.cameras.map(camera=>camera.area))].sort((a,b)=>a.localeCompare(b,'vi'));
  const inArea=data.cameras.filter(camera=>!area||camera.area===area);
  const roads=[...new Map(inArea.map(camera=>[camera.segment_id,camera.segment_name])).entries()];
  const filtered=inArea.filter(camera=>!road||String(camera.segment_id)===road);
  const selected=filtered.find(camera=>camera.id===chosen)||filtered[0];
  const markers=useMemo(()=>filtered.flatMap(camera=>camera.position?[{
    id:camera.id,name:camera.name,position:camera.position,available:Boolean(camera.image_url||camera.video_url),
  }]:[]),[filtered]);
  return <>
    <div className="page-heading"><div><div className="eyebrow">QUAN SÁT TRƯỚC KHI ĐI</div><h1>Camera giao thông<span>.</span></h1><p>Chọn khu vực và camera để xem hình ảnh trên tuyến đường bạn quan tâm.</p></div><button className="button small" disabled={loading} onClick={reload}><RefreshCw size={16}/>Làm mới danh sách</button></div>
    <section className="card camera-filters" aria-label="Bộ lọc camera">
      <label className="field">Tỉnh/thành phố<select value={area} onChange={event=>{setArea(event.target.value);setRoad('');setChosen('');}}><option value="">Tất cả tỉnh/thành phố</option>{areas.map(value=><option key={value}>{value}</option>)}</select></label>
      <label className="field">Tuyến đường<select value={road} onChange={event=>{setRoad(event.target.value);setChosen('');}}><option value="">Tất cả tuyến đường</option>{roads.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
      <label className="field">Vị trí camera<select value={selected?.id||''} disabled={!filtered.length} onChange={event=>setChosen(event.target.value)}>{!filtered.length&&<option value="">Chưa có camera</option>}{filtered.map(camera=><option key={camera.id} value={camera.id}>{camera.location_name}</option>)}</select></label>
    </section>
    {error&&<Notice kind="error">{error}<button className="text-button" onClick={reload}>Thử tải lại</button></Notice>}
    {loading&&!data.generated_at?<div className="workflow-loading"><Spinner/>Đang tải danh sách camera…</div>:<div className="camera-workspace">
      <section className="card camera-directory"><div className="section-title"><Camera size={18}/><h2>Danh sách camera</h2><span className="count-badge">{filtered.length}</span></div>
        {filtered.length?<div className="camera-directory-list">{filtered.map(camera=><button type="button" key={camera.id} className={`camera-list-item ${selected?.id===camera.id?'selected':''}`} aria-pressed={selected?.id===camera.id} onClick={()=>setChosen(camera.id)}><span className="camera-list-title"><Camera size={17}/><b>{camera.name}</b></span><span>{camera.segment_name}</span><small><MapPin size={12}/>{camera.location_name} · {camera.area}</small><span className={`camera-status ${camera.state}`}>{labels[camera.state]}</span></button>)}</div>:<Empty><Camera size={30}/><p>Chưa có camera được chia sẻ trong khu vực này.</p></Empty>}
      </section>
      <div className="camera-observation">
        <TrafficMap places={[]} segments={[]} routes={[]} selected="" onSelect={()=>{}} browserKey="" provider="osm" tileUrl={tileUrl} cameraMarkers={markers} selectedCameraId={selected?.id} onCameraSelect={setChosen}/>
        {selected?<section className="card camera-details">
          <div className="camera-details-heading"><div><h2>{selected.name}</h2><p><MapPin size={14}/>{selected.location_name} · {selected.area}</p></div><span className={`camera-status ${selected.state}`}>{labels[selected.state]}</span></div>
          <CameraViewer key={`${selected.id}-${selected.image_url}-${selected.video_url}`} camera={selected}/>
          <dl className="camera-information"><div><dt>Tuyến đường</dt><dd>{selected.segment_name} · {selected.direction==='reverse'?'Chiều về':'Chiều đi'}</dd></div><div><dt>Nguồn hình ảnh</dt><dd>{selected.source_name}{selected.source_host&&<small>{selected.source_host}</small>}</dd></div><div><dt>Thời điểm ghi hình</dt><dd>{selected.captured_at?cameraTime(selected.captured_at):'Nguồn chưa cung cấp thời điểm ghi hình'}</dd></div><div><dt>Kiểm tra kết nối</dt><dd>{selected.checked_at?cameraTime(selected.checked_at):'Chưa có lần kiểm tra gần đây'}</dd></div></dl>
          {!selected.position_exact&&<p className="micro">Ghim được đặt theo đoạn đường đã khai báo{selected.is_demo?' trong dữ liệu minh họa':''}.</p>}
          <div className="camera-detail-actions">{can(user,'forecast.view')&&selected.segment_active&&<button className="button primary" onClick={()=>onForecast(selected.segment_id,selected.direction)}>Xem dự báo tuyến đường<ArrowRight size={16}/></button>}{selected.source_url&&<a className="button" href={selected.source_url} target="_blank" rel="noreferrer">Mở nguồn camera<ExternalLink size={15}/></a>}</div>
        </section>:<section className="card"><Empty><p>Chọn camera trong danh sách hoặc trên bản đồ để xem hình ảnh.</p></Empty></section>}
      </div>
    </div>}
  </>;
}

function CameraViewer({camera}:{camera:TrafficCamera}){
  const [image,setImage]=useState('');
  const [received,setReceived]=useState('');
  const [busy,setBusy]=useState(Boolean(camera.image_url));
  const [error,setError]=useState('');
  const [paused,setPaused]=useState(false);
  const [attempt,setAttempt]=useState(0);
  const [expanded,setExpanded]=useState(false);
  const objectUrl=useRef('');
  useEffect(()=>{
    if(!camera.image_url)return;
    const controller=new AbortController();
    async function load(){
      setBusy(true);setError('');
      try{
        const response=await fetch(camera.image_url!,{signal:controller.signal,cache:'no-store'});
        if(!response.ok)throw new Error('Chưa lấy được hình ảnh mới. Vui lòng thử lại sau.');
        const blob=await response.blob();
        if(controller.signal.aborted)return;
        if(objectUrl.current)URL.revokeObjectURL(objectUrl.current);
        objectUrl.current=URL.createObjectURL(blob);
        setImage(objectUrl.current);setReceived(response.headers.get('X-Camera-Received-At')||'');
      }catch(reason){if(!controller.signal.aborted)setError((reason as Error).message);}
      finally{if(!controller.signal.aborted)setBusy(false);}
    }
    void load();
    return()=>controller.abort();
  },[camera.image_url,attempt]);
  useEffect(()=>()=>{if(objectUrl.current)URL.revokeObjectURL(objectUrl.current);},[]);
  useEffect(()=>{
    if(paused||!camera.image_url||!camera.refresh_seconds)return;
    const timer=setInterval(()=>{if(!document.hidden)setAttempt(value=>value+1);},Math.max(10,camera.refresh_seconds)*1000);
    return()=>clearInterval(timer);
  },[paused,camera.image_url,camera.refresh_seconds]);
  useEffect(()=>{
    if(!expanded)return;
    const previous=document.body.style.overflow;
    document.body.style.overflow='hidden';
    const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setExpanded(false);};
    window.addEventListener('keydown',close);
    return()=>{document.body.style.overflow=previous;window.removeEventListener('keydown',close);};
  },[expanded]);
  const hasMedia=Boolean(camera.image_url||camera.video_url);
  return <div className={`camera-viewer ${expanded?'expanded':''}`}>
    <div className="camera-viewer-toolbar"><span>{camera.media_kind==='recording'?'Ảnh/video đã lưu':camera.video_url?'Video từ nguồn':'Ảnh camera cập nhật'}</span><div>
      {!!camera.refresh_seconds&&camera.image_url&&<button type="button" className="button small" aria-label={paused?'Tiếp tục cập nhật':'Tạm dừng cập nhật'} aria-pressed={paused} onClick={()=>setPaused(value=>!value)}>{paused?<Play size={14}/>:<Pause size={14}/>}<span>{paused?'Tiếp tục cập nhật':'Tạm dừng cập nhật'}</span></button>}
      {hasMedia&&<button className="icon-button" aria-label={expanded?'Thu gọn hình ảnh':'Phóng to hình ảnh'} onClick={()=>setExpanded(value=>!value)}>{expanded?<Minimize size={17}/>:<Expand size={17}/>}</button>}
    </div></div>
    <div className="camera-picture">
      {camera.video_url?<video key={attempt} controls playsInline preload="none" src={camera.video_url} poster={image||undefined} onError={()=>setError('Không phát được video từ nguồn. Bạn có thể thử lại hoặc mở nguồn camera.')}/>:
        image?<img src={image} alt={`Hình ảnh ${camera.name}`} onError={()=>setError('Không đọc được hình ảnh từ camera.')}/>:
        <Empty>{busy?<Spinner/>:<Camera size={40}/>}<p>{busy?'Đang lấy hình ảnh…':camera.state==='inactive'?'Camera đã ngừng hoạt động.':'Camera chưa có hình ảnh được chia sẻ.'}</p></Empty>}
    </div>
    {error&&<Notice kind="error">{error}</Notice>}
    {hasMedia&&<div className="camera-viewer-foot"><span>{received?`Nhận ảnh từ nguồn lúc ${cameraTime(received)}`:camera.captured_at?`Ghi hình ${cameraTime(camera.captured_at)}`:camera.video_url?'Nhấn nút phát để xem video.':'Đang chờ hình ảnh từ nguồn.'}</span><button type="button" className="text-button" disabled={busy} onClick={()=>setAttempt(value=>value+1)}><RefreshCw size={14}/>{busy?'Đang tải':'Thử tải lại'}</button></div>}
  </div>;
}
