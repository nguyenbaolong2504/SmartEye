import {can} from './permissions';
import { useEffect, useState } from 'react';
import { Bell, Bookmark, Trash2, Plus, ShieldCheck, Check } from 'lucide-react';
import { api,json } from './api';
import { Notice,Empty } from './components';
import { type User,type Favorite,type Segment,type AlertData,densityLabel,dateTime } from './types';
import PublicWarnings, {WarningLink} from './PublicWarnings';
import {AccountsPanel} from './AdminOperations';

export function HistoryPage({user,onLogin,onFavorite}: {user:User|null;onLogin:()=>void;onFavorite:(f:Favorite)=>void}) {
  const [favorites,setFavorites]=useState<Favorite[]>([]);
  const [error,setError]=useState('');
  useEffect(()=>{if(user)api<Favorite[]>('/favorites').then(setFavorites).catch(e=>setError(e.message));},[user]);
  async function remove(id:number){try{await api(`/favorites/${id}`,{method:'DELETE'});setFavorites(favorites.filter(f=>f.id!==id));}catch(e){setError((e as Error).message);}}
  return <><div className="page-heading"><div><div className="eyebrow">HÀNH TRÌNH CÁ NHÂN</div><h1>Hành trình của bạn<span>.</span></h1><p>Lưu và mở lại những hành trình bạn thường đi.</p></div></div>{error&&<Notice kind="error">{error}</Notice>}
    <section className="card"><div className="section-title"><Bookmark size={18}/><h2>Hành trình yêu thích</h2></div>{!user?<Empty><p>Đăng nhập để lưu hành trình yêu thích.</p><button className="button primary" onClick={onLogin}>Đăng nhập</button></Empty>:favorites.length?<div className="favorite-grid">{favorites.map(f=><div key={f.id} className="favorite-card"><Bookmark size={20}/><h3>{f.name}</h3><p>{f.request.mode==='DRIVE'?'Ô tô':'Xe máy'} · {['osm','auto'].includes(f.request.provider)?'OpenStreetMap':f.request.provider==='demo'?'Mạng cấu hình':'Google Routes'}</p><div>{can(user,'routes.search')&&<button className="button small primary" onClick={()=>onFavorite(f)}>Tìm lại tuyến</button>}{can(user,'favorites.delete')&&<button className="icon-button" aria-label={`Xóa ${f.name}`} onClick={()=>remove(f.id)}><Trash2 size={16}/></button>}</div></div>)}</div>:<Empty><p>Chưa có hành trình đã lưu. Bạn có thể lưu sau khi tìm tuyến.</p></Empty>}</section>
  </>;
}

export function AlertsPage({user,onLogin,segments}: {user:User|null;onLogin:()=>void;segments:Segment[]}) {
  const[data,setData]=useState<AlertData>({rules:[],notifications:[]});const[segment,setSegment]=useState(String(segments[0]?.id||''));const[density,setDensity]=useState('HIGH');const[error,setError]=useState('');const[busy,setBusy]=useState(false);
  const load=()=>api<AlertData>('/alerts').then(setData).catch(e=>setError(e.message));
  useEffect(()=>{if(!can(user,'alerts.view'))return;load();const t=setInterval(load,30000);return()=>clearInterval(t);},[user]);
  async function add(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{await api('/alerts',json({segment_id:Number(segment),density,active:true}));await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function action(path:string,method:string){try{await api(path,{method});await load();}catch(e){setError((e as Error).message);}}
  return <><div className="page-heading"><div><div className="eyebrow">CHỦ ĐỘNG VỚI GIAO THÔNG</div><h1>Cảnh báo giao thông<span>.</span></h1><p>Xem cảnh báo đã phát hành và thông báo của bạn.</p></div></div>{can(user,'warnings.view')&&<PublicWarnings segments={segments}/>}{error&&<Notice kind="error">{error}</Notice>}{!user?<section className="card"><Empty><Bell size={32}/><p>Đăng nhập để theo dõi các đoạn đường thường đi.</p><button className="button primary" onClick={onLogin}>Đăng nhập</button></Empty></section>:can(user,'alerts.view')&&<div className="two-columns"><section className="card"><div className="section-title"><Bell size={18}/><h2>Điều kiện theo dõi</h2></div>{can(user,'alerts.follow')&&<form onSubmit={add}><label className="field">Đoạn đường<select value={segment} onChange={e=>setSegment(e.target.value)}>{segments.filter(s=>s.active).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label className="field">Thông báo khi mật độ<select value={density} onChange={e=>setDensity(e.target.value)}>{Object.entries(densityLabel).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><button className="button primary full" disabled={busy}><Plus size={17}/>Thêm theo dõi</button></form>}<p className="micro">Thông báo phát sinh khi một quan sát mới được xác nhận. Mỗi điều kiện gửi tối đa một lần trong 10 phút.</p><div className="rule-list">{data.rules.map(r=><div className="segment-row" key={r.id}><span>{segments.find(s=>s.id===r.segment_id)?.name}<small>Mật độ {densityLabel[r.density].toLowerCase()}</small></span>{can(user,'alerts.follow')&&<button className="icon-button" onClick={()=>action(`/alerts/${r.id}`,'DELETE')} aria-label="Bỏ theo dõi"><Trash2 size={16}/></button>}</div>)}</div></section><section className="card"><div className="section-title"><Bell size={18}/><h2>Thông báo gần đây</h2><span className="count-badge">{data.notifications.filter(n=>!n.read).length}</span></div>{data.notifications.length?data.notifications.map(n=><div className={`notification ${n.read?'read':''}`} key={n.id}><Bell size={17}/><div><p>{n.message}</p><small>{dateTime(n.created_at)}</small>{n.warning_id&&can(user,'warnings.view')&&<WarningLink id={n.warning_id} segments={segments}/>}</div>{!n.read&&can(user,'alerts.read')&&<button className="icon-button" aria-label="Đánh dấu đã đọc" onClick={()=>action(`/notifications/${n.id}/read`,'POST')}><Check size={17}/></button>}</div>):<Empty><p>Chưa có cảnh báo mới. Bạn sẽ thấy thông báo tại đây khi điều kiện được đáp ứng.</p></Empty>}</section></div>}</>;
}

export function AdminPage({user,segments}:{user:User;segments:Segment[]}) {
  return <>
    <div className="page-heading"><div><div className="eyebrow">QUẢN TRỊ TÀI KHOẢN</div><h1>Không gian quản trị<span>.</span></h1><p>Tạo tài khoản, phân quyền thao tác và phân công tuyến cho Quản lý.</p></div><span className="mode-badge"><ShieldCheck size={16}/>Quản trị viên</span></div>
    <AccountsPanel currentUser={user} segments={segments}/>
  </>;
}
