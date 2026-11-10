import {useState} from 'react';
import {Modal, Notice} from './components';
import {dateTime} from './types';
import {trafficLabel,type CurrentRoad} from './business';

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
