import {useEffect, useState} from 'react';
import {Database, Download, Plus, ShieldCheck} from 'lucide-react';
import {api, json} from './api';
import {Empty, Modal, Notice, Spinner} from './components';
import {type Segment, type User, dateTime} from './types';
import {type Direction, type Source, Feedback, History, Loading, RoadFields, State, iso, localInput, useAction, useRemote} from './business';

const sourceKinds: Record<string, string> = {file:'Tệp lịch sử', api:'Dịch vụ dữ liệu', camera:'Camera'};
const roles: Record<User['role'],string> = {user:'Người dùng', analyst:'Quản lý', admin:'Quản trị viên'};
const permissionGroups:Record<string,string>={cameras:'Camera giao thông',traffic:'Tình trạng và bản đồ',forecast:'Dự báo',routes:'Tìm đường',favorites:'Hành trình đã lưu',warnings:'Cảnh báo công khai',alerts:'Thông báo cá nhân',reports:'Phản ánh của mình',monitor:'Giám sát',incidents:'Xử lý phản ánh',publication:'Phát hành cảnh báo',rules:'Quy tắc cảnh báo',analytics:'Báo cáo giao thông',sources:'Nguồn dữ liệu',network:'Đoạn đường và camera',models:'Dữ liệu và mô hình',diagnostics:'Dịch vụ và nhật ký'};
const fieldNames: Record<string,string> = {observed_at:'Thời điểm quan sát', segment_id:'Mã tuyến', direction:'Chiều đường', count:'Số phương tiện', interval_seconds:'Khoảng đo (giây)', speed_kmh:'Vận tốc', score:'Chỉ số mật độ', density:'Mức mật độ', state:'Tình trạng ùn tắc'};
const mandatory = new Set(['observed_at','segment_id','direction']);
const receiptEmpty: Receipt[] = [];
type Receipt = {id:number; source_version:number; accepted:number; rejected:number; duplicates:number; errors:{row?:number;reason:string}[]; received_at:string};

export function SourcesPanel({segments, focus}: {segments: Segment[]; focus?: number}) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState<Source | null>(null);
  const [editing, setEditing] = useState<Source | null | undefined>(undefined);
  const list = useRemote<Source[]>(`/management/sources?q=${encodeURIComponent(filter)}`, []);
  useEffect(() => {
    if (focus && !list.loading) setSelected(list.data.find(s => s.id === focus) || null);
  }, [focus, list.loading]);
  function update(value: Source) {
    setSelected(value);
    list.reload();
  }
  return <section className="card">
    <div className="section-title"><Database size={19}/><h2>Nguồn dữ liệu</h2><button className="button primary small" onClick={() => setEditing(null)}><Plus size={16}/>Thêm nguồn</button></div>
    <p>Khai báo nguồn, kiểm tra định dạng và kết nối rồi bật tiếp nhận.</p>
    <form className="workflow-filter" onSubmit={e => {e.preventDefault(); setFilter(query); list.reload();}}><label className="field">Tìm nguồn<input maxLength={100} value={query} onChange={e => setQuery(e.target.value)}/></label><button className="button primary">Tìm kiếm</button></form>
    <Loading loading={list.loading} error={list.error} onRetry={list.reload}>
      {list.data.length ? <div className="workflow-list">{list.data.map(s => <button className="workflow-list-item" key={s.id} onClick={() => setSelected(s)}>
        <div><b>{s.name}</b><p>{sourceKinds[s.kind]} · {segments.find(r => r.id === s.segment_id)?.name}</p><small>{s.last_received_at ? `Nhận gần nhất ${dateTime(s.last_received_at)}` : 'Chưa có lần nhận'}</small></div><State value={s.data_state}/>
      </button>)}</div> : <Empty><p>Chưa có nguồn phù hợp.</p></Empty>}
    </Loading>
    {editing !== undefined ? <Modal title={editing ? 'Sửa cấu hình nguồn' : 'Thêm nguồn dữ liệu'} onClose={() => setEditing(undefined)}>
      <SourceForm source={editing} segments={segments} onClose={() => setEditing(undefined)} onSave={value => {setEditing(undefined); update(value);}}/>
    </Modal> : selected && <Modal title={selected.name} onClose={() => setSelected(null)}>
      <SourceDetails key={selected.id} source={selected} onUpdate={update} onEdit={() => setEditing(selected)}/>
    </Modal>}
  </section>;
}

