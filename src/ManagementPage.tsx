import {can} from './permissions';
import {useState} from 'react';
import {Activity, Bell, Camera, MessageSquare, Plus, SlidersHorizontal} from 'lucide-react';
import {api, json} from './api';
import {Empty, Modal, Notice, Spinner} from './components';
import {IncidentDetails} from './IncidentsPage';
import {type User, type Segment, dateTime} from './types';
import {
  type CurrentRoad, type Direction, type Incident, type Rule, type Warning,
  CurrentConditions, trafficLabel, Feedback, History, Loading, RoadFields, State, iso, kinds, localInput,
  midpoint, severityText, statusText, useAction, useRemote,
} from './business';

const incidentStates = ['pending', 'verifying', 'processing', 'resolved', 'rejected'];
const warningStates = ['pending_verification', 'pending_publication', 'published', 'ended', 'cancelled'];
const metrics = {score: ['Chỉ số mật độ', 'ratio', 1], speed_kmh: ['Vận tốc', 'km/h', 200], flow_per_minute: ['Lưu lượng', 'vehicles/min', 10000]} as const;
type MetricName = keyof typeof metrics;

function Monitor({segments}: {segments: Segment[]}) {
  const [segment, setSegment] = useState(segments[0]?.id || 0);
  const [direction, setDirection] = useState<Direction>('forward');
  const [cameraErrors, setCameraErrors] = useState<number[]>([]);
  const view = useRemote<{
    current: CurrentRoad | null;
    sources: {id: number; name: string; state: string; last_received_at: string | null}[];
    cameras: {id: number; name: string; url: string | null; format: string; checked_at: string | null; message: string}[];
    warnings: {id: number; content: string}[]; series: {at: string; metrics: {count?: number; flow_per_minute?: number; speed_kmh?: number; state?: string}}[];
    errors: Record<string, string>; checked_at: string;
  } | null>(`/management/monitor?segment_id=${segment}&direction=${direction}`, null);
  if (!segment) return <section className="card"><Empty><p>Chưa có tuyến đường được phân công.</p></Empty></section>;
  const data = view.data;
  return <>
    <section className="card">
      <div className="section-title"><Activity size={19}/><h2>Bảng giám sát</h2><button className="button small" onClick={() => {setCameraErrors([]); view.reload();}}>Làm mới</button></div>
      <RoadFields segments={segments} road={segment} direction={direction} onRoad={id => {setSegment(id); setDirection('forward');}} onDirection={setDirection}/>
      <Loading loading={view.loading} error={view.error} onRetry={view.reload}>
        {data && <><p className="micro">Kiểm tra lúc {dateTime(data.checked_at)}</p><CurrentConditions value={data.current}/></>}
      </Loading>
    </section>
    {data && !view.loading && !view.error && <>
      <div className="two-columns workflow-section">

        <section className="card"><h2>Cảnh báo đã phát hành</h2>{data.errors.warnings && <Notice kind="error">{data.errors.warnings}</Notice>}
          {data.warnings.length ? data.warnings.map(w => <p key={w.id}>{w.content}</p>) : <p className="muted">Hiện chưa có cảnh báo.</p>}
        </section>
      </div>
      <section className="card workflow-section"><h2>Diễn biến trong một giờ gần đây</h2>
        {data.series.length ? <div className="table-wrap"><table><thead><tr><th>Thời điểm</th><th>Số xe</th><th>Lưu lượng (xe/phút)</th><th>Vận tốc (km/h)</th><th>Ùn tắc</th></tr></thead><tbody>{data.series.slice(-60).map((row, index) => <tr key={`${row.at}-${index}`}><td>{dateTime(row.at)}</td><td>{row.metrics.count ?? '—'}</td><td>{row.metrics.flow_per_minute ?? '—'}</td><td>{row.metrics.speed_kmh ?? '—'}</td><td>{trafficLabel(row.metrics.state)}</td></tr>)}</tbody></table></div> : <p className="muted">Chưa có dữ liệu phù hợp.</p>}
      </section>
      <div className="two-columns workflow-section">
        <section className="card"><h2>Trạng thái dữ liệu</h2>{data.errors.sources && <Notice kind="error">{data.errors.sources}</Notice>}
          {data.sources.length ? data.sources.map(s => <div className="segment-row" key={s.id}><span>{s.name}<small>{s.last_received_at ? dateTime(s.last_received_at) : 'Chưa có lần nhận'}</small></span><State value={s.state}/></div>) : <p className="muted">Chưa cấu hình nguồn.</p>}
        </section>
        <section className="card"><div className="section-title"><Camera size={18}/><h2>Camera giao thông</h2></div>
          {data.cameras.length ? data.cameras.map(c => <article className="workflow-camera" key={c.id}><b>{c.name}</b>
            {cameraErrors.includes(c.id) || !c.url ? <p>Mất kết nối nguồn dữ liệu hoặc chưa có hình ảnh phù hợp.</p> :
              c.format === 'image' ? <img src={c.url} alt={c.name} onError={() => setCameraErrors(ids => [...ids, c.id])}/> :
              <video controls preload="metadata" src={c.url} onError={() => setCameraErrors(ids => [...ids, c.id])}/>}
            <small>{c.message}{c.checked_at && ` Kiểm tra kết nối ${dateTime(c.checked_at)}.`}</small>
          </article>) : <p className="muted">Chưa có camera được cấu hình và bật.</p>}
        </section>
      </div>
    </>}
  </>;
}

