import { useEffect, useState } from 'react';
import { Camera, Video, Play, CalendarDays, Clock3, ArrowUpRight, Search, Activity, BarChart3, RefreshCw, MapPin } from 'lucide-react';
import { api } from './api';
import { DensityBadge, Empty, Modal, Notice, Spinner } from './components';
import { type MonitorCamera, type HistoryReport, type TrafficStats, type Segment, densityColor, dateTime } from './types';
import './monitor.css';

const today = () => new Date(Date.now()+7*3600000).toISOString().slice(0,10);
const normalize = (value:string) => value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d');
const percent = (value:number|null) => value===null?'—':`${Math.round(value*100)}%`;
const statsColor = (s:TrafficStats) => s.average_score===null?'#e8edef':s.high_share!==null&&s.high_share>=.5?densityColor.HIGH:s.low_share!==null&&s.low_share>=.5?densityColor.LOW:densityColor.NORMAL;
const slotTitle = (s:TrafficStats) => s.average_score===null?'Chưa có dữ liệu':`Chỉ số ${Math.round(s.average_score*100)}/100 · Mật độ cao ${percent(s.high_share)} số ô có mẫu · ${s.slot_count} ô / ${s.observed_days} ngày`;

function CameraPicture({camera,expanded=false}:{camera:MonitorCamera;expanded?:boolean}) {
  const [failed,setFailed]=useState(false);
  const [imageFailed,setImageFailed]=useState(false);
  useEffect(()=>{setFailed(false);setImageFailed(false);},[camera.image_url,camera.video_url,expanded]);
  if(expanded&&camera.video_url&&!failed) return <video className="monitor-player" src={camera.video_url} poster={camera.image_url||undefined} controls autoPlay muted playsInline onError={()=>setFailed(true)}/>;
  if(camera.image_url&&!imageFailed) return <><img className="monitor-player" src={camera.image_url} alt={`Ảnh đã công bố từ ${camera.name}`} onError={()=>setImageFailed(true)}/>{expanded&&failed&&<Notice>Codec này chưa phát được trên trình duyệt. Đang hiển thị ảnh kết quả; nên dùng MP4 H.264 hoặc WebM.</Notice>}</>;
  return <div className="monitor-no-picture"><Camera size={32}/><span>Chưa có hình ảnh được chia sẻ</span><small>Tải video, phân tích và cho phép công bố để xem tại đây.</small></div>;
}

