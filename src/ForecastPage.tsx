import { lazy, Suspense, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, CalendarDays, Clock3, Settings2 } from 'lucide-react';
import { api } from './api';
import { Notice,Spinner } from './components';
import DemoSetup from './DemoSetup';
import { type Segment,type User,type DataMode,type DemoStatus } from './types';
const Management=lazy(()=>import('./ForecastManagement'));
const localDay=(offset=0)=>new Date(Date.now()+7*3600000+offset*86400000).toISOString().slice(0,10);
const hourText=(hour:number)=>`${String(hour).padStart(2,'0')}:00`;
type Hour={hour:number;label:'FREE'|'SLOW'|'JAM';text:string;similar_days:number;jam_days:number;jam_frequency:number|null};
type Outlook={state:string;date:string;hour:number;segment_id:number;segment_name:string;selected:Hour;hourly:Hour[];avoid_windows:{start_hour:number;end_hour:number}[];alternatives:Hour[];explanation:string;advice:string;history_days:number;history_start:string;history_end:string;is_demo:boolean};
export default function ForecastPage({segments,user,dataMode,demo,onLogin,onHistory,onUpdated,onFindRoute,initialRoad}:{segments:Segment[];user:User|null;dataMode:DataMode;demo:DemoStatus|null;onLogin:()=>void;onHistory:(id:number)=>void;onUpdated:()=>void;onFindRoute:(at:string)=>void;initialRoad?:number}){
  const[road,setRoad]=useState(String(initialRoad||segments.find(s=>s.name==='Hoàng Quốc Việt')?.id||segments.find(s=>s.active)?.id||''));
  const[day,setDay]=useState(localDay(1));const[hour,setHour]=useState(17);const[query,setQuery]=useState({road,day,hour,version:0});
  const[result,setResult]=useState<Outlook|null>(null);const[error,setError]=useState('');const[loading,setLoading]=useState(false);const[manage,setManage]=useState(false);
  const manager=user?.role==='admin'||user?.role==='analyst';const ready=dataMode!=='demo'||demo?.planning_ready;
  useEffect(()=>{let current=true;if(!query.road||!ready){setResult(null);return;}
    setLoading(true);setError('');setResult(null);
    api<Outlook>(`/traffic/outlook?segment_id=${query.road}&date=${query.day}&hour=${query.hour}`).then(value=>{if(current)setResult(value);}).catch(e=>{if(current)setError(e.message);}).finally(()=>{if(current)setLoading(false);});
    return()=>{current=false;};
  },[query,ready,demo?.generated_at]);
  function view(nextHour=hour){setHour(nextHour);setQuery({road,day,hour:nextHour,version:query.version+1});}
  if(manage&&manager)return <><button className="text-button back-link" onClick={()=>setManage(false)}><ArrowLeft size={16}/>Quay lại dự báo</button><Notice>Phần quản lý dành cho lịch sử theo dõi thực tế. Dữ liệu minh họa được lưu riêng.</Notice><Suspense fallback={<Spinner/>}><Management segments={segments} user={user} onLogin={onLogin} onUpload={()=>setManage(false)}/></Suspense></>;
  const edited=road!==query.road||day!==query.day||hour!==query.hour;
  const dateLabel=result?new Date(`${result.date}T12:00:00+07:00`).toLocaleDateString('vi-VN',{weekday:'long',day:'2-digit',month:'2-digit'}):'';
  return <><div className="page-heading"><div><div className="eyebrow">CHỦ ĐỘNG CHO NGÀY SẮP TỚI</div><h1>Dự báo giao thông<span>.</span></h1><p>Chọn tuyến đường và giờ dự định đi để tránh những khung giờ thường ùn tắc.</p></div>{manager&&<button className="button small" onClick={()=>setManage(true)}><Settings2 size={16}/>Quản lý dữ liệu</button>}</div>
    <form className="card outlook-form" onSubmit={e=>{e.preventDefault();view();}}>
      <label className="field">Tuyến đường<select aria-label="Tuyến đường dự báo" value={road} onChange={e=>setRoad(e.target.value)}>{segments.filter(s=>s.active&&(dataMode!=='demo'||demo?.segment_ids.includes(s.id))).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label className="field">Ngày dự định đi<input aria-label="Ngày dự định đi" type="date" required value={day} min={localDay()} max={localDay(7)} onChange={e=>setDay(e.target.value)}/></label>
      <label className="field">Giờ khởi hành<select aria-label="Giờ dự định đi" value={hour} onChange={e=>setHour(Number(e.target.value))}>{Array.from({length:24},(_,h)=><option key={h} value={h}>{hourText(h)}</option>)}</select></label>
      <button className="button primary" disabled={loading||!ready}>{loading?<Spinner/>:<CalendarDays size={17}/>}Xem dự báo</button>
    </form>
    {!ready?<DemoSetup demo={demo} user={user} onUpdated={onUpdated}/>:<>
      {error&&<Notice kind="error">{error}</Notice>}{edited&&result&&<Notice>Thông tin đã thay đổi. Bấm “Xem dự báo” để cập nhật kết quả.</Notice>}
      {loading?<div className="loading-page"><Spinner/><p>Đang xem lại lịch sử và dự tính tình hình…</p></div>:result&&<>
        <section className={`card outlook-summary ${result.selected.label}`}><div><span className="eyebrow">{dateLabel} · {hourText(result.hour)}–{hourText(result.hour+1)}</span><h2>{result.segment_name}</h2><strong className="outlook-state">{result.selected.text}</strong><p>{result.explanation}</p><p className="outlook-advice">{result.advice}</p></div><div className="outlook-history"><CalendarDays size={24}/><b>{result.history_days}</b><span>ngày lịch sử đã xem xét</span></div></section>
        {result.avoid_windows.length>0&&<section className="card outlook-windows"><div><h2>Khung giờ nên cân nhắc tránh</h2><p>Các khoảng thường đông xe trên tuyến trong ngày đã chọn.</p></div><div>{result.avoid_windows.map(w=><span key={w.start_hour}>{hourText(w.start_hour)}–{hourText(w.end_hour)}</span>)}</div></section>}
        <section className="card outlook-day"><div className="section-title"><Clock3 size={18}/><h2>Dự kiến theo từng giờ</h2></div><p className="muted">Bấm vào một giờ để xem chi tiết. Xanh: thông thoáng · vàng: đông xe · đỏ: dễ ùn tắc.</p><div className="outlook-hour-scroll"><div className="outlook-hours">{result.hourly.map(row=><button type="button" key={row.hour} aria-label={`Xem ${hourText(row.hour)}: ${row.text}`} className={`${row.label} ${row.hour===result.hour?'selected':''}`} onClick={()=>view(row.hour)}><i/><b>{hourText(row.hour)}</b></button>)}</div></div></section>
        {result.alternatives.length>0&&<section className="outlook-alternatives"><h2>Bạn có thể cân nhắc những giờ này</h2><div>{result.alternatives.map(row=><button type="button" className="card" key={row.hour} onClick={()=>view(row.hour)}><Clock3 size={20}/><strong>{hourText(row.hour)}</strong><span className={row.label}>{row.text}</span><ArrowRight size={16}/></button>)}</div></section>}
        <section className="card forecast-next"><div><h2>Lên kế hoạch cho hành trình</h2><p>Xem các ngày trước hoặc tìm đường phù hợp với giờ khởi hành này.</p></div><div className="button-row"><button className="button" onClick={()=>onHistory(result.segment_id)}>Xem lịch sử tuyến đường</button><button className="button primary" onClick={()=>onFindRoute(new Date(`${result.date}T${String(result.hour).padStart(2,'0')}:00:00+07:00`).toISOString())}>Tìm tuyến đường<ArrowRight size={16}/></button></div></section>
        <p className="data-footnote">{result.is_demo?'Ước tính từ lịch sử minh họa. ':''}Tình hình thực tế có thể thay đổi do thời tiết, sự cố hoặc sự kiện. Nên kiểm tra lại trước khi đi.</p>
      </>}
    </>}
  </>;
}
