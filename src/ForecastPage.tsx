import {useEffect,useState} from 'react';
import {ArrowRight,CalendarDays,Clock3,Search} from 'lucide-react';
import {api} from './api';
import {Notice,Spinner} from './components';
import {ForecastInfo,type Comparison} from './ForecastTools';
import {can} from './permissions';
import {type Direction} from './business';
import {type Segment,type User} from './types';

const localDay=(offset=0)=>new Date(Date.now()+7*3600000+offset*86400000).toISOString().slice(0,10);
const hourText=(hour:number)=>`${String(hour).padStart(2,'0')}:00`;
const roadName=(road:Segment)=>`${road.name}, ${road.area||'Hà Nội'}`;
const normalize=(text:string)=>text.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu,'').replace(/đ/g,'d').replace(/[^a-z0-9]+/g,' ').trim();

type Hour={hour:number;label:'FREE'|'SLOW'|'JAM'|null;text:string;similar_days:number;jam_days:number};
type Outlook={date:string;hour:number;segment_id:number;segment_name:string;selected:Hour;hourly:Hour[];
  avoid_windows:{start_hour:number;end_hour:number}[];alternatives:Hour[];explanation:string;advice:string;
  history_days:number;is_demo:boolean;historical?:boolean;model?:string;model_version?:string;issue_at?:string;
  predicted_at?:string;comparison?:Comparison|null};
type PlaceResult={id:string;name:string};
type ForecastQuery={road:number;day:string;hour:number;direction:Direction};

