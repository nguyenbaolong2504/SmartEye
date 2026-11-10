import {useEffect, useState} from 'react';
import {Bell, ChevronRight} from 'lucide-react';
import {api} from './api';
import {Empty, Modal} from './components';
import {Feedback, Loading, kinds, severityText, useAction, useRemote, type Direction} from './business';
import {type Segment,dateTime} from './types';

type PublishedWarning = {id:number; segment_id:number; direction:Direction; kind:string; position:number[]; severity:string; content:string; start_at:string; end_at:string|null; version:number; published_at:string; upcoming:boolean};

function WarningDetail({value, segments, onClose}:{value:PublishedWarning;segments:Segment[];onClose:()=>void}) {
  return <Modal title={`Cảnh báo CB-${value.id}`} onClose={onClose}>
    <h3>{kinds[value.kind]} · {segments.find(s => s.id === value.segment_id)?.name || 'Tuyến đường theo dõi'}</h3>
    <p>{value.content}</p>
    <dl className="workflow-details">
      <dt>Mức cảnh báo</dt><dd>{severityText[value.severity]}</dd>
      <dt>Chiều di chuyển</dt><dd>{value.direction === 'forward' ? 'Chiều đi' : 'Chiều về'}</dd>
      <dt>Vị trí</dt><dd>{value.position.map(n => n.toFixed(5)).join(', ')}</dd>
      <dt>Phát hành</dt><dd>{dateTime(value.published_at)}</dd>
      <dt>Bắt đầu</dt><dd>{dateTime(value.start_at)}</dd>
      <dt>Kết thúc</dt><dd>{value.end_at ? dateTime(value.end_at) : 'Đến khi có thông báo kết thúc'}</dd>
    </dl>
  </Modal>;
}

export function WarningLink({id, segments}:{id:number;segments:Segment[]}) {
  const [detail,setDetail] = useState<PublishedWarning|null>(null);
  const action = useAction();
  return <><button type="button" className="text-button" disabled={action.busy} onClick={() => action.run(async () => setDetail(await api<PublishedWarning>(`/warnings/${id}`)))}>Xem cảnh báo</button>
    <Feedback error={action.error}/>
    {detail && <WarningDetail value={detail} segments={segments} onClose={() => setDetail(null)}/>}
  </>;
}

export default function PublicWarnings({segments}:{segments:Segment[]}) {
  const [segment,setSegment] = useState('');
  const [detail,setDetail] = useState<PublishedWarning|null>(null);
  const list = useRemote<PublishedWarning[]>(`/warnings${segment ? `?segment_id=${segment}` : ''}`,[]);
  const action = useAction();
  useEffect(() => {const timer = window.setInterval(list.reload,30000); return () => clearInterval(timer);}, [list.reload]);
  return <section className="card workflow-section">
    <div className="section-title"><Bell size={18}/><h2>Cảnh báo đã phát hành</h2></div>
    <label className="field">Lọc theo tuyến đường<select value={segment} onChange={e => setSegment(e.target.value)}><option value="">Tất cả tuyến</option>{segments.filter(s => s.active).map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label>
    <Feedback error={action.error}/>
    <Loading loading={list.loading} error={list.error} onRetry={list.reload}>
      {list.data.length ? <div className="workflow-list">{list.data.map(w => <button key={w.id} className="workflow-list-item" disabled={action.busy} onClick={() => action.run(async () => setDetail(await api<PublishedWarning>(`/warnings/${w.id}`)))}>
        <div><b>{kinds[w.kind]} · {segments.find(s => s.id === w.segment_id)?.name}</b><p>{w.content}</p><small>{w.upcoming ? 'Sắp áp dụng' : 'Đang áp dụng'} · {dateTime(w.published_at)}</small></div><ChevronRight size={17}/>
      </button>)}</div> : <Empty><p>Hiện chưa có cảnh báo.</p></Empty>}
    </Loading>
    {detail && <WarningDetail value={detail} segments={segments} onClose={() => setDetail(null)}/>}
  </section>;
}
