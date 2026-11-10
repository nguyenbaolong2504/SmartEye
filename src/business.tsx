import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {RefreshCw} from 'lucide-react';
import {api} from './api';
import {Empty,Notice,Spinner} from './components';
import {type Segment,dateTime} from './types';

export type Direction='forward'|'reverse';
export type Journal={event_id:string;actor_id:number|null;action:string;at:string;note:string;conclusion?:string;version?:number};
export type Incident={id:number;code:string;user_id:number;segment_id:number;direction:Direction;kind:string;position:number[];occurred_at:string;content:string;status:string;assignee_id:number|null;verification:string|null;revision:number;created_at:string;history:Journal[];attachments:{id:string;url:string}[]};
export type Warning={id:number;segment_id:number;direction:Direction;kind:string;position:number[];severity:string;content:string;start_at:string;end_at:string|null;status:string;verification:string|null;revision:number;content_version:number;history:Journal[];origin:string;incident_id:number|null;public_snapshot:{version:number;content:string}|null;notification_state:string;rule_id:number|null;rule_version:number|null};
export type Rule={id:number;name:string;segment_id:number;direction:Direction;metric:string;operator:string;threshold:number;unit:string;window_minutes:number;start_hour:number;end_hour:number;severity:string;active:boolean;tested:boolean;revision:number;content_version:number;history:Journal[]};
export type Source={id:number;name:string;kind:string;segment_id:number;direction:Direction;format:string;url:string;credential_env:string;credential_configured:boolean;interval_seconds:number;stale_minutes:number;authorized:boolean;speed_verified:boolean;state_verified:boolean;count_method:string;mapping:Record<string,string>;units:Record<string,string>;active:boolean;tested:boolean;version:number;revision:number;data_state:string;connection_state:string;last_received_at:string|null;checked_at:string|null;last_error:string|null;history:Journal[]};
export type Metric={value:number;unit:string;observed_at:string;source:string};
export type CurrentRoad={segment_id:number;segment_name:string;direction:Direction;start_node:string;end_node:string;geometry:[number,number][];state:string|null;text:string;fresh:boolean;metrics:Record<string,Metric>;observed_at:string|null;source_name:string|null;reason:string;is_demo:boolean;generated_at:string};
export const kinds:Record<string,string>={congestion:'Ùn tắc',accident:'Tai nạn',obstruction:'Vật cản',roadwork:'Thi công',flood:'Ngập nước',other:'Khác'};
export const statusText:Record<string,string>={pending:'Chờ tiếp nhận',verifying:'Đang xác minh',processing:'Đang xử lý',resolved:'Đã xử lý',rejected:'Đã từ chối',pending_verification:'Chờ xác minh',pending_publication:'Chờ phát hành',published:'Đã phát hành',ended:'Đã kết thúc',cancelled:'Đã hủy',fresh:'Đã cập nhật',stale:'Chưa cập nhật',unknown:'Chưa xác định',error:'Mất kết nối hoặc có lỗi',disabled:'Đã tắt',ready:'Đã kiểm tra',receiving:'Đang tiếp nhận',healthy:'Hoạt động',unavailable:'Chưa khả dụng',configured:'Đã cấu hình',sent:'Đã gửi',pending_delivery:'Đang chờ gửi',retry_pending:'Đang chờ gửi lại'};
export const severityText:Record<string,string>={low:'Thấp',medium:'Trung bình',high:'Cao'};
const actions:Record<string,string>={incident_submitted:'Gửi phản ánh',incident_accepted:'Tiếp nhận',incident_verified:'Xác minh',incident_updated:'Bổ sung thông tin sự cố',incident_progress:'Cập nhật tiến độ',incident_rejected:'Từ chối',incident_resolved:'Hoàn tất xử lý',warning_created:'Tạo cảnh báo',warning_proposed:'Quy tắc đề xuất cảnh báo',warning_verified:'Xác minh cảnh báo',warning_published:'Phát hành',warning_revised:'Lưu phiên bản mới',warning_ended:'Kết thúc',warning_cancelled:'Hủy cảnh báo',rule_created:'Tạo quy tắc',rule_tested:'Kiểm tra quy tắc',rule_enabled:'Bật quy tắc',rule_disabled:'Tắt quy tắc',rule_updated:'Sửa quy tắc',rule_deleted:'Xóa quy tắc',source_created:'Khai báo nguồn',source_tested:'Kiểm tra nguồn',source_enabled:'Bật nguồn',source_disabled:'Tắt nguồn',source_reconfigured:'Sửa cấu hình',source_mapping_changed:'Sửa ánh xạ'};
export const localInput=(value?:string)=>new Date(new Date(value||Date.now()).getTime()+7*3600000).toISOString().slice(0,16);
export const iso=(value:string)=>new Date(`${value}:00+07:00`).toISOString();
export const midpoint=(segment?:Segment):[number,number]=>segment?.geometry[Math.floor(segment.geometry.length/2)]||[21.03,105.82];
export function State({value}:{value:string}){return <span className={`workflow-state ${value}`}>{statusText[value]||value}</span>;}
export function RoadFields({segments,road,direction,onRoad,onDirection}:{segments:Segment[];road:number;direction:Direction;onRoad:(value:number)=>void;onDirection:(value:Direction)=>void}){
 const selected=segments.find(s=>s.id===road);
 return <div className="two-columns"><label className="field">Tuyến đường<select value={road} onChange={e=>onRoad(Number(e.target.value))}>{segments.filter(s=>s.active).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label className="field">Chiều di chuyển<select value={direction} onChange={e=>onDirection(e.target.value as Direction)}><option value="forward">{selected?`${selected.start_node} → ${selected.end_node}`:'Chiều đi'}</option>{!selected?.one_way&&<option value="reverse">{selected?`${selected.end_node} → ${selected.start_node}`:'Chiều về'}</option>}</select></label></div>;
}
export function History({entries}:{entries:Journal[]}){return <ol className="workflow-history">{entries.map((entry,i)=><li key={entry.event_id||i}><b>{actions[entry.action]||entry.action}</b><small>{dateTime(entry.at)}{entry.actor_id?` · Người thực hiện #${entry.actor_id}`:''}</small>{entry.note&&<p>{entry.note}</p>}{entry.conclusion&&<span>{entry.conclusion==='valid'?'Kết luận hợp lệ':entry.conclusion==='invalid'?'Kết luận không hợp lệ':'Chưa đủ căn cứ'}</span>}</li>)}</ol>;}
export function useRemote<T>(path:string,initial:T){
 const[data,setData]=useState<T>(initial);const[loading,setLoading]=useState(true);const[error,setError]=useState('');const[version,setVersion]=useState(0);
 useEffect(()=>{const controller=new AbortController();let active=true;setLoading(true);setError('');api<T>(path,{signal:controller.signal}).then(value=>{if(active)setData(value);}).catch(e=>{if(active)setError((e as Error).message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;controller.abort();};},[path,version]);
 const reload=useCallback(()=>setVersion(v=>v+1),[]);return {data,setData,loading,error,reload};
}
export function useAction(){const[busy,setBusy]=useState(false);const[error,setError]=useState('');const[success,setSuccess]=useState('');const pending=useRef(false);async function run(action:()=>Promise<unknown>,message='Đã lưu thay đổi.'){if(pending.current)return;pending.current=true;setBusy(true);setError('');setSuccess('');try{await action();setSuccess(message);}catch(e){setError((e as Error).message);}finally{pending.current=false;setBusy(false);}}return {busy,error,success,setError,run};}
export function Feedback({error,success}:{error?:string;success?:string}){return <>{error&&<Notice kind="error">{error}</Notice>}{success&&<Notice kind="success">{success}</Notice>}</>;}
export function Loading({loading,error,onRetry,children}:{loading:boolean;error:string;onRetry:()=>void;children:ReactNode}){if(error)return <><Notice kind="error">{error}</Notice><button className="button" onClick={onRetry}><RefreshCw size={15}/>Thử lại</button></>;return loading?<div className="workflow-loading"><Spinner/>Đang tải thông tin…</div>:<>{children}</>;}

export function CurrentConditions({value}: {value: CurrentRoad | null}) {
  if (!value) return <Empty><p>Chưa tải được thông tin giao thông.</p></Empty>;
  return <div className="workflow-current">
    <div className="workflow-item-head"><h3>{value.text}</h3><span className="mode-badge">{value.is_demo ? 'Minh họa' : 'Quan sát'}</span></div>
    <p>{value.reason || 'Dữ liệu được ghi nhận trên tuyến và chiều đang xem.'}</p>
    {value.observed_at && <p className="micro">{value.source_name} · Ghi nhận {dateTime(value.observed_at)}</p>}
    <div className="workflow-grid">
      {([['count', 'Số phương tiện'], ['flow_per_minute', 'Lưu lượng'], ['speed_kmh', 'Vận tốc'], ['score', 'Mật độ']] as const).map(([field, label]) => {
        const metric = value.metrics[field];
        return <article key={field}><span>{label}</span><strong>{metric ? `${Number(metric.value.toFixed(2))} ${metric.unit}` : 'Chưa có dữ liệu'}</strong>{metric && <small>{metric.source} · {dateTime(metric.observed_at)}</small>}</article>;
      })}
    </div>
  </div>;
}

export function trafficLabel(value?: string | null) {
  return value === 'FREE' ? 'Thông thoáng' : value === 'SLOW' ? 'Bình thường' : value === 'JAM' ? 'Ùn tắc' : 'Chưa xác định';
}