function RecordFilters({states, onSubmit}: {states: string[]; onSubmit: (query: string) => void}) {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  return <form className="workflow-filter" onSubmit={event => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (status) params.set('status', status);
    if (start) params.set('start', iso(start));
    if (end) params.set('end', iso(end));
    onSubmit(params.toString());
  }}>
    <label className="field">Từ khóa<input value={q} maxLength={100} onChange={e => setQ(e.target.value)}/></label>
    <label className="field">Trạng thái<select value={status} onChange={e => setStatus(e.target.value)}><option value="">Tất cả</option>{states.map(s => <option key={s} value={s}>{statusText[s]}</option>)}</select></label>
    <label className="field">Từ thời điểm<input type="datetime-local" value={start} onChange={e => setStart(e.target.value)}/></label>
    <label className="field">Đến thời điểm<input type="datetime-local" value={end} min={start} onChange={e => setEnd(e.target.value)}/></label>
    <button className="button primary">Tìm kiếm</button>
  </form>;
}

function IncidentQueue({user, segments}: {user: User; segments: Segment[]}) {
  const [filter, setFilter] = useState('');
  const [detail, setDetail] = useState<Incident | null>(null);
  const [edit, setEdit] = useState(false);
  const view = useRemote<Incident[]>(`/management/incidents?${filter}`, []);
  const action = useAction();
  function reload() {view.reload();}
  return <section className="card">
    <h2>Quản lý phản ánh</h2><RecordFilters states={incidentStates} onSubmit={q => {setFilter(q); reload();}}/>
    <Feedback error={action.error}/>
    <Loading loading={view.loading} error={view.error} onRetry={reload}>
      {view.data.length ? <div className="workflow-list">{view.data.map(item => <button key={item.id} className="workflow-list-item" onClick={() => action.run(async () => {setEdit(false); setDetail(await api<Incident>(`/incidents/${item.id}`));})}>
        <div><b>{item.code} · {segments.find(s => s.id === item.segment_id)?.name}</b><p>{item.content}</p><small>{dateTime(item.created_at)}</small></div><State value={item.status}/>
      </button>)}</div> : <Empty><p>Không có phản ánh phù hợp.</p></Empty>}
    </Loading>
    {detail && <Modal title={`Phản ánh ${detail.code}`} onClose={() => setDetail(null)}>
      <IncidentDetails item={detail}/>
      <Feedback error={action.error} success={action.success}/>
      {edit ? <IncidentEditForm key={detail.revision} item={detail} onCancel={() => setEdit(false)} onSave={item => {setDetail(item); setEdit(false); reload();}}/> :
        <IncidentActions item={detail} user={user} onEdit={() => setEdit(true)} onChange={item => {setDetail(item); reload();}}/>}
    </Modal>}
  </section>;
}

