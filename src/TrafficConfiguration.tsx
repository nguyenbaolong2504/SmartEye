import {lazy, Suspense, useState} from 'react';
import {Camera as CameraIcon, Plus, Settings2} from 'lucide-react';
import {api,json} from './api';
import {Modal,Notice,Spinner} from './components';
import {can} from './permissions';
import {SourcesPanel,SystemPanel} from './AdminOperations';
import DemoSetup from './DemoSetup';
import SegmentManager from './SegmentManager';
import type {Camera,DemoStatus,Segment,User} from './types';

const ForecastManagement=lazy(()=>import('./ForecastManagement'));

export default function TrafficConfiguration({user,segments,cameras,demo,onUpdated}: {
  user:User;segments:Segment[];cameras:Camera[];demo:DemoStatus|null;onUpdated:()=>void;
}) {
  const [chosen,setChosen]=useState('');
  const [focusedSource,setFocusedSource]=useState<number>();
  const globalScope=user.managed_segment_ids==null;
  const tabs=[
    {id:'sources',label:'Nguồn dữ liệu',allowed:can(user,'sources.manage')},
    {id:'segments',label:'Đoạn đường',allowed:can(user,'network.manage')},
    {id:'cameras',label:'Camera & hiệu chỉnh',allowed:can(user,'network.manage')},
    {id:'models',label:'Dữ liệu & mô hình',allowed:can(user,'models.manage')},
    {id:'system',label:'Dịch vụ & nhật ký',allowed:globalScope&&can(user,'diagnostics.view')},
  ].filter(item=>item.allowed);
  const tab=tabs.some(item=>item.id===chosen)?chosen:tabs[0]?.id;
  return <>
    <div className="tabs workflow-tabs">{tabs.map(item=><button key={item.id} className={tab===item.id?'active':''} onClick={()=>setChosen(item.id)}>{item.label}</button>)}</div>
    {tab==='sources'&&<SourcesPanel segments={segments} focus={focusedSource}/>}
    {tab==='segments'&&<SegmentManager segments={segments} onUpdated={onUpdated} allowCreate={globalScope}/>}
    {tab==='cameras'&&<CameraSettings cameras={cameras} segments={segments.filter(s=>s.active)} onUpdated={onUpdated}/>}
    {tab==='models'&&<Suspense fallback={<Spinner/>}>{globalScope&&demo?.enabled&&!demo.planning_ready&&<DemoSetup demo={demo} user={user} onUpdated={onUpdated}/>}<ForecastManagement segments={segments} allowActivation={globalScope}/></Suspense>}
    {tab==='system'&&<SystemPanel onSource={can(user,'sources.manage')?id=>{setFocusedSource(id);setChosen('sources');}:undefined}/>}
  </>;
}

function CameraSettings({cameras,segments,onUpdated}:{cameras:Camera[];segments:Segment[];onUpdated:()=>void}) {
  const[error,setError]=useState('');const[busy,setBusy]=useState(false);const[editing,setEditing]=useState<Camera|null|undefined>(undefined);
  const[form,setForm]=useState({name:'',segment_id:segments[0]?.id||1,active:true,capacity:30,low_threshold:.25,high_threshold:.6,roi:[0,0,1,1]});
  function edit(camera:Camera|null){setEditing(camera);setForm(camera?{...camera}:{name:'',segment_id:segments[0]?.id||1,active:true,capacity:30,low_threshold:.25,high_threshold:.6,roi:[0,0,1,1]});}
  async function save(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{await api(editing?`/cameras/${editing.id}`:'/cameras',json(form,editing?'PUT':'POST'));setEditing(undefined);onUpdated();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function disable(camera:Camera){try{await api(`/cameras/${camera.id}`,{method:'DELETE'});onUpdated();}catch(e){setError((e as Error).message);}}
  return <>
    {error&&editing===undefined&&<Notice kind="error">{error}</Notice>}
    <section className="card"><div className="section-title"><CameraIcon size={18}/><h2>Camera theo dõi</h2><button className="button primary small" disabled={!segments.length} onClick={()=>edit(null)}><Plus size={16}/>Thêm camera</button></div><div className="camera-grid">{cameras.map(c=><div className={`camera-card ${c.active?'':'inactive'}`} key={c.id}><div className="camera-card-top"><CameraIcon size={22}/><span className={c.active?'status-active':'muted'}>{c.active?'Đang theo dõi':'Đã ngừng'}</span></div><h3>{c.name}</h3><p>{segments.find(s=>s.id===c.segment_id)?.name}</p><div className="camera-config-row"><span>Sức chứa <b>{c.capacity} xe</b></span><span>Ngưỡng <b>{Math.round(c.low_threshold*100)} / {Math.round(c.high_threshold*100)}%</b></span></div><div className="camera-card-actions"><button className="button small" onClick={()=>edit(c)}><Settings2 size={15}/>Hiệu chỉnh</button>{c.active&&<button className="text-button danger-text" onClick={()=>disable(c)}>Ngừng camera</button>}</div></div>)}</div></section>
    {editing!==undefined&&<Modal title={editing?'Hiệu chỉnh camera':'Thêm camera'} onClose={()=>setEditing(undefined)}><form onSubmit={save}><label className="field">Tên camera<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} required minLength={2} maxLength={120}/></label><label className="field">Gắn vào đoạn đường<select value={form.segment_id} onChange={e=>setForm({...form,segment_id:Number(e.target.value)})}>{segments.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label className="field">Sức chứa xe trong vùng nhận dạng<input type="number" min="1" max="500" value={form.capacity} onChange={e=>setForm({...form,capacity:Number(e.target.value)})}/></label><div className="two-columns"><label className="field">Ngưỡng bình thường (%)<input type="number" min="1" max="95" value={Math.round(form.low_threshold*100)} onChange={e=>setForm({...form,low_threshold:Number(e.target.value)/100})}/></label><label className="field">Ngưỡng cao (%)<input type="number" min="2" max="100" value={Math.round(form.high_threshold*100)} onChange={e=>setForm({...form,high_threshold:Number(e.target.value)/100})}/></label></div><label className="field">Vùng mặt đường ROI (%, từ góc trên trái)</label><div className="roi-fields">{['X trái','Y trên','X phải','Y dưới'].map((label,i)=><label className="field" key={i}>{label}<input type="number" min="0" max="100" value={Math.round(form.roi[i]*100)} onChange={e=>setForm({...form,roi:form.roi.map((v,j)=>i===j?Number(e.target.value)/100:v)})}/></label>)}</div><label className="check"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/>Camera hoạt động</label><p className="micro">Chỉ số = max(tỷ lệ che vùng mặt đường, số xe / sức chứa). Cần hiệu chỉnh với nhãn thực tế của từng góc camera.</p>{error&&<Notice kind="error">{error}</Notice>}<button className="button primary full" disabled={busy}>{busy?<Spinner/>:'Lưu cấu hình'}</button></form></Modal>}
  </>;
}
