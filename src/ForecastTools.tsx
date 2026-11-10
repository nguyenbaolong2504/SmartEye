import {useState} from 'react';
import {Clock3} from 'lucide-react';
import {api} from './api';
import {Empty, Modal, Notice, Spinner} from './components';
import {type Segment,dateTime} from './types';
import {trafficLabel, type CurrentRoad,type Direction,Feedback,Loading,RoadFields,useAction,useRemote} from './business';

type Prediction = {label:string; predicted_at:string; horizon_minutes?:number; model?:string};
export type Comparison = {current:CurrentRoad; forecast:Prediction};

export function ForecastInfo({model,version,issued,at,label,demo,comparison}:{model?:string;version?:string;issued?:string;at:string;label:string;demo:boolean;comparison?:Comparison|null}) {
  const [show,setShow] = useState<'detail'|'compare'|null>(null);
  return <>
    <div className="workflow-buttons workflow-section"><button className="button small" onClick={() => setShow('detail')}>Chi tiết dự báo</button><button className="button small" onClick={() => setShow('compare')}>So sánh hiện tại với dự báo</button></div>
    {show && <Modal title={show === 'detail' ? 'Chi tiết dự báo' : 'So sánh hiện tại với dự báo'} onClose={() => setShow(null)}>
      {show === 'detail' ? <dl className="workflow-details"><dt>Trạng thái dự báo</dt><dd>{trafficLabel(label)}</dd><dt>Thời điểm áp dụng</dt><dd>{dateTime(at)}</dd><dt>Tạo dự báo lúc</dt><dd>{issued ? dateTime(issued) : 'Chưa có thông tin'}</dd><dt>Nguồn dữ liệu</dt><dd>{demo ? 'Lịch sử minh họa' : 'Quan sát thực'}</dd>{model && <><dt>Mô hình</dt><dd>{model}</dd></>}{version && <><dt>Phiên bản</dt><dd>{version}</dd></>}</dl> :
        comparison?.current.fresh && comparison.current.state ? <>
          <div className="workflow-grid"><article><span>{demo ? 'Hiện tại theo lịch sử minh họa' : 'Quan sát hiện tại'}</span><strong>{trafficLabel(comparison.current.state)}</strong><small>{comparison.current.observed_at && dateTime(comparison.current.observed_at)}</small></article><article><span>Dự báo</span><strong>{trafficLabel(comparison.forecast.label)}</strong><small>{dateTime(comparison.forecast.predicted_at)}</small></article></div>
          <p className="workflow-section">{comparison.current.segment_name} · Cùng tuyến và chiều di chuyển.</p>
          <p>{trend(comparison.current.state,comparison.forecast.label)}</p>
        </> : <Notice>Chưa có dữ liệu hiện tại đủ mới để so sánh.</Notice>}
    </Modal>}
  </>;
}

function trend(current:string,forecast:string) {
  const severity:Record<string,number> = {FREE:0,SLOW:1,JAM:2};
  if (severity[forecast] === severity[current]) return 'Dự kiến giữ cùng mức giao thông.';
  return severity[forecast] > severity[current] ? 'Dự kiến đông hơn so với thời điểm quan sát.' : 'Dự kiến thông thoáng hơn so với thời điểm quan sát.';
}

type ShortForecast = {state:string;message?:string;generated_at?:string;issue_at?:string;model_version?:string;selected?:Prediction;predictions:Prediction[];comparison?:Comparison|null};
export function NearForecast({segments,initialRoad}:{segments:Segment[];initialRoad?:number}) {
  const [road,setRoad] = useState(initialRoad || segments.find(s => s.active)?.id || 0);
  const [direction,setDirection] = useState<Direction>('forward');
  const [horizon,setHorizon] = useState<number|null>(null);
  const [result,setResult] = useState<ShortForecast|null>(null);
  const action = useAction();
  const params = `segment_id=${road}&direction=${direction}`;
  const options = useRemote<{ready:boolean;horizons:number[];message?:string}>(`/traffic/forecast-options?${params}&data_mode=observed`,{ready:false,horizons:[]});
  const available = options.data.horizons;
  const selection = horizon != null && available.includes(horizon) ? horizon : available[0];
  return <section className="card">
    <div className="section-title"><Clock3 size={18}/><h2>Dự báo ngắn hạn</h2></div><p className="muted">Mốc dự báo phụ thuộc mô hình đã kích hoạt và độ mới của dữ liệu quan sát.</p>
    <RoadFields segments={segments} road={road} direction={direction} onRoad={id => {setRoad(id);setDirection('forward');setResult(null);setHorizon(null);}} onDirection={value => {setDirection(value);setResult(null);setHorizon(null);}}/>
    <Loading loading={options.loading} error={options.error} onRetry={options.reload}>
      {options.data.ready ? <form onSubmit={e => {e.preventDefault();void action.run(async () => {setResult(null);setResult(await api<ShortForecast>(`/traffic/forecast?${params}&horizon=${selection}`));});}}>
        <label className="field">Mốc dự báo<select value={selection} onChange={e => {setHorizon(Number(e.target.value));setResult(null);}}>{available.map(h => <option value={h} key={h}>Sau {h} phút</option>)}</select></label>
        <button className="button primary" disabled={action.busy}>{action.busy && <Spinner/>}Xem dự báo</button>
      </form> : <Empty><p>{options.data.message || 'Chưa có mốc dự báo được hỗ trợ.'}</p></Empty>}
    </Loading>
    <Feedback error={action.error}/>
    {result && (result.state === 'ready' && result.selected ? <>
      <h3 className="workflow-section">{trafficLabel(result.selected.label)}</h3><p>Áp dụng {dateTime(result.selected.predicted_at)}</p>
      <ForecastInfo model={result.selected.model} version={result.model_version} issued={result.generated_at || result.issue_at} at={result.selected.predicted_at} label={result.selected.label} demo={false} comparison={result.comparison}/>
      <h3>Xu hướng dự báo</h3>
      {result.predictions.length >= 2 ? <div className="workflow-grid">{result.predictions.map(p => <article key={p.predicted_at}><span>{dateTime(p.predicted_at)}</span><strong>{trafficLabel(p.label)}</strong></article>)}</div> : <p>Chưa đủ mốc dự báo để xem xu hướng.</p>}
    </> : <Notice>{result.message || 'Dự báo chưa khả dụng do thiếu hoặc quá hạn dữ liệu.'}</Notice>)}
  </section>;
}