export default function ForecastPage({segments,user,onHistory,onFindRoute,initialRoad}:{
  segments:Segment[];user:User|null;onHistory:(id:number)=>void;onFindRoute:(at:string)=>void;initialRoad?:number;
}){
  const active=segments.filter(s=>s.active);
  const first=active.find(s=>s.id===initialRoad)||active.find(s=>s.name==='Hoàng Quốc Việt')||active[0];
  const [road,setRoad]=useState<Segment|null>(first||null);
  const [text,setText]=useState(first?roadName(first):'');
  const [day,setDay]=useState(localDay(1));
  const [hour,setHour]=useState(17);
  const [direction,setDirection]=useState<Direction>('forward');
  const [query,setQuery]=useState<ForecastQuery|null>(first?{road:first.id,day:localDay(1),hour:17,direction:'forward'}:null);
  const [result,setResult]=useState<Outlook|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const [finding,setFinding]=useState(false);
  const [places,setPlaces]=useState<PlaceResult[]>([]);
  const [location,setLocation]=useState<PlaceResult|null>(null);
  const term=normalize(text);
  const matches=road||location||term.length<2?[]:active.filter(item=>term.split(' ').every(word=>normalize(roadName(item)).split(' ').some(part=>part.startsWith(word)))).slice(0,6);

  useEffect(()=>{
    if(!query){setResult(null);setLoading(false);return;}
    const controller=new AbortController();
    setLoading(true);setError('');setResult(null);
    const params=new URLSearchParams({segment_id:String(query.road),date:query.day,hour:String(query.hour),direction:query.direction});
    api<Outlook>(`/traffic/outlook?${params}`,{signal:controller.signal})
      .then(value=>{if(!controller.signal.aborted)setResult(value);})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[query]);

  function select(item:Segment) {
    setRoad(item);setText(roadName(item));setDirection('forward');
    setPlaces([]);setLocation(null);setQuery(null);setError('');
  }
  function editRoad(value:string) {
    setText(value);setRoad(null);setQuery(null);setPlaces([]);setLocation(null);setError('');
  }
  function view(nextHour=hour){
    if(!road)return;
    setHour(nextHour);setQuery({road:road.id,day,hour:nextHour,direction});
  }
  async function submit(event:React.FormEvent){
    event.preventDefault();
    if(road){view();return;}
    if(matches.length===1){
      select(matches[0]);setQuery({road:matches[0].id,day,hour,direction:'forward'});return;
    }
    if(matches.length){setError('Chọn một đoạn đường trong kết quả bên dưới ô tìm kiếm.');return;}
    if(location)return;
    setFinding(true);setError('');setPlaces([]);
    try{
      const value=await api<{places:PlaceResult[]}>(`/map/places?scope=vn&q=${encodeURIComponent(text.trim())}`);
      setPlaces(value.places);
      if(!value.places.length)setError('Chưa tìm thấy địa chỉ. Thử thêm tên tỉnh hoặc thành phố.');
    }catch(e){setError((e as Error).message);}finally{setFinding(false);}
  }
  const edited=Boolean(query&&(query.day!==day||query.hour!==hour||query.direction!==direction));
  const dateLabel=result?new Date(`${result.date}T12:00:00+07:00`).toLocaleDateString('vi-VN',{weekday:'long',day:'2-digit',month:'2-digit',year:'numeric',timeZone:'Asia/Ho_Chi_Minh'}):'';

  return <>
    <div className="page-heading"><div><div className="eyebrow">LÊN KẾ HOẠCH ĐI LẠI</div><h1>Dự báo giao thông<span>.</span></h1><p>Gõ tên đường và tỉnh hoặc thành phố, sau đó chọn ngày và giờ bạn muốn xem.</p></div></div>
    <form className="card outlook-form" onSubmit={submit}>
      <div className="forecast-road-field">
        <label className="field">Đường, tỉnh hoặc thành phố<input value={text} onChange={e=>editRoad(e.target.value)} disabled={finding} placeholder="Ví dụ Hoàng Quốc Việt, Hà Nội" minLength={3} maxLength={240} required/></label>
        {matches.length>0&&<div className="forecast-road-matches" aria-label="Đoạn đường theo dõi">{matches.map(item=><button type="button" key={item.id} onClick={()=>select(item)}>{roadName(item)}</button>)}</div>}
        {road&&!road.one_way&&<label className="forecast-direction">Chiều di chuyển<select value={direction} onChange={e=>setDirection(e.target.value as Direction)}><option value="forward">Chiều đi</option><option value="reverse">Chiều về</option></select></label>}
      </div>
      <label className="field">Ngày dự định đi<input aria-label="Ngày dự định đi" type="date" required value={day} min={localDay(-365)} max={localDay(7)} onChange={e=>setDay(e.target.value)}/></label>
      <label className="field">Giờ khởi hành<select aria-label="Giờ dự định đi" value={hour} onChange={e=>setHour(Number(e.target.value))}>{Array.from({length:24},(_,h)=><option key={h} value={h}>{hourText(h)}–{hourText(h+1)}</option>)}</select></label>
      <button className="button primary" disabled={loading||finding||Boolean(location)}>{loading||finding?<Spinner/>:road?<CalendarDays size={17}/>:<Search size={17}/>} {road||matches.length?'Xem dự báo':'Tìm địa điểm'}</button>
    </form>
    {places.length>0&&<section className="card workflow-section"><h2>Địa chỉ tìm thấy trên bản đồ</h2><p>Chọn vị trí để kiểm tra phạm vi dữ liệu.</p><div className="workflow-list">{places.map(item=><button type="button" key={item.id} className="workflow-list-item" onClick={()=>{setLocation(item);setText(item.name);setPlaces([]);}}>{item.name}</button>)}</div></section>}
    {location&&<Notice>Đã tìm thấy {location.name}. Vị trí này chưa có đoạn đường và lịch sử quan trắc được liên kết trong SmartEye.</Notice>}
    {error&&<Notice kind="error">{error}</Notice>}
    {edited&&result&&<Notice>Bấm “Xem dự báo” để cập nhật theo lựa chọn mới.</Notice>}
    {loading?<div className="loading-page"><Spinner/><p>Đang đối chiếu lịch sử của khung giờ đã chọn…</p></div>:result&&result.selected.label&&<>
      <section className={`card outlook-summary ${result.selected.label}`}>
        <div><span className="eyebrow">{result.historical?'Ước tính lại · ':''}{dateLabel} · {hourText(result.hour)}–{hourText(result.hour+1)}</span>
          <h2>{road?roadName(road):result.segment_name}</h2><strong className="outlook-state">{result.selected.text}</strong>
          <p>{result.explanation}</p><p className="outlook-advice">{result.advice}</p></div>
        <div className="outlook-history"><CalendarDays size={24}/><b>{result.selected.similar_days}</b><span>ngày đủ dữ liệu cùng khung giờ</span><span className="mode-badge">{result.is_demo?'Lịch sử minh họa':'Lịch sử quan trắc'}</span></div>
      </section>
      <ForecastInfo model={result.model} version={result.model_version} issued={result.issue_at} at={result.predicted_at||new Date(`${result.date}T${String(result.hour).padStart(2,'0')}:00:00+07:00`).toISOString()} label={result.selected.label} demo={result.is_demo} comparison={result.comparison}/>
      {result.avoid_windows.length>0&&<section className="card outlook-windows"><div><h2>Khung giờ nên cân nhắc tránh</h2><p>Các khoảng có khả năng ùn tắc theo lịch sử.</p></div><div>{result.avoid_windows.map(w=><span key={w.start_hour}>{hourText(w.start_hour)}–{hourText(w.end_hour)}</span>)}</div></section>}
      <section className="card outlook-day"><div className="section-title"><Clock3 size={18}/><h2>Dự kiến theo từng giờ</h2></div><p className="muted">Chọn giờ để xem chi tiết. Giờ màu xám chưa đủ dữ liệu.</p><div className="outlook-hour-scroll"><div className="outlook-hours">{result.hourly.map(row=><button type="button" key={row.hour} disabled={!row.label||edited} aria-label={`Xem ${hourText(row.hour)}: ${row.text}`} className={`${row.label||'UNKNOWN'} ${row.hour===result.hour?'selected':''}`} onClick={()=>view(row.hour)}><i/><b>{hourText(row.hour)}</b></button>)}</div></div></section>
      {result.alternatives.length>0&&<section className="outlook-alternatives"><h2>Bạn có thể cân nhắc những giờ này</h2><div>{result.alternatives.map(row=><button type="button" className="card" disabled={edited} key={row.hour} onClick={()=>view(row.hour)}><Clock3 size={20}/><strong>{hourText(row.hour)}</strong><span className={row.label||''}>{row.text}</span><ArrowRight size={16}/></button>)}</div></section>}
      {(can(user,'traffic.view')||can(user,'routes.search')&&!result.historical)&&<section className="card forecast-next"><div><h2>Lên kế hoạch cho hành trình</h2></div><div className="button-row">{can(user,'traffic.view')&&<button className="button" onClick={()=>onHistory(result.segment_id)}>Xem lịch sử tuyến đường</button>}{can(user,'routes.search')&&!result.historical&&<button className="button primary" onClick={()=>onFindRoute(new Date(`${result.date}T${String(result.hour).padStart(2,'0')}:00:00+07:00`).toISOString())}>Tìm tuyến đường<ArrowRight size={16}/></button>}</div></section>}
    </>}
  </>;
}