function IncidentActions({item, user, onEdit, onChange}: {item: Incident; user: User; onEdit: () => void; onChange: (value: Incident) => void}) {
  const [note, setNote] = useState('');
  const [conclusion, setConclusion] = useState('valid');
  const action = useAction();
  const mine = item.assignee_id === user.id;
  async function apply(name: string, requireNote = true) {
    await action.run(async () => {
      if (requireNote && note.trim().length < 5) throw new Error('Vui lòng ghi rõ lý do hoặc kết quả xử lý.');
      const next = await api<Incident>(`/management/incidents/${item.id}/${name}`, json({
        revision: item.revision, note: requireNote ? note : 'Quản lý đã tiếp nhận phản ánh.',
        ...(name === 'verify' ? {conclusion} : {}),
      }));
      onChange(next);
      setNote('');
    });
  }
  if (item.status === 'pending') return can(user,'incidents.accept')?<><Feedback error={action.error}/><button className="button primary" disabled={action.busy} onClick={() => apply('accept', false)}>Tiếp nhận</button></>:null;
  if (!mine || !['verifying', 'processing'].includes(item.status)) return null;
  const verify=item.status==='verifying'&&can(user,'incidents.verify');
  const reject=item.status==='verifying'&&item.verification==='invalid'&&can(user,'incidents.reject');
  const progress=item.status==='processing'&&can(user,'incidents.progress');
  const resolve=item.status==='processing'&&can(user,'incidents.resolve');
  const edit=can(user,'incidents.edit');
  if(!verify&&!reject&&!progress&&!resolve&&!edit)return null;
  return <div className="workflow-actions">
    <Feedback error={action.error} success={action.success}/>
    {verify && <label className="field">Kết luận<select value={conclusion} onChange={e => setConclusion(e.target.value)}><option value="valid">Hợp lệ</option><option value="invalid">Không hợp lệ</option><option value="insufficient">Chưa đủ căn cứ</option></select></label>}
    {(verify||reject||progress||resolve)&&<label className="field">Ghi chú hoặc căn cứ xử lý<textarea rows={3} maxLength={2000} value={note} onChange={e => setNote(e.target.value)}/></label>}
    <div className="workflow-buttons">
      {edit&&<button className="button" onClick={onEdit}>Sửa thông tin sự cố</button>}
      {verify && <button className="button primary" disabled={action.busy} onClick={() => apply('verify')}>Lưu xác minh</button>}
      {reject && <button className="button" disabled={action.busy} onClick={() => {if (window.confirm('Từ chối phản ánh này?')) void apply('reject');}}>Từ chối</button>}
      {progress && <button className="button" disabled={action.busy} onClick={() => apply('progress')}>Cập nhật tiến độ</button>}{resolve && <button className="button primary" disabled={action.busy} onClick={() => {if (window.confirm('Xác nhận đã xử lý xong phản ánh?')) void apply('resolve');}}>Hoàn tất</button>}
    </div>
  </div>;
}