export default function TrafficMonitor({segments,onUpload,onFindRoute}:{segments:Segment[];onUpload:(id:number)=>void;onFindRoute:()=>void}) {
  const [tab,setTab]=useState<'cameras'|'history'>('cameras');
  const [cameras,setCameras]=useState<MonitorCamera[]>([]);
  const [boardError,setBoardError]=useState('');
  const [loading,setLoading]=useState(true);
  const [search,setSearch]=useState('');
  const [filter,setFilter]=useState('all');
  const [opened,setOpened]=useState<MonitorCamera|null>(null);
  const [road,setRoad]=useState(String(segments.find(s=>s.active)?.id||''));
  const [period,setPeriod]=useState<'day'|'month'>('day');
  const [value,setValue]=useState(today());
  const [report,setReport]=useState<HistoryReport|null>(null);
  const [reportError,setReportError]=useState('');
  const [reportLoading,setReportLoading]=useState(false);
  async function refresh(){
    try {const data=await api<{cameras:MonitorCamera[]}>('/monitor/cameras');setCameras(data.cameras);setBoardError('');}
    catch(e){setBoardError((e as Error).message);}finally{setLoading(false);}
  }
  useEffect(()=>{refresh();const timer=setInterval(refresh,30000);return()=>clearInterval(timer);},[]);
  useEffect(()=>{
    if(tab!=='history'||!road||!value)return;
    let stale=false;setReportLoading(true);setReportError('');setReport(null);
    api<HistoryReport>(`/traffic/history?segment_id=${road}&period=${period}&value=${encodeURIComponent(value)}`)
      .then(data=>{if(!stale)setReport(data);}).catch(e=>{if(!stale)setReportError(e.message);})
      .finally(()=>{if(!stale)setReportLoading(false);});
    return()=>{stale=true;};
  },[tab,road,period,value]);
  const visible=cameras.filter(c=>normalize(`${c.name} ${c.segment_name}`).includes(normalize(search))&&(filter==='all'||(filter==='high'?c.density==='HIGH':filter==='current'?c.state==='current':c.state!=='current')));
  const current=cameras.filter(c=>c.state==='current');
  function history(segmentId:number){setRoad(String(segmentId));setTab('history');}
  function switchPeriod(next:'day'|'month'){
    setPeriod(next);setValue(next==='month'?value.slice(0,7):value.slice(0,7)===today().slice(0,7)?today():`${value.slice(0,7)}-01`);
  }
  return <>
    <div className="page-heading"><div><div className="eyebrow">QUAN SÁT ĐƯỜNG · HIỂU THÓI QUEN GIAO THÔNG</div><h1>Camera & giao thông<span>.</span></h1><p>Xem hình ảnh từng đường, trạng thái mới nhất và các khung giờ thường có mật độ cao.</p></div><span className="mode-badge"><Video size={16}/>Nguồn video tải lên</span></div>
    <div className="monitor-kpis"><div><Camera size={19}/><span>Camera hoạt động<strong>{cameras.filter(c=>c.active).length}</strong></span></div><div><Activity size={19}/><span>Có dữ liệu hiện tại<strong>{current.length}</strong></span></div><div><span className="monitor-high-dot"/><span>Camera mật độ cao<strong>{current.filter(c=>c.density==='HIGH').length}</strong></span></div><div><Clock3 size={19}/><span>Cần bổ sung dữ liệu<strong>{cameras.filter(c=>c.active&&c.state!=='current').length}</strong></span></div></div>
    <div className="tabs"><button className={tab==='cameras'?'active':''} onClick={()=>setTab('cameras')}><Camera size={17}/>Camera ngoài đường</button><button className={tab==='history'?'active':''} onClick={()=>setTab('history')}><BarChart3 size={17}/>Thống kê từng đường</button></div>
    {boardError&&<Notice kind="error">{boardError}</Notice>}
    {tab==='cameras'?<>
      <div className="monitor-toolbar"><label className="monitor-search"><Search size={17}/><input aria-label="Tìm camera hoặc đường" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Tìm camera, tên đường…"/></label><select aria-label="Lọc tình trạng camera" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">Tất cả tình trạng</option><option value="current">Có dữ liệu hiện tại</option><option value="high">Mật độ cao hiện tại</option><option value="missing">Chưa có / dữ liệu cũ</option></select><button className="button small" onClick={refresh}><RefreshCw size={15}/>Làm mới</button></div>
      <div className="monitor-layout"><div>
        {loading?<div className="empty"><Spinner/>Đang tải camera…</div>:visible.length?<div className="monitor-grid">{visible.map(camera=><article className="monitor-camera card" key={camera.id}>
          <button className="monitor-picture" onClick={()=>setOpened(camera)} aria-label={`Xem camera ${camera.name}`}><CameraPicture camera={camera}/><span className="monitor-source"><Video size={12}/>{camera.video_url?'Video đã công bố':camera.image_url?'Ảnh đã công bố':'Chưa có nguồn'}{camera.preview_at&&` · ${dateTime(camera.preview_at)}`}</span>{camera.image_url&&<span className="monitor-play"><Play size={20}/></span>}</button>
          <div className="monitor-camera-body"><div className="monitor-camera-title"><h3>{camera.name}</h3><DensityBadge value={camera.density}/></div><p className="monitor-road"><MapPin size={12}/>{camera.segment_name}{camera.is_demo&&<small>Minh họa</small>}</p>
            <div className="monitor-vehicles"><div><span>Ô tô / ảnh</span><strong>{camera.vehicle_counts.car??'—'}</strong></div><div><span>Xe máy / ảnh</span><strong>{camera.vehicle_counts.motorcycle??'—'}</strong></div><div><span>Tổng xe / ảnh</span><strong>{camera.count??'—'}</strong></div></div>
            <p className={`monitor-timestamp ${camera.state==='stale'?'is-stale':''}`}><Clock3 size={12}/>{camera.state==='inactive'?'Camera / đường đã ngừng':camera.observed_at?`${camera.state==='stale'?'Dữ liệu cũ · ':''}${dateTime(camera.observed_at)}`:'Chưa có quan sát được công bố'}</p>
            <div className="monitor-actions"><button className="text-button" onClick={()=>history(camera.segment_id)}>Thống kê ngày / tháng<ArrowUpRight size={14}/></button><button className="button small" disabled={!camera.active} onClick={()=>onUpload(camera.id)}><Video size={14}/>Tải video</button></div>
          </div></article>)}</div>:<section className="card"><Empty><h3>Chưa tìm thấy camera phù hợp.</h3><p>Thử tên đường khác hoặc thêm camera trong trang Quản trị.</p></Empty></section>}
        <p className="micro">Video và ảnh ở đây đã được cho phép chia sẻ. Thời điểm ghi hình được hiển thị riêng; video cũ không đại diện giao thông hiện tại. Số xe là hiện diện mỗi ảnh, chưa phải vận tốc hay lưu lượng xe đi qua.</p>
      </div><aside className="card monitor-road-list"><div className="section-title"><Activity size={17}/><h2>Tình trạng từng đường</h2></div>{segments.filter(s=>s.active).map(s=><button key={s.id} onClick={()=>history(s.id)}><span>{s.name}<small>{s.is_demo?'Mạng minh họa':s.observation?dateTime(s.observation.observed_at):'Chưa có dữ liệu'}</small></span><DensityBadge value={s.observation?.density||null}/></button>)}<button className="button primary full monitor-find-route" onClick={onFindRoute}>So sánh tuyến đường<ArrowUpRight size={15}/></button></aside></div>
    </>:<>
      <section className="card monitor-history-filter"><label className="field">Đường cần thống kê<select value={road} onChange={e=>setRoad(e.target.value)}>{segments.map(s=><option key={s.id} value={s.id}>{s.name}{s.active?'':' (đã ngừng)'}</option>)}</select></label><div className="monitor-period" aria-label="Khoảng thống kê"><button className={period==='day'?'active':''} onClick={()=>switchPeriod('day')}>Theo ngày</button><button className={period==='month'?'active':''} onClick={()=>switchPeriod('month')}>Theo tháng</button></div><label className="field">{period==='day'?'Ngày quan sát':'Tháng quan sát'}<input aria-label={period==='day'?'Ngày thống kê':'Tháng thống kê'} type={period==='day'?'date':'month'} value={value} max={period==='day'?today():today().slice(0,7)} onChange={e=>setValue(e.target.value)}/></label><span className="monitor-timezone"><CalendarDays size={15}/>Giờ Việt Nam · UTC+7</span></section>
      {reportError&&<Notice kind="error">{reportError}</Notice>}
      {reportLoading?<section className="card"><Empty><Spinner/><p>Đang tổng hợp lịch sử…</p></Empty></section>:report&&<>
        <div className="monitor-history-heading"><div><h2>{report.segment_name}</h2><p>{period==='day'?`Diễn biến ngày ${value}`:`Tổng hợp tháng ${value}`} · {report.is_demo?'Đoạn đường minh họa':'Đoạn đường khảo sát'}</p></div><button className="button" onClick={onFindRoute}>Tìm tuyến phù hợp<ArrowUpRight size={15}/></button></div>
        <div className="monitor-kpis"><div><BarChart3 size={18}/><span>Mẫu quan sát<strong>{report.summary.raw_samples}</strong></span></div><div><CalendarDays size={18}/><span>Ngày có dữ liệu<strong>{report.summary.observed_days}</strong></span></div><div><Clock3 size={18}/><span>Ô 5 phút có mẫu<strong>{report.summary.coverage_percent}<small>%</small></strong></span></div><div><Activity size={18}/><span>Mật độ cao trong ô có mẫu<strong>{percent(report.summary.high_share)}</strong></span></div></div>
        {!report.summary.slot_count?<Notice>Đường này chưa có dữ liệu trong khoảng đã chọn. Phân tích video có thời điểm quay, sau đó dùng “Lưu vào lịch sử”. Các giờ trống được giữ là chưa có dữ liệu.</Notice>:<Notice>{report.summary.slot_count} ô 5 phút có mẫu. Các tỷ lệ chỉ phản ánh phần thời gian đã có dữ liệu; độ phủ thấp chưa đủ để kết luận tình trạng cả ngày hoặc cả tháng.</Notice>}
        <div className="monitor-analysis-layout"><section className="card monitor-chart-card"><div className="section-title"><BarChart3 size={18}/><h2>Mật độ theo khung giờ</h2><span className="muted">Chỉ số / 100</span></div><div className="monitor-hour-chart" role="img" aria-label="Biểu đồ chỉ số mật độ theo 24 giờ"><div className="monitor-chart-scale"><span>100</span><span>50</span><span>0</span></div><div className="monitor-hour-bars">{report.hourly.map(h=><div key={h.hour} className="monitor-hour-column"><div className="monitor-bar-space"><span title={`${String(h.hour).padStart(2,'0')}:00–${String(h.hour+1).padStart(2,'0')}:00 · ${slotTitle(h)}`} style={{height:h.average_score===null?'4px':`${Math.max(4,h.average_score*100)}%`,background:statsColor(h)}}/></div><small>{h.hour.toString().padStart(2,'0')}</small></div>)}</div></div><div className="monitor-legend"><span><i style={{background:densityColor.LOW}}/>Thấp</span><span><i style={{background:densityColor.NORMAL}}/>Bình thường</span><span><i style={{background:densityColor.HIGH}}/>Cao</span><span><i style={{background:'#e8edef'}}/>Chưa có dữ liệu</span></div><p className="micro">Mỗi giờ chỉ tổng hợp các ô có mẫu. Màu theo mức mật độ chiếm đa số; chiều cao theo chỉ số trung bình, không phải xác suất tắc đường.</p></section>
        <section className="card monitor-peaks"><div className="section-title"><Clock3 size={18}/><h2>{period==='month'?'Khung giờ thường mật độ cao':'Giờ có mật độ cao'}</h2></div>{period==='month'?(report.peak_hours.length?report.peak_hours.map(h=><div className="monitor-peak" key={h.hour}><strong>{String(h.hour).padStart(2,'0')}:00–{String(h.hour+1).padStart(2,'0')}:00</strong><span>{percent(h.high_share)} ô có mẫu ở mức cao</span><small>{h.observed_days} ngày · {h.slot_count} ô quan sát</small></div>):<p className="muted">Chưa có khung giờ mật độ cao đủ bằng chứng để kết luận lặp lại.</p>):report.hourly.filter(h=>h.high_share!==null&&h.high_share>=.5).map(h=><div className="monitor-peak" key={h.hour}><strong>{String(h.hour).padStart(2,'0')}:00–{String(h.hour+1).padStart(2,'0')}:00</strong><span>{percent(h.high_share)} ô có mẫu ở mức cao</span><small>{h.slot_count} ô quan sát trong ngày</small></div>)}{period==='day'&&!report.hourly.some(h=>h.high_share!==null&&h.high_share>=.5)&&<p className="muted">Chưa ghi nhận giờ có đa số mẫu mật độ cao trong ngày.</p>}<p className="micro">{report.pattern_requirement}</p></section></div>
        {period==='month'&&<section className="card monitor-heatmap-card"><div className="section-title"><CalendarDays size={18}/><h2>Bản đồ nhiệt ngày × giờ</h2></div><p className="micro">Chọn một ô để xem ngày đó. Ô xám chưa có dữ liệu.</p><div className="monitor-heatmap-scroll"><div className="monitor-heatmap"><span className="monitor-heatmap-label">Ngày / giờ</span>{Array.from({length:24},(_,h)=><span className="monitor-heatmap-hour" key={h}>{h.toString().padStart(2,'0')}</span>)}{report.daily.map(d=><HeatmapRow key={d.date} date={d.date} report={report} onDay={()=>{setPeriod('day');setValue(d.date);}}/>)}</div></div><p className="micro">{report.method}</p></section>}
      </>}
    </>}
    {opened&&<Modal title={opened.name} onClose={()=>setOpened(null)}><CameraPicture camera={opened} expanded/><p className="monitor-road"><MapPin size={14}/>{opened.segment_name}</p><DensityBadge value={opened.density}/><p className="micro">Ảnh/video ghi hình {opened.preview_at?dateTime(opened.preview_at):'chưa có'}. Nguồn: video tải lên đã được công bố; không phải luồng camera trực tiếp.</p><div className="monitor-actions"><button className="button" onClick={()=>{history(opened.segment_id);setOpened(null);}}>Xem thống kê đường</button><button className="button primary" onClick={()=>{onUpload(opened.id);setOpened(null);}}>Phân tích video mới</button></div></Modal>}
  </>;
}

function HeatmapRow({date,report,onDay}:{date:string;report:HistoryReport;onDay:()=>void}) {
  const future=date>today();
  return <><button className="monitor-heatmap-label" disabled={future} onClick={onDay}>{date.slice(8,10)}/{date.slice(5,7)}</button>{report.heatmap.filter(c=>c.date===date).map(c=><button key={c.hour} className="monitor-heat-cell" disabled={future} aria-label={`${date} ${c.hour} giờ: ${slotTitle(c)}`} title={`${date} · ${c.hour}:00 · ${future?'Chưa đến ngày':slotTitle(c)}`} style={{background:statsColor(c),opacity:c.average_score===null?1:.4+c.average_score*.6}} onClick={onDay}/>)}</>;
}
