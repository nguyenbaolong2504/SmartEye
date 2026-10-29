import { useState } from 'react';
import { Database, RefreshCw } from 'lucide-react';
import { api } from './api';
import { Notice,Spinner } from './components';
import { type DemoStatus,type User } from './types';

export default function DemoSetup({demo,user,onUpdated}:{demo:DemoStatus|null;user:User|null;onUpdated:()=>void}){
  const[error,setError]=useState('');const[busy,setBusy]=useState(false);
  async function prepare(){setBusy(true);setError('');try{await api('/demo/prepare',{method:'POST'});onUpdated();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="card demo-setup"><Database size={28}/><h2>{demo?.running?'Đang chuẩn bị bản chạy thử':'Chuẩn bị dữ liệu mô phỏng'}</h2><p>{demo?.message||'Đang kết nối bộ dữ liệu mẫu…'}</p><p className="muted">Lịch sử giờ cao điểm, ngày thường và cuối tuần sẽ giúp bạn thử dự báo và thống kê mà chưa cần camera.</p>{demo?.running?<Spinner/>:user?.role==='admin'?<button className="button primary" disabled={busy} onClick={prepare}>{busy?<Spinner/>:<RefreshCw size={16}/>}Tạo dữ liệu mẫu</button>:<p className="micro">Dữ liệu được chuẩn bị tự động khi máy chủ chạy lần đầu. Nếu cần tạo lại, đăng nhập tài khoản Admin.</p>}{error&&<Notice kind="error">{error}</Notice>}</section>;
}
