import { useState } from 'react';
import { Database, RefreshCw } from 'lucide-react';
import { api } from './api';
import { Notice,Spinner } from './components';
import { type DemoStatus,type User } from './types';

export default function DemoSetup({demo,user,onUpdated}:{demo:DemoStatus|null;user:User|null;onUpdated:()=>void}){
  const[error,setError]=useState('');const[busy,setBusy]=useState(false);
  async function prepare(){setBusy(true);setError('');try{await api('/demo/prepare',{method:'POST'});onUpdated();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="card demo-setup"><Database size={28}/><h2>{demo?.running?'Đang cập nhật lịch sử giao thông':'Lịch sử đang được chuẩn bị'}</h2><p>{demo?.message||'Đang kết nối bộ dữ liệu mẫu…'}</p><p className="muted">Lịch sử theo từng ngày đang được tổng hợp để giúp bạn chọn giờ đi phù hợp.</p>{demo?.running?<Spinner/>:user?.role==='admin'?<button className="button primary" disabled={busy} onClick={prepare}>{busy?<Spinner/>:<RefreshCw size={16}/>}Cập nhật lịch sử</button>:<p className="micro">Dữ liệu được chuẩn bị tự động khi máy chủ chạy lần đầu. Nếu cần tạo lại, đăng nhập tài khoản Admin.</p>}{error&&<Notice kind="error">{error}</Notice>}</section>;
}