function IncidentEditForm({item, onCancel, onSave}: {item: Incident; onCancel: () => void; onSave: (value: Incident) => void}) {
  const [content, setContent] = useState(item.content);
  const [kind, setKind] = useState(item.kind);
  const [when, setWhen] = useState(localInput(item.occurred_at));
  const [position, setPosition] = useState(item.position);
  const action = useAction();
  return <form onSubmit={event => {event.preventDefault(); void action.run(async () => onSave(await api<Incident>(`/management/incidents/${item.id}`, json({content, kind, position, occurred_at: iso(when), revision: item.revision}, 'PATCH'))));}}>
    <Feedback error={action.error}/>
    <label className="field">Loại sự cố<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label className="field">Thời điểm xảy ra<input type="datetime-local" value={when} onChange={e => setWhen(e.target.value)} required max={localInput()}/></label>
    <PositionFields value={position} onChange={setPosition}/>
    <label className="field">Thông tin sự cố<textarea value={content} onChange={e => setContent(e.target.value)} minLength={10} maxLength={2000} required rows={3}/></label>
    <div className="workflow-buttons"><button type="button" className="button" onClick={onCancel}>Hủy</button><button className="button primary" disabled={action.busy}>Lưu sự cố</button></div>
  </form>;
}

function PositionFields({value, onChange}: {value: number[]; onChange: (value: number[]) => void}) {
  return <div className="two-columns">
    <label className="field">Vĩ độ<input type="number" step="any" min="20.5" max="21.5" value={value[0]} onChange={e => onChange([Number(e.target.value), value[1]])} required/></label>
    <label className="field">Kinh độ<input type="number" step="any" min="105.2" max="106.2" value={value[1]} onChange={e => onChange([value[0], Number(e.target.value)])} required/></label>
  </div>;
}

