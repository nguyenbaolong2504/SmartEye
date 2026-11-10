import {useState} from 'react';
import {Activity, MapPin} from 'lucide-react';
import {api} from './api';
import {Empty, Notice} from './components';
import {TrafficMap} from './TrafficMap';
import {type Segment, dateTime} from './types';
import {CurrentConditions, trafficLabel, type CurrentRoad, type Direction, Feedback, Loading, iso, localInput, useAction, useRemote} from './business';

type Reading = {at:string;metrics:{count?:number;flow_per_minute?:number;speed_kmh?:number;state?:string}};

export default function RoadObservation({segment,tileUrl}:{segment:Segment;tileUrl?:string}) {
  const [open,setOpen] = useState(false);
  return <section className="card workflow-section">
    <div className="section-title"><Activity size={18}/><h2>Tình trạng hiện tại</h2><button className="button small" onClick={() => setOpen(v => !v)}>{open ? 'Thu gọn' : 'Xem hiện trạng và bản đồ'}</button></div>
    <p className="muted">Quan sát trên tuyến {segment.name} theo từng chiều.</p>
    {open && <RoadDetail key={segment.id} segment={segment} tileUrl={tileUrl}/>}
  </section>;
}

function RoadDetail({segment,tileUrl}:{segment:Segment;tileUrl?:string}) {
  const [direction,setDirection] = useState<Direction>('forward');
  const [showMap,setShowMap] = useState(false);
  const [start,setStart] = useState(localInput(new Date(Date.now()-86400000).toISOString()));
  const [end,setEnd] = useState(localInput());
  const [rows,setRows] = useState<Reading[]|null>(null);
  const action = useAction();
  const query = `segment_id=${segment.id}&direction=${direction}`;
  const view = useRemote<CurrentRoad|null>(`/traffic/road?${query}`,null);
  function search(e:React.FormEvent) {
    e.preventDefault();
    void action.run(async () => {
      setRows(null);
      setRows(await api<Reading[]>(`/traffic/readings?${query}&start=${encodeURIComponent(iso(start))}&end=${encodeURIComponent(iso(end))}`));
    }, 'Đã tra cứu lịch sử.');
  }
  return <>
    <label className="field">Chiều di chuyển<select value={direction} onChange={e => {setDirection(e.target.value as Direction);setRows(null);}}>
      <option value="forward">Chiều đi</option>{!segment.one_way && <option value="reverse">Chiều về</option>}
    </select></label>
    <Loading loading={view.loading} error={view.error} onRetry={view.reload}>
      {view.data && <>
        <p><b>{view.data.segment_name}</b> · {view.data.start_node} → {view.data.end_node}</p>
        <CurrentConditions value={view.data}/>
        <button className="button small" onClick={() => setShowMap(v => !v)}><MapPin size={16}/>{showMap ? 'Ẩn bản đồ' : 'Xem tuyến trên bản đồ'}</button>
        {showMap && (view.data.geometry.length ? <TrafficMap places={[]} segments={[{...segment,is_demo:false,geometry:view.data.geometry,observation:null}]} routes={[]} selected="" onSelect={() => {}} browserKey="" provider="auto" origin={{name:'Điểm đầu',lat:view.data.geometry[0][0],lng:view.data.geometry[0][1]}} destination={{name:'Điểm cuối',lat:view.data.geometry.at(-1)![0],lng:view.data.geometry.at(-1)![1]}} tileUrl={tileUrl}/> : <Notice>Chưa có thông tin vị trí tuyến đường.</Notice>)}
      </>}
    </Loading>
    <div className="workflow-actions">
      <h3>Tra cứu quan sát đã ghi nhận</h3>
      <Feedback error={action.error}/>
      <form onSubmit={search}>
        <div className="two-columns"><label className="field">Từ thời điểm<input type="datetime-local" value={start} onChange={e => setStart(e.target.value)} required/></label><label className="field">Đến thời điểm<input type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} min={start} max={localInput()} required/></label></div>
        <button className="button primary" disabled={action.busy}>Tìm kiếm</button>
      </form>
      {rows && (rows.length ? <div className="table-wrap"><table><thead><tr><th>Ghi nhận</th><th>Số xe</th><th>Lưu lượng (xe/phút)</th><th>Vận tốc (km/h)</th><th>Tình trạng</th></tr></thead><tbody>{rows.map((row,i) => <tr key={`${row.at}-${i}`}><td>{dateTime(row.at)}</td><td>{row.metrics.count ?? '—'}</td><td>{row.metrics.flow_per_minute ?? '—'}</td><td>{row.metrics.speed_kmh ?? '—'}</td><td>{trafficLabel(row.metrics.state)}</td></tr>)}</tbody></table></div> : <Empty><p>Chưa có quan sát phù hợp trong khoảng này.</p></Empty>)}
    </div>
  </>;
}
