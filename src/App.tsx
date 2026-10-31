import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Navigation, Bookmark, Bell, Settings2, ChevronRight, Menu, X, Radio, MapPin, LogIn, Activity, LayoutDashboard, BrainCircuit } from 'lucide-react';
import { api } from './api';
import { AuthModal,ProfilePage } from './Auth';
import { Modal,Notice,Spinner } from './components';
import { type Place,type Segment,type Camera,type Config,type User,type Favorite,type DemoStatus,type DataMode } from './types';
const OverviewPage=lazy(()=>import('./OverviewPage'));
const RoutesPage=lazy(()=>import('./RoutesPage'));
const TrafficMonitor=lazy(()=>import('./TrafficMonitor'));
const ForecastPage=lazy(()=>import('./ForecastPage'));
const HistoryPage=lazy(()=>import('./WorkspacePages').then(m=>({default:m.HistoryPage})));
const AlertsPage=lazy(()=>import('./WorkspacePages').then(m=>({default:m.AlertsPage})));
const AdminPage=lazy(()=>import('./WorkspacePages').then(m=>({default:m.AdminPage})));
type Tab='overview'|'forecast'|'routes'|'monitor'|'history'|'alerts'|'admin'|'profile';
const navigation=[{id:'overview',label:'Tổng quan',icon:LayoutDashboard},{id:'monitor',label:'Tình trạng & thống kê',icon:Activity},{id:'forecast',label:'Dự báo giao thông',icon:BrainCircuit},{id:'routes',label:'Tìm tuyến đường',icon:Navigation},{id:'history',label:'Hành trình & dữ liệu',icon:Bookmark},{id:'alerts',label:'Cảnh báo giao thông',icon:Bell},{id:'admin',label:'Quản trị hệ thống',icon:Settings2}] as const;
type Bootstrap={places:Place[];segments:Segment[];cameras:Camera[];config:Config;user:User|null;demo:DemoStatus};
export default function App(){
  const[tab,setTab]=useState<Tab>(()=>{const view=location.hash.slice(1);return navigation.some(n=>n.id===view)?view as Tab:'overview';});
  const[dataMode,setDataMode]=useState<DataMode>('demo');
  const[places,setPlaces]=useState<Place[]>([]);const[segments,setSegments]=useState<Segment[]>([]);const[cameras,setCameras]=useState<Camera[]>([]);
  const[loadedMode,setLoadedMode]=useState<DataMode|null>(null);const[config,setConfig]=useState<Config|null>(null);const[demo,setDemo]=useState<DemoStatus|null>(null);const[user,setUser]=useState<User|null>(null);
  const[error,setError]=useState('');const[authOpen,setAuthOpen]=useState(Boolean(new URLSearchParams(location.search).get('reset')));const[mobileOpen,setMobileOpen]=useState(false);
  const[initialRoad,setInitialRoad]=useState<number>();const[initialDeparture,setInitialDeparture]=useState('');const[preset,setPreset]=useState<Favorite|null>(null);const[routeKey,setRouteKey]=useState(0);const[toast,setToast]=useState('');const[legal,setLegal]=useState(false);const version=useRef(0);
  const refresh=useCallback(()=>{
    const current=++version.current;
    api<Bootstrap>(`/bootstrap?data_mode=${dataMode}`).then(data=>{
      if(current!==version.current)return;
      setPlaces(data.places);setSegments(data.segments);setCameras(data.cameras);setConfig(data.config);setLoadedMode(dataMode);setUser(data.user);setDemo(data.demo);setError('');
      if(!data.demo.enabled&&dataMode==='demo')setDataMode('observed');
    }).catch(e=>{if(current===version.current)setError(e.message);});
  },[dataMode]);
  useEffect(()=>{refresh();return()=>{version.current++;};},[refresh]);
  useEffect(()=>{const interval=setInterval(()=>{if(!document.hidden)refresh();},demo?.enabled&&!demo.ready?5000:30000);return()=>clearInterval(interval);},[refresh,demo?.ready,demo?.enabled]);
  useEffect(()=>{const changed=()=>{const view=location.hash.slice(1);if(navigation.some(n=>n.id===view)||view==='profile')setTab(view as Tab);else{setTab('overview');location.hash='overview';}setMobileOpen(false);};window.addEventListener('hashchange',changed);return()=>window.removeEventListener('hashchange',changed);},[]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(''),5000);return()=>clearTimeout(timer);},[toast]);
  function navigate(id:Tab){setTab(id);location.hash=id;setMobileOpen(false);window.scrollTo({top:0});}
  function onUser(next:User|null){version.current++;setUser(next);if(!next)navigate('overview');}
  const current=tab==='profile'?'Hồ sơ cá nhân':navigation.find(n=>n.id===tab)?.label;
  return <div className="app-shell"><aside className={`sidebar ${mobileOpen?'open':''}`}>
    <a href="#overview" className="brand" onClick={e=>{e.preventDefault();navigate('overview');}}><span className="brand-icon"><span/><i/></span><span>SmartEye<small>HIỂU ĐƯỜNG · CHỌN LỐI</small></span></a>
    <button className="mobile-close icon-button" onClick={()=>setMobileOpen(false)} aria-label="Đóng menu"><X size={20}/></button>
    <nav aria-label="Điều hướng chính">{navigation.filter(n=>n.id!=='admin'||user?.role==='admin').map(({id,label,icon:Icon})=><div className="nav-entry" key={id}>{(id==='overview'||id==='history'||id==='admin')&&<div className="nav-group-label">{id==='overview'?'GIAO THÔNG HÀ NỘI':id==='history'?'CÁ NHÂN':'QUẢN TRỊ'}</div>}<button className={`nav-item ${tab===id?'active':''}`} aria-current={tab===id?'page':undefined} onClick={()=>navigate(id)}><Icon size={19}/>{label}{tab===id&&<ChevronRight size={15}/>}</button></div>)}</nav>
    <div className="sidebar-project"><div><Radio size={17}/><b>Hà Nội</b></div><p>Theo dõi từng tuyến đường<br/>giao thông đô thị</p><div className="project-stats"><span><b>{segments.filter(s=>s.active).length}</b> tuyến đường</span><span>Giờ Việt Nam</span></div></div>
    <div className="sidebar-bottom"><p>Dữ liệu rõ ràng.<br/>Chủ động hành trình.</p><small>SmartEye · Phiên bản 1.1</small></div>
  </aside>{mobileOpen&&<div className="sidebar-scrim" onClick={()=>setMobileOpen(false)}/>}
    <div className="main-shell"><header className="topbar"><button className="mobile-toggle icon-button" onClick={()=>setMobileOpen(true)} aria-label="Mở menu"><Menu size={21}/></button><div className="breadcrumb"><span>Không gian làm việc</span><ChevronRight size={14}/><b>{current}</b></div><div className="topbar-actions"><span className="city-label"><MapPin size={14}/>Hà Nội, Việt Nam</span>{user?<button className="user-button" aria-label={`Hồ sơ ${user.name}`} onClick={()=>navigate('profile')}><span>{user.name.charAt(0).toUpperCase()}</span><div>{user.name}<small>{user.role==='admin'?'Quản trị viên':user.role==='analyst'?'Quản lý':'Người dùng'}</small></div><ChevronRight size={15}/></button>:<button className="button small" onClick={()=>setAuthOpen(true)}><LogIn size={15}/>Đăng nhập</button>}</div></header>
    <main>{error&&<div className="connection-error"><Notice kind="error">{error}</Notice><button className="button" onClick={refresh}>Thử kết nối lại</button></div>}
      {(!config||loadedMode!==dataMode)&&!error?<div className="loading-page"><Spinner/><p>Đang kết nối SmartEye…</p></div>:config&&<Suspense fallback={<div className="loading-page"><Spinner/><p>Đang mở trang…</p></div>}>
        {tab==='overview'&&<OverviewPage segments={segments} places={places} onNavigate={navigate} dataMode={dataMode}/>}
        {tab==='forecast'&&<ForecastPage segments={segments} user={user} dataMode={dataMode} demo={demo} onLogin={()=>setAuthOpen(true)} initialRoad={initialRoad} onHistory={id=>{setInitialRoad(id);navigate('monitor');}} onFindRoute={at=>{setPreset(null);setInitialDeparture(at);setRouteKey(k=>k+1);navigate('routes');}} onUpdated={refresh}/>}
        {tab==='routes'&&<RoutesPage key={`${routeKey}-${dataMode}`} places={places} segments={segments} config={config} user={user} dataMode={dataMode} initialDeparture={initialDeparture} onLogin={()=>setAuthOpen(true)} preset={preset} onSaved={()=>setToast('Đã lưu hành trình yêu thích.')}/>}
        {tab==='monitor'&&<TrafficMonitor key={initialRoad||'all'} initialRoad={initialRoad} onForecast={id=>{setInitialRoad(id);navigate('forecast');}} segments={segments} dataMode={dataMode} demo={demo} onFindRoute={()=>navigate('routes')} user={user} onUpdated={refresh}/>}
        {tab==='history'&&<HistoryPage user={user} onLogin={()=>setAuthOpen(true)} segments={segments} onFavorite={f=>{setPreset(f);setRouteKey(k=>k+1);navigate('routes');}}/>}
        {tab==='alerts'&&<AlertsPage user={user} onLogin={()=>setAuthOpen(true)} segments={segments}/>}
        {tab==='admin'&&user?.role==='admin'&&<AdminPage user={user} cameras={cameras} segments={segments} onUpdated={refresh}/>}
        {tab==='profile'&&user&&<ProfilePage user={user} onUser={onUser}/>}
      </Suspense>}
      <footer className="footer"><span>© SmartEye · Hệ thống hỗ trợ quyết định giao thông</span><button className="text-button" onClick={()=>setLegal(true)}>Điều khoản & quyền riêng tư</button></footer>
    </main></div>
    {authOpen&&config&&<AuthModal config={config} onClose={()=>setAuthOpen(false)} onUser={onUser} resetToken={new URLSearchParams(location.search).get('reset')||undefined}/>}
    {toast&&<div role="status" className="toast">{toast}</div>}
    {legal&&<Modal title="Điều khoản & quyền riêng tư" onClose={()=>setLegal(false)}><h3>Sử dụng SmartEye</h3><p>SmartEye phục vụ nghiên cứu, không bảo đảm tình trạng giao thông hay dẫn đường thực tế. Lịch sử minh họa được tạo để bạn trải nghiệm các tính năng; chưa phản ánh tình hình giao thông thực tế.</p><h3>Dữ liệu được lưu</h3><p>Hệ thống lưu thông tin tài khoản, mật khẩu đã băm, phiên đăng nhập, hành trình yêu thích, quan sát, cảnh báo và nhật ký quản trị. Lịch sử và mô hình mô phỏng được lưu riêng với dữ liệu thực. Các bản ghi camera cũ được giữ theo quyền truy cập đã cấp.</p><h3>Bản đồ và địa chỉ</h3><p>Bản đồ sử dụng OpenStreetMap. Nội dung tìm địa chỉ được gửi qua máy chủ tới Photon; tọa độ tìm tuyến được gửi tới OSRM hoặc vùng mạng đường Overpass khi cần. Dịch vụ công cộng có thể chậm hoặc thiếu số nhà. Chọn ghim sát lối vào, kiểm tra biển báo và đường thực tế. Thời gian di chuyển là ước tính và có thể thay đổi. Hành trình chỉ được lưu vào tài khoản khi bạn chọn lưu.</p><h3>Thông tin từ Google Maps</h3><p>Khi dịch vụ Google Maps được bật, điểm đi, điểm đến và giờ khởi hành được gửi đến Google để dự tính hành trình. Kết quả từ Google được hiển thị riêng, không dùng làm lịch sử minh họa hay dữ liệu huấn luyện của dự án. Việc sử dụng tuân theo <a className="text-button" href="https://maps.google.com/help/terms_maps/" target="_blank" rel="noreferrer">Điều khoản Google Maps</a> và <a className="text-button" href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">Chính sách quyền riêng tư Google</a>.</p></Modal>}
  </div>;
}