function WarningQueue({segments,user}: {segments: Segment[];user:User}) {
  const [filter, setFilter] = useState('');
  const [detail, setDetail] = useState<Warning | null>(null);
  const [editing, setEditing] = useState(false);
  const view = useRemote<Warning[]>(`/management/warnings?${filter}`, []);
  const action = useAction();
  return <section className="card">
    <div className="section-title"><Bell size={19}/><h2>Quản lý cảnh báo</h2>{can(user,'publication.add')&&<button className="button primary small" onClick={() => {setDetail(null); setEditing(true);}}><Plus size={16}/>Tạo cảnh báo</button>}</div>
    <RecordFilters states={warningStates} onSubmit={q => {setFilter(q); view.reload();}}/>
    <Feedback error={action.error}/>
    <Loading loading={view.loading} error={view.error} onRetry={view.reload}>
      {view.data.length ? <div className="workflow-list">{view.data.map(w => <button key={w.id} className="workflow-list-item" onClick={() => action.run(async () => {setEditing(false); setDetail(await api<Warning>(`/management/warnings/${w.id}`));})}>
        <div><b>CB-{w.id} · {segments.find(s => s.id === w.segment_id)?.name}</b><p>{w.content}</p><small>Phiên bản {w.content_version} · Mức {severityText[w.severity]}</small></div><State value={w.status}/>
      </button>)}</div> : <Empty><p>Không có cảnh báo phù hợp.</p></Empty>}
    </Loading>
    {editing ? <Modal title={detail ? 'Cập nhật cảnh báo' : 'Tạo cảnh báo'} onClose={() => setEditing(false)}>
      <WarningForm item={detail} segments={segments} onCancel={() => setEditing(false)} onSave={w => {setDetail(w); setEditing(false); view.reload();}}/>
    </Modal> : detail && <Modal title={`Cảnh báo CB-${detail.id}`} onClose={() => setDetail(null)}>
      <div className="workflow-item-head"><State value={detail.status}/><span>Phiên bản {detail.content_version}</span></div>
      <p>{detail.content}</p><p className="micro">Mức {severityText[detail.severity]} · Áp dụng từ {dateTime(detail.start_at)}{detail.end_at && ` đến ${dateTime(detail.end_at)}`}</p>
      {detail.public_snapshot && detail.content_version !== detail.public_snapshot.version && <Notice>Người dùng đang xem phiên bản {detail.public_snapshot.version}. Phiên bản mới cần xác minh và phát hành.</Notice>}
      {detail.rule_id && <p className="micro">Đề xuất từ quy tắc #{detail.rule_id}, phiên bản {detail.rule_version}</p>}
      <WarningActions user={user} item={detail} onEdit={() => setEditing(true)} onChange={w => {setDetail(w); view.reload();}}/>
      <h3>Lịch sử xử lý</h3><History entries={detail.history}/>
    </Modal>}
  </section>;
}

function WarningForm({item, segments, onCancel, onSave}: {item: Warning | null; segments: Segment[]; onCancel: () => void; onSave: (value: Warning) => void}) {
  const [road, setRoad] = useState(item?.segment_id || segments[0]?.id || 0);
  const [direction, setDirection] = useState<Direction>(item?.direction || 'forward');
  const [kind, setKind] = useState(item?.kind || 'congestion');
  const [position, setPosition] = useState(item?.position || midpoint(segments.find(s => s.id === road)));
  const [severity, setSeverity] = useState(item?.severity || 'medium');
  const [content, setContent] = useState(item?.content || '');
  const [start, setStart] = useState(localInput(item?.start_at));
  const [end, setEnd] = useState(item?.end_at ? localInput(item.end_at) : localInput(new Date(Date.now()+7200000).toISOString()));
  const [incident, setIncident] = useState(item?.incident_id || 0);
  const [reason, setReason] = useState('');
  const action = useAction();
  return <form onSubmit={event => {
    event.preventDefault();
    void action.run(async () => {
      const fields = {segment_id: road, direction, kind, position, severity, content, start_at: iso(start), end_at: end ? iso(end) : null, incident_id: incident || null, duplicate_reason: reason};
      const next = await api<Warning>(item ? `/management/warnings/${item.id}` : '/management/warnings', json(item ? {...fields, revision: item.revision} : fields, item ? 'PATCH' : 'POST'));
      onSave(next);
    });
  }}>
    <Feedback error={action.error}/>
    {item ? <p>{segments.find(s => s.id === road)?.name} · {direction === 'forward' ? 'Chiều đi' : 'Chiều về'}</p> :
      <RoadFields segments={segments} road={road} direction={direction} onRoad={id => {setRoad(id); setDirection('forward'); setPosition(midpoint(segments.find(s => s.id === id)));}} onDirection={setDirection}/>}
    <div className="two-columns">
      <label className="field">Loại cảnh báo<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(kinds).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="field">Mức cảnh báo<select value={severity} onChange={e => setSeverity(e.target.value)}>{Object.entries(severityText).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    </div>
    <PositionFields value={position} onChange={setPosition}/>
    <div className="two-columns"><label className="field">Bắt đầu<input type="datetime-local" value={start} onChange={e => setStart(e.target.value)} required/></label><label className="field">Tự hết hiệu lực lúc<input type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} min={start} required/></label></div>
    <label className="field">Nội dung cảnh báo<textarea value={content} onChange={e => setContent(e.target.value)} required minLength={10} maxLength={2000} rows={3}/></label>
    <label className="field">Số phản ánh liên quan (nếu có)<input type="number" min={1} value={incident || ''} onChange={e => setIncident(Number(e.target.value))}/></label>
    {!item && <label className="field">Lý do tạo thêm nếu đã có cảnh báo tương tự<input value={reason} onChange={e => setReason(e.target.value)} maxLength={1000}/></label>}
    <div className="workflow-buttons"><button className="button" type="button" onClick={onCancel}>Hủy</button><button className="button primary" disabled={action.busy || !road}>{action.busy && <Spinner/>}Lưu chờ xác minh</button></div>
  </form>;
}

function WarningActions({item,user,onEdit,onChange}: {item: Warning;user:User; onEdit: () => void; onChange: (value: Warning) => void}) {
  const [note, setNote] = useState('');
  const [conclusion, setConclusion] = useState('valid');
  const action = useAction();
  if (item.public_snapshot) return <Notice>Cảnh báo đã phát hành chỉ để xem và tự hết hiệu lực theo giờ đã đặt.</Notice>;
  if (['ended','cancelled'].includes(item.status)) return null;
  const verify=item.status==='pending_verification'&&can(user,'publication.verify');
  const publish=item.status==='pending_publication'&&can(user,'publication.publish');
  const edit=can(user,'publication.edit');
  const cancel=can(user,'publication.cancel');
  if(!verify&&!publish&&!edit&&!cancel)return null;
  function apply(name: string) {
    void action.run(async () => {
      if (name !== 'publish' && note.trim().length < 5) throw new Error('Vui lòng nhập lý do hoặc căn cứ.');
      const next = await api<Warning>(`/management/warnings/${item.id}/${name}`, json({
        revision: item.revision, ...(name === 'publish' ? {} : {note}), ...(name === 'verify' ? {conclusion} : {}),
      }));
      onChange(next);
      setNote('');
    });
  }
  return <div className="workflow-actions">
    <Feedback error={action.error} success={action.success}/>
    {verify && <label className="field">Kết luận<select value={conclusion} onChange={e => setConclusion(e.target.value)}><option value="valid">Hợp lệ</option><option value="invalid">Không hợp lệ</option><option value="insufficient">Chưa đủ căn cứ</option></select></label>}
    {(verify||cancel)&&<label className="field">Căn cứ hoặc lý do<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} rows={2}/></label>}
    <div className="workflow-buttons">
      {edit&&<button className="button" onClick={onEdit}>Sửa bản nháp</button>}
      {verify && <button className="button primary" disabled={action.busy} onClick={() => apply('verify')}>Lưu xác minh</button>}
      {publish && <button className="button primary" disabled={action.busy} onClick={() => {if (window.confirm('Phát hành cảnh báo và gửi thông báo cho người đã bật nhận?')) apply('publish');}}>Phát hành</button>}
      {cancel&&<button className="button danger-text" disabled={action.busy} onClick={() => {if (window.confirm('Hủy bản nháp này?')) apply('cancel');}}>Hủy bản nháp</button>}
    </div>
  </div>;
}

