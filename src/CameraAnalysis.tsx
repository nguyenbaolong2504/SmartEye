import {useEffect} from 'react';
import {Bike,Car,Clock3,ExternalLink,Truck} from 'lucide-react';
import {Notice,Spinner} from './components';
import {useRemote} from './business';
import type {Density} from './types';

type Sample={second:number;count:number;score:number;occupancy:number;density:Density;vehicle_counts:{car:number;motorcycle:number;bus:number;truck:number}};
type Forecast={horizon_minutes:number;label:Density};
type Analysis={state:string;progress:number;message:string;is_demo:boolean;samples?:Sample[];duration_seconds?:number;high_threshold?:number;
  average_count?:number;peak_count?:number;frame_url?:string;method?:string;
  source?:{title:string;author:string;page_url:string;license:string;license_url:string;published_date:string;location_note:string};
  forecast?:{is_demo:boolean;reference_at?:string;message:string;timeline:{second:number;predictions:Forecast[]}[]}|null};
const empty:Analysis={state:'queued',progress:0,message:'Đang tải kết quả phân tích.',is_demo:true};
const densityText:Record<Density,string>={LOW:'Thấp',NORMAL:'Vừa',HIGH:'Cao'};
const timeText=(second:number)=>`${String(Math.floor(second/60)).padStart(2,'0')}:${String(Math.floor(second%60)).padStart(2,'0')}`;

export default function CameraAnalysis({url,second,onSeek}:{url:string;second:number;onSeek:(second:number)=>void}){
  const view=useRemote<Analysis>(url.replace(/^\/api(?=\/)/,''),empty);
  const data=view.data;
  useEffect(()=>{
    if(!['queued','processing'].includes(data.state))return;
    const timer=setInterval(view.reload,2500);
    return()=>clearInterval(timer);
  },[data.state,view.reload]);
  if(view.error)return <Notice kind="error">{view.error}<button className="text-button" onClick={view.reload}>Thử tải kết quả</button></Notice>;
  if(data.state!=='completed')return <section className="camera-analysis"><h3>Phân tích video</h3><p>{['queued','processing'].includes(data.state)&&<Spinner/>} {data.message}</p></section>;
  const samples=data.samples||[];
  const sample=[...samples].reverse().find(row=>row.second<=Math.floor(second))||samples[0];
  if(!sample)return null;
  const predictions=data.forecast?.timeline.find(row=>row.second===sample.second)?.predictions||[];
  const high=data.high_threshold??.6;
  const level=sample.density==='HIGH'&&sample.score>=high+(1-high)*.65?'Rất cao':densityText[sample.density];
  return <section className="camera-analysis" aria-label="Phân tích video camera">
    <div className="camera-analysis-heading"><div><h3>Mật độ trong video</h3><p>Tại giây {timeText(sample.second)} · Kéo thanh phát để xem thời điểm khác</p></div><strong className={`camera-density ${sample.density}`}>{level}</strong></div>
    <div className="camera-counts"><article><b>{sample.count}</b><span>Tổng xe / khung hình</span></article><article><Car size={17}/><b>{sample.vehicle_counts.car}</b><span>Ô tô</span></article><article><Bike size={17}/><b>{sample.vehicle_counts.motorcycle}</b><span>Xe máy</span></article><article><Truck size={17}/><b>{sample.vehicle_counts.bus+sample.vehicle_counts.truck}</b><span>Xe buýt, xe tải</span></article></div>
    <div className="camera-density-track"><span style={{width:`${Math.min(100,sample.score*100)}%`}}/></div>
    <div className="camera-video-timeline" aria-label="Mật độ theo thời gian video">{samples.map(row=><button key={row.second} type="button" className={`${row.density} ${row.second===sample.second?'selected':''}`} style={{height:`${12+row.score*44}px`}} aria-label={`Xem giây ${row.second}, mật độ ${densityText[row.density].toLowerCase()}`} title={`${timeText(row.second)} · ${row.count} xe`} onClick={()=>onSeek(row.second)}/>)}</div>
    <p className="micro">Video dài {timeText(data.duration_seconds||0)} · Trung bình {data.average_count} xe/khung hình · Nhiều nhất {data.peak_count} xe. Các xe có thể xuất hiện lại ở nhiều giây.</p>
    {data.forecast&&<div className="camera-forecast"><h3><Clock3 size={18}/>Dự báo mật độ chạy thử</h3><p>{data.forecast.message}</p>
      {predictions.length?<div className="camera-forecast-cards">{predictions.map(item=><article key={item.horizon_minutes} className={item.label}><span>Sau {item.horizon_minutes} phút</span><strong>{densityText[item.label]}</strong></article>)}</div>:<p>Chưa có dự báo cho thời điểm này.</p>}
      <p className="micro">Kết quả dùng lịch sử minh họa để chạy thử. Cần lịch sử camera thực tế để đánh giá độ chính xác trên tuyến đường.</p>
    </div>}
    <details className="camera-detection-details"><summary>Xem khung hình nhận diện và cách đánh giá</summary>
      {data.frame_url&&<><p className="micro">Khung hình tại giây đầu của video</p><img loading="lazy" src={data.frame_url} alt="Khung hình được đánh dấu xe bằng YOLO"/></>}
      <p>Mật độ dựa trên số xe và phần vùng quan sát có xe. Việc xác định ùn tắc cần thêm diễn biến di chuyển và lịch sử đã kiểm chứng.</p>
      <p className="micro">Nhận diện bằng {data.method}. Phần dự báo chạy thử dùng XGBoost, thay mẫu mới nhất bằng kết quả video trong ngữ cảnh 60 phút có lịch sử minh họa.</p>
    </details>
    {data.source&&<div className="camera-video-credit"><b>Video minh họa</b><p>{data.source.location_note}</p><p>{data.source.title} · {data.source.author} · Công bố {data.source.published_date}</p><div><a href={data.source.page_url} target="_blank" rel="noreferrer">Video gốc<ExternalLink size={12}/></a><a href={data.source.license_url} target="_blank" rel="noreferrer">{data.source.license}</a></div></div>}
  </section>;
}
