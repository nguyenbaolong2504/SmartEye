import {useState} from 'react';
import {Activity,ArrowRight,ArrowUpRight,BrainCircuit,Camera,ChartNoAxesCombined,ChevronRight,Clock3,MapPin,Navigation,Route} from 'lucide-react';
import {type Segment,type DataMode,type User,dateTime} from './types';
import PublicWarnings from './PublicWarnings';
import {can} from './permissions';
import './overview.css';

type Destination='monitor'|'forecast'|'routes'|'alerts'|'cameras';
const densityText={LOW:'Ít xe',NORMAL:'Vừa phải',HIGH:'Đông xe'};
const priority={HIGH:0,NORMAL:1,LOW:2,unknown:3};

export default function OverviewPage({user,segments,onNavigate,onRoad,dataMode}:{
  user:User|null;segments:Segment[];onNavigate:(tab:Destination)=>void;onRoad:(id:number)=>void;dataMode:DataMode;
}){
  const [area,setArea]=useState('Hà Nội');
  const roads=segments.filter(road=>road.active);
  const areaOf=(road:Segment)=>road.area?.trim()||'Chưa phân vùng';
  const areas=[...new Set(roads.map(areaOf))].sort((a,b)=>a.localeCompare(b,'vi'));
  const selectedArea=areas.includes(area)?area:areas[0]||'';
  const localRoads=roads.filter(road=>areaOf(road)===selectedArea).sort((a,b)=>
    priority[a.observation?.density||'unknown']-priority[b.observation?.density||'unknown']||a.name.localeCompare(b.name,'vi'));
  const shortcuts=[
    {permission:'cameras.view',tab:'cameras' as const,icon:Camera,tone:'green',title:'Nhìn đường trước khi đi',description:'Xem video và phân tích tình hình tại camera.',action:'Xem camera'},
    {permission:'forecast.view',tab:'forecast' as const,icon:BrainCircuit,tone:'blue',title:'Chọn giờ đi phù hợp',description:'Tham khảo giao thông vào ngày và giờ bạn dự định.',action:'Xem dự báo'},
    {permission:'traffic.view',tab:'monitor' as const,icon:ChartNoAxesCombined,tone:'amber',title:'Hiểu nhịp giao thông',description:'Xem những khung giờ thường đông xe trên từng tuyến.',action:'Xem thống kê'},
  ].filter(item=>can(user,item.permission));
  return <div className="home-page">
    <div className="home-topline"><span><span className="home-live-dot"/>Cùng bạn trên mọi hành trình</span><time dateTime={new Date().toISOString().slice(0,10)}>{new Date().toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',weekday:'long',day:'2-digit',month:'2-digit',year:'numeric'})}</time></div>
    <section className="home-hero" aria-labelledby="home-heading">
      <div className="home-hero-copy"><div className="home-eyebrow"><Route size={15}/>DI CHUYỂN THÔNG MINH HƠN</div><h1 id="home-heading">Hiểu đường đi.<br/><span>Chủ động giờ đến.</span></h1><p>Một chút chuẩn bị, một hành trình nhẹ nhàng hơn. Xem đường, chọn giờ và tìm lối đi phù hợp với bạn.</p>
        <div className="home-hero-actions">{can(user,'routes.search')&&<button className="button home-primary" onClick={()=>onNavigate('routes')}><Navigation size={17}/>Tìm đường phù hợp<ArrowRight size={17}/></button>}{can(user,'forecast.view')&&<button className="home-secondary" onClick={()=>onNavigate('forecast')}>Xem dự báo trước khi đi<ArrowUpRight size={16}/></button>}</div>
      </div>
      <div className="home-journey-art" aria-hidden="true"><div className="home-art-label"><span><Navigation size={14}/></span>Hành trình của bạn</div>
        <svg viewBox="0 0 420 260" fill="none"><g stroke="#a8d6cb" strokeOpacity=".14" strokeWidth="13" strokeLinecap="round"><path d="M-30 48H450M-30 127H450M-30 221H450M66-30V290M184-30V290M318-30V290"/><path d="M-15 264L249-12M214 284L442 52"/></g><g fill="#bde3d7" fillOpacity=".08"><rect x="85" y="65" width="80" height="43" rx="8"/><rect x="204" y="65" width="95" height="43" rx="8"/><rect x="85" y="146" width="80" height="56" rx="8"/><rect x="337" y="146" width="65" height="56" rx="8"/></g><path d="M66 48H184V127H318V221" stroke="#0a3f3c" strokeWidth="23" strokeLinecap="round" strokeLinejoin="round"/><path d="M66 48H184V127H318V221" stroke="#83dfb7" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round"/><path d="M66 48H184V127H318V221" stroke="#c3f7db" strokeWidth="2" strokeDasharray="2 10" strokeLinecap="round"/><circle cx="66" cy="48" r="19" fill="#d6f8e5" fillOpacity=".12"/><circle cx="66" cy="48" r="9" fill="#eefcf5"/><circle cx="66" cy="48" r="4" fill="#178775"/><circle cx="318" cy="221" r="22" fill="#83dfb7" fillOpacity=".17"/><circle cx="318" cy="221" r="12" fill="#d6f8e5"/><path d="m313 221 4 4 7-8" stroke="#126458" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
        <div className="home-art-caption"><span className="home-art-icon"><MapPin size={17}/></span><div><b>Đi đúng hướng. Chọn đúng giờ.</b><span>Sẵn sàng cho chuyến đi tiếp theo.</span></div></div>
      </div>
    </section>
    {shortcuts.length>0&&<section className="home-shortcuts" aria-label="Tiện ích cho hành trình">{shortcuts.map(({tab,icon:Icon,tone,title,description,action})=><button className={`home-shortcut ${tone}`} key={tab} type="button" aria-label={action} onClick={()=>onNavigate(tab)}><span className="home-shortcut-icon"><Icon size={23}/></span><div className="home-shortcut-copy"><h2>{title}</h2><p>{description}</p><span className="home-shortcut-action">{action}<ArrowUpRight size={15}/></span></div></button>)}</section>}
    <div className="home-information-grid">
      {can(user,'traffic.view')&&<section className="home-road-panel" aria-label="Tình hình các tuyến đường">
        <div className="home-panel-heading"><div><span className="home-section-eyebrow">QUAN SÁT GIAO THÔNG</span><h2>Tình hình các tuyến đường</h2></div><label className="home-area"><MapPin size={15}/><span className="sr-only">Khu vực theo dõi</span><select aria-label="Khu vực theo dõi" value={selectedArea} disabled={!areas.length} onChange={event=>setArea(event.target.value)}>{areas.length?areas.map(value=><option key={value}>{value}</option>):<option value="">Chưa có khu vực</option>}</select></label></div>
        <div className="home-road-list">{localRoads.length?localRoads.slice(0,5).map(road=><button type="button" className="home-road-row" key={road.id} aria-label={`Xem tuyến ${road.name}`} onClick={()=>onRoad(road.id)}><span className={`home-road-symbol ${road.observation?.density||'unknown'}`}><Route size={17}/></span><span className="home-road-name"><b>{road.name}</b><small>{road.observation?`Ghi nhận ${dateTime(road.observation.observed_at)}`:'Chưa có theo dõi mới'}</small></span><span className={`home-road-state ${road.observation?.density||'unknown'}`}><i/>{road.observation?densityText[road.observation.density]:'Chưa có dữ liệu'}</span><ChevronRight size={15} className="home-road-chevron"/></button>):<div className="home-roads-empty"><Activity size={25}/><b>Chưa có tuyến đường để hiển thị</b><p>Các tuyến được theo dõi sẽ xuất hiện tại đây.</p></div>}</div>
        <div className="home-road-footer"><span>Mật độ phương tiện trên các tuyến đang theo dõi</span><button type="button" className="text-button" onClick={()=>onNavigate('monitor')}>Xem tất cả<ArrowRight size={14}/></button></div>
      </section>}
      {can(user,'warnings.view')&&<aside className="home-alerts" aria-label="Cảnh báo mới"><PublicWarnings segments={segments} compact onAll={()=>onNavigate('alerts')}/><div className="home-tip"><span><Clock3 size={19}/></span><p><b>Trước khi xuất phát</b>Xem camera và dự báo gần giờ đi để có thêm thông tin cho hành trình.</p></div></aside>}
    </div>
    {dataMode==='demo'&&<p className="home-data-note">Dữ liệu minh họa phục vụ trải nghiệm các tính năng.</p>}
  </div>;
}