function RuleList({segments,user}: {segments: Segment[];user:User}) {
  const [q, setQ] = useState('');
  const [metric, setMetric] = useState('');
  const [state, setState] = useState('');
  const [filter, setFilter] = useState('');
  const [editor, setEditor] = useState<Rule | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<Rule | null>(null);
  const [reason, setReason] = useState('');
  const view = useRemote<Rule[]>(`/management/rules?${filter}`, []);
  const action = useAction();
  function command(item: Rule, name: string, fields: Record<string, unknown> = {}) {
    return action.run(async () => {
      await api(`/management/rules/${item.id}/${name}`, json({revision: item.revision, ...fields}));
      setDeleting(null);
      view.reload();
    });
  }
  return <section className="card">
    <div className="section-title"><SlidersHorizontal size={19}/><h2>Quy tắc cảnh báo</h2>{can(user,'rules.add')&&<button className="button primary small" onClick={() => setEditor(null)}><Plus size={16}/>Thêm quy tắc</button>}</div>
    <p>Quy tắc đủ điều kiện tạo đề xuất để Quản lý xác minh và quyết định phát hành.</p>
    <form className="workflow-filter" onSubmit={e => {e.preventDefault(); setFilter(new URLSearchParams(Object.entries({q, metric, active: state}).filter(([,v]) => v)).toString()); view.reload();}}>
      <label className="field">Tên quy tắc<input value={q} maxLength={100} onChange={e => setQ(e.target.value)}/></label>
      <label className="field">Chỉ số<select value={metric} onChange={e => setMetric(e.target.value)}><option value="">Tất cả</option>{Object.entries(metrics).map(([key,[label]]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="field">Trạng thái<select value={state} onChange={e => setState(e.target.value)}><option value="">Tất cả</option><option value="true">Đang bật</option><option value="false">Đã tắt</option></select></label>
      <button className="button primary">Tìm kiếm</button>
    </form>
    <Feedback error={action.error} success={action.success}/>
    <Loading loading={view.loading} error={view.error} onRetry={view.reload}>
      {view.data.length ? <div className="workflow-list">{view.data.map(item => <article key={item.id} className="workflow-row">
        <div className="workflow-item-head"><b>{item.name}</b><span className="workflow-state">{item.active ? 'Đang bật' : 'Đã tắt'}</span></div>
        <p>{segments.find(s => s.id === item.segment_id)?.name} · {metrics[item.metric as MetricName][0]} {item.operator} {item.threshold} {item.unit} · {item.window_minutes} phút</p>
        <small>Phiên bản {item.content_version} · {item.tested ? 'Đã kiểm tra' : 'Chưa kiểm tra'}</small>
        <div className="workflow-buttons">
          {can(user,'rules.edit')&&<button className="button small" onClick={() => setEditor(item)}>Sửa quy tắc</button>}
          {can(user,'rules.test')&&<button className="button small" disabled={action.busy} onClick={() => command(item, 'test')}>Kiểm tra quy tắc</button>}
          {can(user,'rules.toggle')&&<button className="button small" disabled={action.busy} onClick={() => {if (window.confirm(item.active ? 'Tắt quy tắc này?' : 'Bật quy tắc này?')) void command(item, 'toggle', {active: !item.active, confirmed: true});}}>{item.active ? 'Tắt' : 'Bật'}</button>}
          {can(user,'rules.delete')&&<button className="button small danger-text" onClick={() => {setReason(''); setDeleting(item);}}>Xóa quy tắc</button>}
        </div>
        <details><summary>Lịch sử quy tắc</summary><History entries={item.history}/></details>
      </article>)}</div> : <Empty><p>Không có quy tắc phù hợp.</p></Empty>}
    </Loading>
    {editor !== undefined && <Modal title={editor ? 'Sửa quy tắc' : 'Thêm quy tắc'} onClose={() => setEditor(undefined)}>
      <RuleForm item={editor} segments={segments} onClose={() => setEditor(undefined)} onSaved={() => {setEditor(undefined); view.reload();}}/>
    </Modal>}
    {deleting && <Modal title="Xác nhận xóa quy tắc" onClose={() => setDeleting(null)}>
      <p>Quy tắc sẽ dừng đánh giá. Các cảnh báo đã tạo giữ lịch sử và phiên bản quy tắc.</p>
      <Feedback error={action.error}/>
      <form onSubmit={e => {e.preventDefault(); void command(deleting, 'delete', {note: reason});}}><label className="field">Lý do xóa<textarea value={reason} onChange={e => setReason(e.target.value)} required minLength={5} maxLength={2000}/></label><button className="button primary" disabled={action.busy}>Xác nhận xóa</button></form>
    </Modal>}
  </section>;
}

function RuleForm({item, segments, onClose, onSaved}: {item: Rule | null; segments: Segment[]; onClose: () => void; onSaved: () => void}) {
  const [name, setName] = useState(item?.name || '');
  const [road, setRoad] = useState(item?.segment_id || segments[0]?.id || 0);
  const [direction, setDirection] = useState<Direction>(item?.direction || 'forward');
  const [metric, setMetric] = useState<MetricName>((item?.metric as MetricName) || 'score');
  const [operator, setOperator] = useState(item?.operator || 'gte');
  const [threshold, setThreshold] = useState(item?.threshold ?? 0.6);
  const [windowMinutes, setWindow] = useState(item?.window_minutes ?? 5);
  const [start, setStart] = useState(item?.start_hour ?? 0);
  const [end, setEnd] = useState(item?.end_hour ?? 24);
  const [severity, setSeverity] = useState(item?.severity || 'medium');
  const action = useAction();
  return <form onSubmit={e => {
    e.preventDefault();
    void action.run(async () => {
      const body = {name, segment_id: road, direction, metric, operator, threshold, unit: metrics[metric][1], window_minutes: windowMinutes, start_hour: start, end_hour: end, severity};
      await api(item ? `/management/rules/${item.id}` : '/management/rules', json(item ? {...body, revision: item.revision} : body, item ? 'PATCH' : 'POST'));
      onSaved();
    });
  }}>
    <Feedback error={action.error}/>
    <label className="field">Tên quy tắc<input value={name} onChange={e => setName(e.target.value)} required minLength={3} maxLength={120}/></label>
    <RoadFields segments={segments} road={road} direction={direction} onRoad={id => {setRoad(id); setDirection('forward');}} onDirection={setDirection}/>
    <div className="two-columns"><label className="field">Chỉ số<select value={metric} onChange={e => {setMetric(e.target.value as MetricName); setThreshold(0);}}>{Object.entries(metrics).map(([key,[label]]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label className="field">So sánh<select value={operator} onChange={e => setOperator(e.target.value)}><option value="gte">Lớn hơn hoặc bằng</option><option value="gt">Lớn hơn</option><option value="lte">Nhỏ hơn hoặc bằng</option><option value="lt">Nhỏ hơn</option></select></label></div>
    <div className="two-columns"><label className="field">Ngưỡng ({metrics[metric][1]})<input type="number" min={0} max={metrics[metric][2]} step="any" value={threshold} onChange={e => setThreshold(Number(e.target.value))} required/></label><label className="field">Khoảng đánh giá (phút)<input type="number" min={1} max={60} value={windowMinutes} onChange={e => setWindow(Number(e.target.value))} required/></label></div>
    <div className="two-columns"><label className="field">Từ giờ<input type="number" min={0} max={23} value={start} onChange={e => setStart(Number(e.target.value))}/></label><label className="field">Đến giờ<input type="number" min={1} max={24} value={end} onChange={e => setEnd(Number(e.target.value))}/></label></div>
    <label className="field">Mức cảnh báo<select value={severity} onChange={e => setSeverity(e.target.value)}>{Object.entries(severityText).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <div className="workflow-buttons"><button type="button" className="button" onClick={onClose}>Hủy</button><button className="button primary" disabled={action.busy || !road}>Lưu quy tắc</button></div>
  </form>;
}

export default function ManagementPage({user, segments}: {user: User; segments: Segment[]}) {
  const [chosen, setTab] = useState('monitor');
  const scoped = segments.filter(s => s.active && (!user.managed_segment_ids || user.managed_segment_ids.includes(s.id)));
  const tabs = [{id:'monitor', permission:'monitor.view', label:'Giám sát', Icon:Activity}, {id:'incidents', permission:'incidents.view', label:'Quản lý phản ánh', Icon:MessageSquare}, {id:'warnings', permission:'publication.view', label:'Quản lý cảnh báo', Icon:Bell}, {id:'rules', permission:'rules.view', label:'Quy tắc cảnh báo', Icon:SlidersHorizontal}].filter(item=>can(user,item.permission));
  const tab=tabs.some(item=>item.id===chosen)?chosen:tabs[0]?.id;
  return <>
    <div className="page-heading"><div><div className="eyebrow">DÀNH CHO QUẢN LÝ</div><h1>Giám sát & xử lý<span>.</span></h1><p>Theo dõi số liệu, tiếp nhận sự cố và xác minh cảnh báo trước khi công bố.</p></div></div>
    <div className="tabs workflow-tabs">{tabs.map(({id,label,Icon}) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}><Icon size={17}/>{label}</button>)}</div>
    {tab === 'monitor' && <Monitor segments={scoped}/>}
    {tab === 'incidents' && <IncidentQueue user={user} segments={scoped}/>}
    {tab === 'warnings' && <WarningQueue segments={scoped} user={user}/>}
    {tab === 'rules' && <RuleList segments={scoped} user={user}/>}
  </>;
}
