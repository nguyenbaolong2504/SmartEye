import { lazy, Suspense, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, BrainCircuit, Clock3, Settings2 } from 'lucide-react';
import { api } from './api';
import { Notice,Spinner } from './components';
import DemoSetup from './DemoSetup';
import { type Segment,type User,type DataMode,type DemoStatus,dateTime } from './types';
const Management=lazy(()=>import('./ForecastManagement'));
const labels:Record<string,string>={FREE:'Thông thoáng',SLOW:'Đông, di chuyển chậm',JAM:'Ùn tắc'};
type Prediction={state:string;message:string;issue_at?:string;is_demo?:boolean;current?:{label:string;speed_kmh:number;count:number};predictions:{horizon_minutes:number;predicted_at:string;label:string;model:string}[]};
export default function ForecastPage({segments,user,dataMode,demo,onLogin,onHistory,onUpdated}:{segments:Segment[];user:User|null;dataMode:DataMode;demo:DemoStatus|null;onLogin:()=>void;onHistory:()=>void;onUpdated:()=>void}){
  const[road,setRoad]=useState(String(segments.find(s=>s.name==='Hoàng Quốc Việt')?.id||segments.find(s=>s.active)?.id||''));
  const[scenario,setScenario]=useState('now');
  const[prediction,setPrediction]=useState<Prediction|null>(null);const[error,setError]=useState('');const[loading,setLoading]=useState(false);const[tick,setTick]=useState(0);const[manage,setManage]=useState(false);
  const manager=user?.role==='admin'||user?.role==='analyst';
  useEffect(()=>{let current=true;if(!road||dataMode==='demo'&&!demo?.ready){setPrediction(null);return;}
    setPrediction(null);setLoading(true);setError('');
    const day=new Date(Date.now()+7*3600000-86400000).toISOString().slice(0,10);
    const issue=dataMode==='demo'&&scenario!=='now'?'&issue_at='+encodeURIComponent(`${day}T${scenario==='morning'?'07:30':'17:30'}:00+07:00`):'';
    api<Prediction>(dataMode==='demo'?`/demo/predict?segment_id=${road}${issue}`:`/forecast/predict?segment_id=${road}&target=congestion`).then(value=>{if(current)setPrediction(value);}).catch(e=>{if(current)setError(e.message);}).finally(()=>{if(current)setLoading(false);});
    return()=>{current=false;};
  },[road,dataMode,demo?.ready,tick,scenario]);
  useEffect(()=>{const timer=setInterval(()=>{if(!document.hidden)setTick(t=>t+1);},60000);return()=>clearInterval(timer);},[]);
  if(manage&&manager)return <><button className="text-button back-link" onClick={()=>setManage(false)}><ArrowLeft size={16}/>Quay lại dự báo</button><Suspense fallback={<Spinner/>}><Management segments={segments} user={user} onLogin={onLogin} onUpload={()=>setManage(false)}/></Suspense></>;
  const results=prediction?.predictions||[];const current=prediction?.current;
  return <><div className="page-heading"><div><div className="eyebrow">CHỦ ĐỘNG TRƯỚC GIỜ XUẤT PHÁT</div><h1>Dự báo giao thông<span>.</span></h1><p>Tình trạng dự kiến sau 15 và 30 phút trên tuyến bạn quan tâm.</p></div>{manager&&<button className="button small" onClick={()=>setManage(true)}><Settings2 size={16}/>Dữ liệu & mô hình</button>}</div>
    {dataMode==='demo'&&!demo?.ready?<DemoSetup demo={demo} user={user} onUpdated={onUpdated}/>:<>
    <section className="card simple-forecast-controls"><label className="field">Tuyến đường<select aria-label="Tuyến đường dự báo" value={road} onChange={e=>setRoad(e.target.value)}>{segments.filter(s=>s.active&&(dataMode!=='demo'||demo?.segment_ids.includes(s.id))).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>{dataMode==='demo'&&<label className="field">Thời điểm chạy thử<select aria-label="Thời điểm chạy thử" value={scenario} onChange={e=>setScenario(e.target.value)}><option value="now">Hiện tại</option><option value="morning">07:30 hôm qua</option><option value="evening">17:30 hôm qua</option></select></label>}<button className="button" onClick={()=>setTick(t=>t+1)} disabled={loading}>Làm mới</button></section>
    {error&&<Notice kind="error">{error}</Notice>}
    <div className="forecast-context"><div><span className="eyebrow">TUYẾN ĐANG XEM</span><h2>{segments.find(s=>String(s.id)===road)?.name}</h2><p>{prediction?.issue_at?`Dữ liệu đến ${dateTime(prediction.issue_at)} · UTC+7`:'Dự báo theo lịch sử gần nhất của tuyến đường.'}</p></div>{dataMode==='demo'&&<span className="source-pill">Mô phỏng · XGBoost</span>}</div>
    {loading?<div className="loading-page"><Spinner/><p>Đang tính dự báo…</p></div>:prediction?.state==='ready'?<>
      <div className="prediction-timeline">{current&&<article className={`card current-condition ${current.label}`}><span className="eyebrow">{scenario==='now'?'HIỆN TẠI · MÔ PHỎNG':'TẠI MỐC CHẠY THỬ · MÔ PHỎNG'}</span><h2>{labels[current.label]}</h2><p>Vận tốc mẫu <b>{current.speed_kmh} km/h</b></p></article>}{results.map(result=><article key={result.horizon_minutes} className={`card forecast-card ${result.label}`}><div className="forecast-card-top"><Clock3 size={20}/><span>Sau {result.horizon_minutes} phút</span></div><h2>{labels[result.label]||result.label}</h2><p>{dateTime(result.predicted_at)}</p><div className="forecast-model"><BrainCircuit size={15}/>{result.model}<span>{dataMode==='demo'?'Huấn luyện từ lịch sử mô phỏng':'Mô hình đã kích hoạt'}</span></div></article>)}</div>
      <section className="card forecast-next"><div><h2>Chọn thời điểm và lộ trình phù hợp</h2><p>Xem các khung giờ thường đông xe trước khi lên kế hoạch di chuyển.</p></div><button className="button primary" onClick={onHistory}>Xem thống kê ngày / tháng<ArrowRight size={16}/></button></section>
    </>:!error&&<section className="card demo-setup"><h2>Chưa đủ dữ liệu quan sát để dự báo</h2><p>{prediction?.message||'Chọn chế độ mô phỏng ở đầu trang để chạy thử ngay.'}</p>{manager&&<button className="button" onClick={()=>setManage(true)}>Nhập lịch sử bằng CSV</button>}</section>}
    <p className="micro">{dataMode==='demo'?'XGBoost học từ dữ liệu tổng hợp có giờ cao điểm và biến động theo ngày. Kết quả chỉ minh họa quy trình dự báo, chưa chứng minh độ chính xác trên đường thực tế.':'Tình trạng dự báo cần mô hình đã kiểm thử và lịch sử quan sát đủ mới; mật độ cao riêng lẻ chưa đủ để kết luận ùn tắc.'}</p>
    </>}
  </>;
}
