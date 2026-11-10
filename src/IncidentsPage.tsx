import {useState} from 'react';
import {MessageSquare,Plus,MapPin} from 'lucide-react';
import {can} from './permissions';
import {api,json} from './api';
import {Empty,Modal,Spinner} from './components';
import {TrafficMap} from './TrafficMap';
import {type User,type Segment,type Config,dateTime} from './types';
import {type Incident,type Direction,kinds,State,History,RoadFields,localInput,iso,midpoint,useRemote,useAction,Feedback,Loading} from './business';

export function IncidentDetails({item}:{item:Incident}){return <><div className="workflow-item-head"><b>{item.code}</b><State value={item.status}/></div><p>{item.content}</p><dl className="workflow-details"><dt>Loại sự cố</dt><dd>{kinds[item.kind]}</dd><dt>Thời điểm xảy ra</dt><dd>{dateTime(item.occurred_at)}</dd><dt>Chiều di chuyển</dt><dd>{item.direction==='forward'?'Chiều đi':'Chiều về'}</dd></dl>{item.attachments.length>0&&<div className="incident-images">{item.attachments.map(a=><a key={a.id} href={a.url} target="_blank" rel="noreferrer"><img src={a.url} alt="Ảnh kèm phản ánh"/></a>)}</div>}<h3>Lịch sử xử lý</h3><History entries={item.history}/></>;}

function Submission({segments,config,onClose,onCreated}:{segments:Segment[];config:Config;onClose:()=>void;onCreated:(item:Incident)=>void}){
 const[road,setRoad]=useState(segments.find(s=>s.active)?.id||0);const[direction,setDirection]=useState<Direction>('forward');const[kind,setKind]=useState('congestion');const[content,setContent]=useState('');const[at,setAt]=useState(localInput());const[file,setFile]=useState<File|null>(null);const[point,setPoint]=useState<[number,number]>(midpoint(segments.find(s=>s.id===road)));const[submissionKey]=useState(()=>crypto.randomUUID());const action=useAction();
 function selectRoad(id:number){setRoad(id);setDirection('forward');setPoint(midpoint(segments.find(s=>s.id===id)));}
 async function submit(e:React.FormEvent){e.preventDefault();await action.run(async()=>{const body={segment_id:road,direction,kind,position:point,occurred_at:iso(at),content,submission_key:submissionKey};let result:Incident;if(file){const data=new FormData();data.append('payload',JSON.stringify(body));data.append('image',file);result=await api('/incidents/with-image',{method:'POST',body:data});}else result=await api('/incidents',json(body));onCreated(result);});}
 return <Modal title="Gửi phản ánh giao thông" onClose={onClose}><form onSubmit={submit}><Feedback error={action.error}/><RoadFields segments={segments} road={road} direction={direction} onRoad={selectRoad} onDirection={setDirection}/><label className="field">Loại sự cố<select value={kind} onChange={e=>setKind(e.target.value)}>{Object.entries(kinds).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><label className="field">Thời điểm xảy ra<input type="datetime-local" value={at} max={localInput()} onChange={e=>setAt(e.target.value)} required/></label><p className="micro"><MapPin size={13}/> Chạm bản đồ để chọn đúng vị trí sự cố trên tuyến đã chọn.</p><div className="incident-location-map"><TrafficMap places={[]} segments={segments.filter(s=>s.id===road)} routes={[]} selected="" onSelect={()=>{}} browserKey="" provider="auto" origin={{lat:point[0],lng:point[1],name:'Vị trí phản ánh'}} picking="origin" onPick={setPoint} tileUrl={config.osm_tile_url}/></div><label className="field">Nội dung phản ánh<textarea value={content} onChange={e=>setContent(e.target.value)} required minLength={10} maxLength={2000} rows={4} placeholder="Mô tả tình hình, vị trí dễ nhận biết và ảnh hưởng đến việc đi lại…"/></label><label className="field">Ảnh đính kèm (không bắt buộc)<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setFile(e.target.files?.[0]||null)}/><small>JPG, PNG hoặc WebP, tối đa 5 MB. Ảnh chỉ dành cho bạn và Quản lý được phân công.</small></label><div className="workflow-buttons"><button type="button" className="button" onClick={onClose} disabled={action.busy}>Hủy</button><button className="button primary" disabled={action.busy}>{action.busy?<Spinner/>:<MessageSquare size={16}/>}Gửi phản ánh</button></div></form></Modal>;
}

export default function IncidentsPage({user,segments,config,onLogin}:{user:User|null;segments:Segment[];config:Config;onLogin:()=>void}){
 const[creating,setCreating]=useState(false);const[detail,setDetail]=useState<Incident|null>(null);const[success,setSuccess]=useState('');
 return <><div className="page-heading"><div><div className="eyebrow">CÙNG THEO DÕI GIAO THÔNG</div><h1>Phản ánh giao thông<span>.</span></h1><p>Gửi thông tin sự cố và theo dõi kết quả xác minh, xử lý.</p></div>{(!user||can(user,'reports.add'))&&<button className="button primary" onClick={()=>user?setCreating(true):onLogin()}><Plus size={16}/>Gửi phản ánh</button>}</div><Feedback success={success}/>{!user?<section className="card"><Empty><p>Đăng nhập để gửi và theo dõi phản ánh của bạn.</p><button className="button primary" onClick={onLogin}>Đăng nhập</button></Empty></section>:can(user,'reports.view')&&<OwnReports key={success} onDetail={setDetail}/>} {creating&&can(user,'reports.add')&&<Submission segments={segments} config={config} onClose={()=>setCreating(false)} onCreated={item=>{setCreating(false);setSuccess(`Đã gửi phản ánh ${item.code}. Quản lý sẽ tiếp nhận và xác minh.`);if(can(user,'reports.view'))setDetail(item);}}/>}{detail&&<Modal title={`Phản ánh ${detail.code}`} onClose={()=>setDetail(null)}><IncidentDetails item={detail}/></Modal>}</>;
}

const reportStates = {
  pending: 'Chờ tiếp nhận', verifying: 'Đang xác minh', processing: 'Đang xử lý',
  resolved: 'Đã xử lý', rejected: 'Đã từ chối',
};

function OwnReports({onDetail}: {onDetail: (item: Incident) => void}) {
  const [state, setState] = useState('');
  const records = useRemote<Incident[]>(`/incidents${state ? `?status=${state}` : ''}`, []);
  const detail = useAction();

  return <section className="card">
    <div className="section-title"><MessageSquare size={18}/><h2>Phản ánh của tôi</h2></div>
    <label className="field">Trạng thái<select value={state} onChange={e => setState(e.target.value)}>
      <option value="">Tất cả trạng thái</option>
      {Object.entries(reportStates).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select></label>
    <Feedback error={detail.error}/>
    <Loading loading={records.loading} error={records.error} onRetry={records.reload}>
      {records.data.length ? <div className="workflow-list">{records.data.map(item => <button className="workflow-list-item" key={item.id}
        disabled={detail.busy} onClick={() => detail.run(async () => onDetail(await api<Incident>(`/incidents/${item.id}`)), '')}>
        <div><b>{item.code} · {kinds[item.kind]}</b><p>{item.content}</p><small>{dateTime(item.created_at)}</small></div>
        <State value={item.status}/>
      </button>)}</div> : <Empty><p>Bạn chưa có phản ánh nào phù hợp.</p></Empty>}
    </Loading>
  </section>;
}