function SourceForm({source, segments, onSave, onClose}: {source: Source | null; segments: Segment[]; onSave: (value: Source) => void; onClose: () => void}) {
  const [fields, setFields] = useState({
    name: source?.name || '', kind: source?.kind || 'file', segment_id: source?.segment_id || segments.find(s => s.active)?.id || 0,
    direction: source?.direction || 'forward' as Direction, format: source?.format || 'csv', url: source?.url || '',
    credential_env: source?.credential_env || '', interval_seconds: source?.interval_seconds || 60, stale_minutes: source?.stale_minutes || 15,
    count_method: source?.count_method || 'occupancy', authorized: source?.authorized || false, speed_verified: source?.speed_verified || false, state_verified: source?.state_verified || false,
    public_preview:source?.public_preview||false,location_name:source?.location_name||'',
  });
  const [latitude,setLatitude]=useState(source?.position?.[0]?.toString()||'');
  const [longitude,setLongitude]=useState(source?.position?.[1]?.toString()||'');
  const action = useAction();
  function update<K extends keyof typeof fields>(key: K, value: typeof fields[K]) {setFields(previous => ({...previous, [key]: value}));}
  function submit(event: React.FormEvent) {
    event.preventDefault();
    void action.run(async () => {
      if(fields.kind==='camera'&&Boolean(latitude)!==Boolean(longitude))throw new Error('Nhập đủ vĩ độ và kinh độ của camera.');
      const payload={...fields,public_preview:fields.kind==='camera'&&fields.public_preview,
        position:fields.kind==='camera'&&latitude&&longitude?[Number(latitude),Number(longitude)]:null};
      const data = await api<Source>(source ? `/management/sources/${source.id}` : '/management/sources',
        json(source ? {...payload, revision: source.revision} : payload, source ? 'PATCH' : 'POST'));
      onSave(data);
    });
  }
  return <form onSubmit={submit}>
    <Feedback error={action.error}/>
    <label className="field">Tên nguồn<input value={fields.name} required minLength={3} maxLength={120} onChange={e => update('name', e.target.value)}/></label>
    <RoadFields segments={segments} road={fields.segment_id} direction={fields.direction} onRoad={id => setFields(old => ({...old,segment_id:id,direction:'forward'}))} onDirection={v => update('direction',v)}/>
    <div className="two-columns">
      <label className="field">Loại nguồn<select value={fields.kind} onChange={e => {
        const kind = e.target.value;
        setFields(old => ({...old, kind, format:kind === 'camera' ? 'image' : kind === 'api' ? 'json' : 'csv', url:kind === 'file' ? '' : old.url, credential_env:kind === 'file' ? '' : old.credential_env}));
      }}>{Object.entries(sourceKinds).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="field">Định dạng<select value={fields.format} onChange={e => update('format',e.target.value)}>{(fields.kind === 'camera' ? [['image','Ảnh'],['video','Video']] : [['csv','CSV'],['json','JSON']]).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>
    {fields.kind !== 'file' && <>
      <label className="field">Địa chỉ kết nối<input type="url" value={fields.url} onChange={e => update('url',e.target.value)} required placeholder="https://…" maxLength={1000}/></label>
      <label className="field">Tên biến chứa mã truy cập (nếu có)<input value={fields.credential_env} onChange={e => update('credential_env',e.target.value)} placeholder="TRAFFIC_SOURCE_…" maxLength={80}/><small>Chỉ nhập tên biến đã cấu hình trên máy chủ.</small></label>
    </>}
    <div className="two-columns"><label className="field">Chu kỳ lấy dữ liệu (giây)<input type="number" min={5} max={3600} value={fields.interval_seconds} onChange={e => update('interval_seconds',Number(e.target.value))} required/></label><label className="field">Thời hạn dữ liệu mới (phút)<input type="number" min={1} max={1440} value={fields.stale_minutes} onChange={e => update('stale_minutes',Number(e.target.value))} required/></label></div>
    {fields.kind !== 'camera' && <>
      <label className="field">Phương pháp đếm<select value={fields.count_method} onChange={e => update('count_method',e.target.value)}><option value="occupancy">Đếm xe tại thời điểm</option><option value="crossings">Đếm xe đi qua trong một khoảng đo</option></select></label>
      <label className="check"><input type="checkbox" checked={fields.speed_verified} onChange={e => update('speed_verified',e.target.checked)}/>Nguồn có phương pháp đo vận tốc đã kiểm chứng</label>
      <label className="check"><input type="checkbox" checked={fields.state_verified} onChange={e => update('state_verified',e.target.checked)}/>Nguồn có tiêu chí phân loại ùn tắc đã kiểm chứng</label>
    </>}
    {fields.kind==='camera'&&<>
      <label className="field">Vị trí hoặc giao lộ<input maxLength={160} value={fields.location_name} onChange={e=>update('location_name',e.target.value)} placeholder="Ví dụ ngã tư Hoàng Quốc Việt – Phạm Văn Đồng"/></label>
      <div className="two-columns"><label className="field">Vĩ độ camera<input type="number" step="any" min={-90} max={90} value={latitude} onChange={e=>setLatitude(e.target.value)} placeholder="21.046"/></label><label className="field">Kinh độ camera<input type="number" step="any" min={-180} max={180} value={longitude} onChange={e=>setLongitude(e.target.value)} placeholder="105.789"/></label></div>
      <p className="micro">Có thể để trống tọa độ để đặt ghim theo đoạn đường đã chọn.</p>
      <label className="check"><input type="checkbox" checked={fields.public_preview} onChange={e=>update('public_preview',e.target.checked)}/>Cho phép người dùng xem camera trên trang Camera giao thông</label>
    </>}
    <label className="check"><input type="checkbox" checked={fields.authorized} onChange={e => update('authorized',e.target.checked)} required/>Tôi xác nhận được phép sử dụng nguồn này</label>
    <div className="workflow-buttons"><button type="button" className="button" onClick={onClose}>Hủy</button><button className="button primary" disabled={action.busy || !fields.segment_id}>Lưu cấu hình nguồn</button></div>
  </form>;
}

function SourceDetails({source, onUpdate, onEdit}: {source: Source; onUpdate: (value: Source) => void; onEdit: () => void}) {
  const [mapping, setMapping] = useState<Record<string,string>>({...Object.fromEntries([...mandatory].map(k => [k,k])),...source.mapping});
  const [speedUnit, setSpeedUnit] = useState(source.units.speed_kmh || 'km/h');
  const [sample, setSample] = useState('');
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [showMapping, setShowMapping] = useState(!source.tested && source.kind !== 'camera');
  const [showReceipts, setShowReceipts] = useState(false);
  const action = useAction();
  const path = `/management/sources/${source.id}`;
  function parseSample() {
    if (!sample.trim()) return undefined;
    try {
      const value: unknown = JSON.parse(sample);
      if (typeof value !== 'object' || !value || Array.isArray(value)) throw new Error();
      return value;
    } catch {throw new Error('Bản ghi mẫu phải là một đối tượng JSON hợp lệ.');}
  }
  function map(confirmed: boolean) {
    void action.run(async () => {
      const value = await api<Source & {preview: Record<string,unknown> | null; saved:boolean}>(`${path}/mapping`, json({
        revision:source.revision, mapping:Object.fromEntries(Object.entries(mapping).filter(([,v]) => v.trim())), units:{speed_kmh:speedUnit}, sample:parseSample(), confirmed,
      }, 'PUT'));
      setPreview(value.preview);
      if (value.saved) onUpdate(value);
    }, confirmed ? 'Đã lưu ánh xạ. Hãy kiểm tra nguồn trước khi bật.' : 'Đã kiểm tra cấu hình ánh xạ.');
  }
  function testSource() {
    void action.run(async () => {
      const next = await api<Source & {preview:Record<string,unknown> | null}>(`${path}/test`, json({revision:source.revision,sample:parseSample()}));
      onUpdate(next);
      setPreview(next.preview);
    }, 'Nguồn đã qua kiểm tra.');
  }
  function receive() {
    void action.run(async () => {
      let result: Receipt;
      if (source.kind === 'file') {
        if (!file) throw new Error('Chọn tệp dữ liệu trước khi nhập.');
        const data = new FormData();
        data.append('file',file);
        result = await api(`${path}/upload`, {method:'POST',body:data});
      } else result = await api(`${path}/poll`, {method:'POST'});
      setPreview({accepted:result.accepted,rejected:result.rejected,duplicates:result.duplicates});
      setShowReceipts(true);
    }, 'Đã xử lý lượt tiếp nhận.');
  }
  return <>
    <div className="workflow-item-head"><span>{sourceKinds[source.kind]} · Phiên bản {source.version}</span><State value={source.data_state}/></div>
    <p className="micro">{source.tested ? 'Đã kiểm tra cấu hình' : 'Chưa kiểm tra cấu hình'} · {source.active ? 'Đang bật' : 'Đang tắt'}</p>
    {source.last_error && <Notice kind="error">{source.last_error}</Notice>}
    <Feedback error={action.error} success={action.success}/>
    <div className="workflow-buttons">
      <button className="button" onClick={onEdit}>Sửa cấu hình</button>
      {source.kind !== 'camera' && <button className="button" onClick={() => setShowMapping(v => !v)}>Ánh xạ trường dữ liệu</button>}
      <button className="button" onClick={testSource} disabled={action.busy}>Kiểm tra nguồn</button>
      <button className="button primary" disabled={action.busy} onClick={() => {
        if (!window.confirm(source.active ? 'Tắt tiếp nhận từ nguồn này?' : 'Bật tiếp nhận từ nguồn đã kiểm tra?')) return;
        void action.run(async () => onUpdate(await api<Source>(`${path}/toggle`, json({revision:source.revision,active:!source.active,confirmed:true}))));
      }}>{source.active ? 'Tắt nguồn' : 'Bật nguồn'}</button>
    </div>
    {showMapping && source.kind !== 'camera' && <div className="workflow-actions">
      <h3>Ánh xạ trường dữ liệu</h3><p className="micro">Nhập tên cột hoặc tên trường đúng như trong nguồn. Có thể bỏ trống chỉ số chưa đo được.</p>
      <div className="two-columns">{Object.entries(fieldNames).map(([key,label]) => <label className="field" key={key}>{label}{mandatory.has(key) ? ' *' : ''}<input value={mapping[key] || ''} placeholder={key} onChange={e => setMapping(old => ({...old,[key]:e.target.value}))} maxLength={80}/></label>)}</div>
      <label className="field">Đơn vị vận tốc trong nguồn<select value={speedUnit} onChange={e => setSpeedUnit(e.target.value)}><option>km/h</option><option>m/s</option></select></label>
      <label className="field">Bản ghi mẫu để kiểm tra<textarea rows={4} value={sample} onChange={e => setSample(e.target.value)} placeholder={'{"observed_at":"…","segment_id":1,"direction":"forward","count":10}'}/><small>Bản ghi mẫu chỉ dùng để kiểm tra ánh xạ.</small></label>
      <div className="workflow-buttons"><button className="button" disabled={action.busy} onClick={() => map(false)}>Thử ánh xạ</button><button className="button primary" disabled={action.busy} onClick={() => map(true)}>Xác nhận lưu ánh xạ</button></div>
    </div>}
    {preview && <div className="workflow-preview"><b>Kết quả kiểm tra hoặc tiếp nhận</b><pre>{JSON.stringify(preview, null, 2)}</pre></div>}
    {source.active && source.kind !== 'camera' && <div className="workflow-actions">
      {source.kind === 'file' && <label className="field">Tệp quan trắc<input type="file" accept={source.format === 'csv' ? '.csv,text/csv' : '.json,application/json'} onChange={e => setFile(e.target.files?.[0] || null)}/></label>}
      <button className="button primary" disabled={action.busy} onClick={receive}>{source.kind === 'file' ? 'Nhập dữ liệu' : 'Tiếp nhận ngay'}</button>
    </div>}
    <button className="button" onClick={() => setShowReceipts(v => !v)}>Tình trạng tiếp nhận</button>
    {showReceipts && <Receipts key={action.success} sourceId={source.id}/>}
    <details className="workflow-section"><summary>Lịch sử cấu hình</summary><History entries={source.history}/></details>
  </>;
}

function Receipts({sourceId}: {sourceId:number}) {
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [filter, setFilter] = useState('');
  const result = useRemote<Receipt[]>(`/management/sources/${sourceId}/receipts?${filter}`, receiptEmpty);
  return <div className="workflow-actions">
    <form onSubmit={e => {e.preventDefault(); const q = new URLSearchParams(); if(start)q.set('start',iso(start)); if(end)q.set('end',iso(end)); setFilter(q.toString()); result.reload();}}>
      <div className="two-columns"><label className="field">Từ thời điểm<input type="datetime-local" value={start} onChange={e => setStart(e.target.value)}/></label><label className="field">Đến thời điểm<input type="datetime-local" value={end} min={start} onChange={e => setEnd(e.target.value)}/></label></div>
      <button className="button">Xem lượt tiếp nhận</button>
    </form>
    <Loading loading={result.loading} error={result.error} onRetry={result.reload}>{result.data.length ? result.data.map(r => <div className="workflow-row" key={r.id}>
      <b>{dateTime(r.received_at)}</b><p>{r.accepted} hợp lệ · {r.rejected} bị loại · {r.duplicates} trùng · Cấu hình {r.source_version}</p>{r.errors.map((error,index) => <small key={index}>{error.row ? `Dòng ${error.row}. ` : ''}{error.reason}</small>)}
    </div>) : <p>Chưa có dữ liệu tiếp nhận.</p>}</Loading>
  </div>;
}

export function AccountsPanel({currentUser, segments}: {currentUser: User; segments: Segment[]}) {
  const [query, setQuery] = useState('');
  const [role, setRole] = useState('');
  const [active, setActive] = useState('');
  const [filter, setFilter] = useState('');
  const [editing, setEditing] = useState<{mode:'create'|'edit'|'role'|'disable'; user:User|null} | null>(null);
  const result = useRemote<User[]>(`/admin/accounts?${filter}`, []);
  const action = useAction();
  return <section className="card">
    <div className="section-title"><ShieldCheck size={19}/><h2>Quản lý tài khoản</h2><button className="button primary small" onClick={() => setEditing({mode:'create',user:null})}><Plus size={16}/>Thêm tài khoản</button></div>
    <form className="workflow-filter" onSubmit={e => {e.preventDefault(); setFilter(new URLSearchParams(Object.entries({q:query,role,active}).filter(([,v]) => v)).toString()); result.reload();}}>
      <label className="field">Tìm người dùng<input value={query} onChange={e => setQuery(e.target.value)} maxLength={100}/></label>
      <label className="field">Vai trò<select value={role} onChange={e => setRole(e.target.value)}><option value="">Tất cả</option>{Object.entries(roles).map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label className="field">Trạng thái<select value={active} onChange={e => setActive(e.target.value)}><option value="">Tất cả</option><option value="true">Hoạt động</option><option value="false">Vô hiệu hóa</option></select></label><button className="button primary">Tìm kiếm</button>
    </form>
    <Feedback error={action.error} success={action.success}/>
    <Loading loading={result.loading} error={result.error} onRetry={result.reload}>
      {result.data.length ? <div className="workflow-list">{result.data.map(u => <article className="workflow-row" key={u.id}>
        <div className="workflow-item-head"><b>{u.name}</b><span className="workflow-state">{u.active ? 'Hoạt động' : 'Vô hiệu hóa'}</span></div>
        <p>{u.email} · {roles[u.role]}{u.username && ` · ${u.username}`}</p>
        <div className="workflow-buttons"><button className="button small" onClick={() => setEditing({mode:'edit',user:u})}>Sửa thông tin</button>
          <button className="button small" disabled={u.id === currentUser.id} onClick={() => setEditing({mode:'role',user:u})}>Phân quyền</button>
          <button className="button small" disabled={!u.active || u.protected || u.id === currentUser.id} onClick={() => setEditing({mode:'disable',user:u})}>Vô hiệu hóa</button>
          <button className="button small" disabled={action.busy || u.id === currentUser.id} onClick={() => {if(window.confirm('Thu hồi các phiên đăng nhập của tài khoản này?'))void action.run(() => api(`/admin/users/${u.id}/revoke`,{method:'POST'}),'Đã thu hồi phiên đăng nhập.');}}>Thu hồi phiên</button>
        </div>
      </article>)}</div> : <Empty><p>Không có tài khoản phù hợp.</p></Empty>}
    </Loading>
    {editing && <Modal title={{create:'Thêm tài khoản',edit:'Sửa thông tin tài khoản',role:'Phân quyền tài khoản',disable:'Vô hiệu hóa tài khoản'}[editing.mode]} onClose={() => setEditing(null)}>
      <AccountForm {...editing} segments={segments} onClose={() => setEditing(null)} onSaved={() => {setEditing(null); result.reload();}}/>
    </Modal>}
  </section>;
}

function AccountForm({mode,user,segments,onClose,onSaved}: {mode:'create'|'edit'|'role'|'disable';user:User|null;segments:Segment[];onClose:()=>void;onSaved:()=>void}) {
  const [name,setName] = useState(user?.name || '');
  const [email,setEmail] = useState(user?.email || '');
  const [username,setUsername] = useState('');
  const [phone,setPhone] = useState(user?.phone || '');
  const [role,setRole] = useState<User['role']>(user?.role || 'user');
  const [active,setActive] = useState(user?.active ?? true);
  const [password,setPassword] = useState('');
  const [confirmation,setConfirmation] = useState('');
  const [reason,setReason] = useState('');
  const [all,setAll] = useState(user?.managed_segment_ids == null);
  const [scope,setScope] = useState<number[]>(user?.managed_segment_ids || []);
  const [permissions,setPermissions] = useState<string[]|null>(user?.uses_role_permissions===false?user.permissions:null);
  const [catalog,setCatalog] = useState<Record<string,Record<string,string>>|null>(null);
  const [catalogError,setCatalogError] = useState('');
  const action = useAction();
  const profile = mode === 'create' || mode === 'edit';
  const options=catalog?.[role]||{};
  const selected=permissions??Object.keys(options);
  useEffect(()=>{
    if(mode!=='role')return;
    const controller=new AbortController();
    api<Record<string,Record<string,string>>>('/admin/permission-options',{signal:controller.signal}).then(setCatalog).catch(e=>{if(!controller.signal.aborted)setCatalogError(e.message);});
    return()=>controller.abort();
  },[mode]);
  function submit(e:React.FormEvent) {
    e.preventDefault();
    void action.run(async () => {
      const managed_segment_ids = role === 'analyst' && !all ? scope : null;
      const path = user ? `/admin/accounts/${user.id}` : '/admin/accounts';
      if (mode === 'create') {
        if (password !== confirmation) throw new Error('Mật khẩu và xác nhận không khớp.');
        await api(path,json({name,email,username,phone,password,password_confirmation:confirmation,role,managed_segment_ids}));
      } else if (mode === 'edit') await api(path,json({name,email,phone,active,revision:user?.profile_version},'PATCH'));
      else if (mode === 'role') await api(`${path}/role`,json({role,managed_segment_ids,permissions:role==='admin'?null:permissions,revision:user?.profile_version,confirmed:true}));
      else await api(`${path}/disable`,json({revision:user?.profile_version,note:reason}));
      onSaved();
    });
  }
  return <form onSubmit={submit}>
    <Feedback error={action.error}/>
    {user && <p>{user.name} · {user.email}</p>}
    {profile && <><label className="field">Họ và tên<input required minLength={2} maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label><label className="field">Email<input required type="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)}/></label><label className="field">Số điện thoại<input type="tel" maxLength={24} value={phone} onChange={e => setPhone(e.target.value)}/></label></>}
    {mode === 'create' && <>
      <label className="field">Tên đăng nhập<input required minLength={3} maxLength={40} pattern="[A-Za-z0-9_.\\-]+" value={username} onChange={e => setUsername(e.target.value)}/></label>
      <label className="field">Mật khẩu<input type="password" minLength={10} maxLength={128} required value={password} onChange={e => setPassword(e.target.value)}/></label>
      <label className="field">Xác nhận mật khẩu<input type="password" minLength={10} maxLength={128} required value={confirmation} onChange={e => setConfirmation(e.target.value)}/></label>
    </>}
    {mode === 'edit' && <label className="check"><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)}/>Tài khoản hoạt động</label>}
    {(mode === 'create' || mode === 'role') && <>
      <label className="field">Vai trò<select value={role} onChange={e => {setRole(e.target.value as User['role']);setPermissions(null);}}>{Object.entries(roles).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      {role === 'analyst' && <><label className="check"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)}/>Quản lý tất cả tuyến</label>
        {!all && <label className="field">Các tuyến được phân công<select multiple value={scope.map(String)} onChange={e => setScope(Array.from(e.target.selectedOptions,o => Number(o.value)))}>{segments.filter(s => s.active).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}</>}
      {mode==='role'&&role!=='admin'&&<section className="permission-editor">
        <h3>Quyền theo từng thao tác</h3>
        <p className="micro">Bỏ chọn mục nào thì tài khoản sẽ không thấy mục đó. Để dùng nút trong một màn hình quản lý, bật cả quyền xem màn hình đó.</p>
        <Feedback error={catalogError}/>
        {!catalog&&!catalogError?<Spinner/>:catalog&&<>
          <button className="button small" type="button" onClick={()=>setPermissions(null)} disabled={permissions===null}>Dùng quyền mặc định</button>
          {Object.entries(permissionGroups).map(([group,label])=>{
            const entries=Object.entries(options).filter(([key])=>key.startsWith(group+'.'));
            return entries.length>0&&<fieldset key={group}><legend>{label}</legend>{entries.map(([key,title])=><label className="check" key={key}>
              <input type="checkbox" checked={selected.includes(key)} onChange={e=>setPermissions(e.target.checked?[...selected,key]:selected.filter(item=>item!==key))}/>{title}
            </label>)}</fieldset>;
          })}
        </>}
      </section>}
      {mode === 'role' && <p className="micro">Quyền mới được áp dụng sau khi xác nhận. Tài khoản cần đăng nhập lại.</p>}
    </>}
    {mode === 'disable' && <><p>Tài khoản sẽ bị vô hiệu hóa và thu hồi phiên. Lịch sử nghiệp vụ được lưu để tra cứu.</p><label className="field">Lý do vô hiệu hóa<textarea required minLength={5} maxLength={2000} value={reason} onChange={e => setReason(e.target.value)}/></label></>}
    <div className="workflow-buttons"><button className="button" type="button" onClick={onClose}>Hủy</button><button className="button primary" disabled={action.busy||(mode==='role'&&role!=='admin'&&!catalog)}>{action.busy && <Spinner/>}{mode === 'role' || mode === 'disable' ? 'Xác nhận' : 'Lưu tài khoản'}</button></div>
  </form>;
}

type Report = {hours:{hour:string; FREE:number; SLOW:number; JAM:number; unknown:number; samples:number}[]; valid_samples:number; unknown_samples:number};
export function ReportPanel({segments,allowExport}:{segments:Segment[];allowExport:boolean}) {
  const [road,setRoad] = useState(segments.find(s => s.active)?.id || 0);
  const [direction,setDirection] = useState<Direction>('forward');
  const [start,setStart] = useState(localInput(new Date(Date.now()-86400000).toISOString()));
  const [end,setEnd] = useState(localInput());
  const [query,setQuery] = useState('');
  const [report,setReport] = useState<Report|null>(null);
  const action = useAction();
  function submit(e:React.FormEvent) {
    e.preventDefault();
    void action.run(async () => {
      const next = new URLSearchParams({segment_id:String(road),direction,start:iso(start),end:iso(end)}).toString();
      setReport(await api<Report>(`/management/traffic-report?${next}`));
      setQuery(next);
    },'Đã cập nhật thống kê.');
  }
  async function download() {
    const response = await fetch(`/api/management/traffic-report/export?${query}&format=csv`,{credentials:'same-origin'});
    if(!response.ok){const error = await response.json();throw new Error(error.detail || 'Không tạo được tệp báo cáo.');}
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'smarteye-thong-ke-theo-gio.csv';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  return <section className="card">
    <h2>Thống kê ùn tắc theo giờ</h2><p className="muted">Dữ liệu quan trắc theo chiều đường và giờ Việt Nam.</p><Feedback error={action.error} success={action.success}/>
    <form onSubmit={submit}>
      <RoadFields segments={segments} road={road} direction={direction} onRoad={id => {setRoad(id);setDirection('forward');}} onDirection={setDirection}/>
      <div className="two-columns"><label className="field">Từ thời điểm<input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)}/></label><label className="field">Đến thời điểm<input type="datetime-local" required min={start} max={localInput()} value={end} onChange={e => setEnd(e.target.value)}/></label></div>
      <div className="workflow-buttons"><button className="button primary" disabled={action.busy || !road}>Thống kê</button>{report && allowExport && <button type="button" className="button" disabled={action.busy} onClick={() => action.run(download,'Đã tạo tệp báo cáo.')}><Download size={16}/>Xuất báo cáo CSV</button>}</div>
    </form>
    {report && <><p>{report.valid_samples} bản ghi hợp lệ · {report.unknown_samples} chưa phân loại</p>{report.hours.length ? <div className="table-wrap"><table><thead><tr><th>Khung giờ</th><th>Thông thoáng</th><th>Bình thường</th><th>Ùn tắc</th><th>Chưa xác định</th><th>Tổng mẫu</th></tr></thead><tbody>{report.hours.map(h => <tr key={h.hour}><td>{h.hour}</td><td>{h.FREE}</td><td>{h.SLOW}</td><td>{h.JAM}</td><td>{h.unknown}</td><td>{h.samples}</td></tr>)}</tbody></table></div> : <Empty><p>Không có bản ghi phù hợp với khoảng thời gian đã chọn.</p></Empty>}</>}
  </section>;
}

type AuditEvent = {id:number; user_id:number|null; action:string; detail:string; created_at:string; event_id:string; request_id:string; service:string; level:string};
type Operation = {checked_at:string;services:{name:string;state:string;checked_at:string}[];ingestion:{total:number;fresh:number;stale:number;error:number;unknown:number;disabled:number;last_received_at:string|null};sources:{id:number;name:string;state:string;last_received_at:string|null;last_error:string|null}[]};
export function SystemPanel({onSource}:{onSource?:(id:number)=>void}) {
  const [q,setQ] = useState('');
  const [level,setLevel] = useState('');
  const [service,setService] = useState('');
  const [start,setStart] = useState('');
  const [end,setEnd] = useState('');
  const [query,setQuery] = useState('');
  const [detail,setDetail] = useState<AuditEvent|null>(null);
  const status = useRemote<Operation|null>('/management/operations',null);
  const logs = useRemote<AuditEvent[]>(`/management/events?${query}`,[]);
  const action = useAction();
  return <>
    <section className="card">
      <div className="section-title"><ShieldCheck size={18}/><h2>Trạng thái dịch vụ</h2><button className="button small" onClick={status.reload}>Kiểm tra lại</button></div>
      <Loading loading={status.loading} error={status.error} onRetry={status.reload}>{status.data && <>
        <div className="workflow-grid">{status.data.services.map(s => <article key={s.name}><span>{s.name}</span><State value={s.state}/><small>{dateTime(s.checked_at)}</small></article>)}</div>
        <h3 className="workflow-section">Trạng thái tiếp nhận dữ liệu</h3>
        <p>{status.data.ingestion.total} nguồn · {status.data.ingestion.fresh} mới · {status.data.ingestion.stale} cũ · {status.data.ingestion.error} lỗi · {status.data.ingestion.disabled} đã tắt</p>
        <p className="micro">{status.data.ingestion.last_received_at ? `Nhận gần nhất ${dateTime(status.data.ingestion.last_received_at)}` : 'Chưa có lượt tiếp nhận.'}</p>
        {status.data.sources.map(s => <div className="segment-row" key={s.id}><span>{s.name}<small>{s.last_error || (s.last_received_at ? dateTime(s.last_received_at) : 'Chưa có dữ liệu')}</small></span><State value={s.state}/>{onSource&&<button className="button small" onClick={() => onSource(s.id)}>Xem nguồn</button>}</div>)}
      </>}</Loading>
    </section>
    <section className="card workflow-section">
      <h2>Nhật ký hoạt động</h2><Feedback error={action.error}/>
      <form className="workflow-filter" onSubmit={e => {e.preventDefault(); setQuery(new URLSearchParams(Object.entries({q,level,service,start:start?iso(start):'',end:end?iso(end):''}).filter(([,v]) => v)).toString()); logs.reload();}}>
        <label className="field">Mã sự kiện hoặc từ khóa<input value={q} maxLength={100} onChange={e => setQ(e.target.value)}/></label>
        <label className="field">Từ thời điểm<input type="datetime-local" value={start} onChange={e => setStart(e.target.value)}/></label>
        <label className="field">Đến thời điểm<input type="datetime-local" value={end} min={start} onChange={e => setEnd(e.target.value)}/></label>
        <label className="field">Dịch vụ<select value={service} onChange={e => setService(e.target.value)}><option value="">Tất cả</option><option value="application">Ứng dụng</option><option value="workflow">Nghiệp vụ</option><option value="ingestion">Tiếp nhận</option><option value="forecast">Dự báo</option></select></label>
        <label className="field">Mức độ<select value={level} onChange={e => setLevel(e.target.value)}><option value="">Tất cả</option><option value="info">Thông tin</option><option value="warning">Cảnh báo</option><option value="error">Lỗi</option></select></label>
        <button className="button primary">Áp dụng</button><button type="button" className="button" onClick={() => {setQ('');setStart('');setEnd('');setService('');setLevel('');setQuery('');logs.reload();}}>Xóa bộ lọc</button>
      </form>
      <Loading loading={logs.loading} error={logs.error} onRetry={logs.reload}>{logs.data.length ? <div className="table-wrap"><table><thead><tr><th>Thời điểm</th><th>Hành động</th><th>Mức độ</th><th></th></tr></thead><tbody>{logs.data.map(row => <tr key={row.id}><td>{dateTime(row.created_at)}</td><td>{row.action}</td><td>{row.level}</td><td><button className="button small" onClick={() => action.run(async () => setDetail(await api<AuditEvent>(`/management/events/${row.id}`)))}>Chi tiết</button></td></tr>)}</tbody></table></div> : <Empty><p>Không có nhật ký phù hợp.</p></Empty>}</Loading>
      {detail && <Modal title="Chi tiết sự kiện" onClose={() => setDetail(null)}><dl className="workflow-details"><dt>Thời điểm</dt><dd>{dateTime(detail.created_at)}</dd><dt>Sự kiện</dt><dd>{detail.action}</dd><dt>Dịch vụ</dt><dd>{detail.service}</dd><dt>Tác nhân</dt><dd>{detail.user_id ?? 'Hệ thống'}</dd><dt>Mã sự kiện</dt><dd>{detail.event_id || detail.id}</dd><dt>Mã yêu cầu</dt><dd>{detail.request_id || 'Chưa có'}</dd><dt>Chi tiết</dt><dd>{detail.detail || 'Chưa có mô tả bổ sung.'}</dd></dl></Modal>}
    </section>
  </>;
}
