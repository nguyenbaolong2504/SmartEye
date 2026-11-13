import {useState} from 'react';
import {Bike,Bus,Car,Clock3,ExternalLink,HelpCircle,Truck} from 'lucide-react';
import {Modal,Notice,Spinner} from './components';
import {atTime,type CameraAnalysisData,type CameraPrediction,type DetectionFrame} from './cameraAnalysisData';
import type {Density} from './types';

const densityText:Record<Density,string>={LOW:'Thấp',NORMAL:'Vừa',HIGH:'Cao'};
const trafficText={FREE:'Thông thoáng',SLOW:'Di chuyển chậm',JAM:'Dễ ùn tắc'};
const timeText=(second:number)=>`${String(Math.floor(second/60)).padStart(2,'0')}:${String(Math.floor(second%60)).padStart(2,'0')}`;
const percentage=(value:number)=>value<.01?'<1%':value>.99?'>99%':`${Math.round(value*100)}%`;

export default function CameraAnalysis({view,second,onSeek,onExplain}:{view:{data:CameraAnalysisData;error:string;reload:()=>void};second:number;onSeek:(second:number)=>void;onExplain:()=>void}){
  const [explaining,setExplaining]=useState<CameraPrediction|null>(null);
  const [explainFrame,setExplainFrame]=useState<DetectionFrame|null>(null);
  const data=view.data;
  if(view.error)return <Notice kind="error">{view.error}<button className="text-button" onClick={view.reload}>Thử tải kết quả</button></Notice>;
  if(data.state!=='completed')return <section className="camera-analysis"><h3>Phân tích video</h3><p>{['queued','processing'].includes(data.state)&&<Spinner/>} {data.message}</p>{['queued','processing'].includes(data.state)&&<progress aria-label="Tiến độ phân tích" max={100} value={data.progress}/>}</section>;
  const sample=atTime(data.frames?.length?data.frames:data.samples||[],second);
  if(!sample)return null;
  const basis=explainFrame||sample;
  const predictions=atTime(data.forecast?.timeline||[],sample.second)?.predictions||[];
  const high=data.high_threshold??.6;
  const level=sample.density==='HIGH'&&sample.score>=high+(1-high)*.65?'Rất cao':densityText[sample.density];
  const cumulative=sample.cumulative_vehicle_counts;
  return <section className="camera-analysis" aria-label="Phân tích video camera">
    {data.source?.scenario_note&&<div className="camera-scenario-note"><p>{data.source.location_note}</p><p>{data.source.scenario_note}</p><button className="button small" onClick={()=>{
      const frames=data.frames||[];if(frames.length)onSeek(frames.reduce((best,row)=>row.count>best.count?row:best).second);
    }}>Xem đoạn đông xe nhất</button></div>}
    {cumulative&&<div className="camera-cumulative"><h3>Xe đã ghi nhận từ đầu video</h3><p>Mỗi mã xe được theo dõi và cộng một lần. Khi tua lại, số liệu trở về đúng thời điểm video.</p>
      <div className="camera-counts"><article><b>{sample.cumulative_count}</b><span>Tổng xe cộng dồn</span></article><article><Car size={17}/><b>{cumulative.car}</b><span>Ô tô</span></article><article><Bike size={17}/><b>{cumulative.motorcycle}</b><span>Xe máy</span></article><article><Bus size={17}/><b>{cumulative.bus}</b><span>Xe buýt</span></article><article><Truck size={17}/><b>{cumulative.truck}</b><span>Xe tải</span></article></div>
      <p className="micro">Xe bị che lâu hoặc camera di chuyển có thể làm mất dấu và đếm lại. Đây là số mã xe đã xác nhận trong clip, chưa phải lưu lượng xe qua một vạch đếm.</p></div>}
    <div className="camera-analysis-heading"><div><h3>Xe đang xuất hiện trong video</h3><p>Tại {timeText(sample.second)}{sample.frame_index!=null?` · Khung hình ${sample.frame_index+1}`:''}</p></div><strong className={`camera-density ${sample.density}`}>{level}</strong></div>
    <div className="camera-counts camera-current-counts"><article><b>{sample.count}</b><span>Tổng xe đang nhận diện</span></article><article><Car size={17}/><b>{sample.vehicle_counts.car}</b><span>Ô tô</span></article><article><Bike size={17}/><b>{sample.vehicle_counts.motorcycle}</b><span>Xe máy</span></article><article><Bus size={17}/><b>{sample.vehicle_counts.bus}</b><span>Xe buýt</span></article><article><Truck size={17}/><b>{sample.vehicle_counts.truck}</b><span>Xe tải</span></article></div>
    <p className="micro">Số đếm khớp với các ô nhận diện trong vùng đường được đánh dấu. Một xe có thể xuất hiện ở nhiều khung hình; xe bị che hoặc quá nhỏ có thể bị bỏ sót.</p>
    <div className="camera-density-track"><span style={{width:`${Math.min(100,sample.score*100)}%`}}/></div>
    <div className="camera-video-timeline" aria-label="Mật độ theo thời gian video">{(data.samples||[]).map(row=><button key={row.second} type="button" className={`${row.density} ${Math.floor(row.second)===Math.floor(sample.second)?'selected':''}`} style={{height:`${12+row.score*44}px`}} aria-label={`Xem giây ${row.second}, mật độ ${densityText[row.density].toLowerCase()}`} title={`${timeText(row.second)} · ${row.count} xe`} onClick={()=>onSeek(row.second)}/>)}</div>
    <p className="micro">Video dài {timeText(data.duration_seconds||0)} · Trung bình {data.average_count} xe/khung hình · Nhiều nhất {data.peak_count} xe.</p>
    {data.forecast&&<div className="camera-forecast"><h3><Clock3 size={18}/>Khả năng ùn tắc sắp tới <small>Chạy thử</small></h3><p>{data.forecast.message}</p>
      {data.forecast.reference_at&&<p className="micro">Tính từ mốc chạy thử {new Date(data.forecast.reference_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})}.</p>}
      {predictions.length?<div className="camera-forecast-cards">{predictions.map(item=><article key={item.horizon_minutes} className={item.label}><span>Sau {item.horizon_minutes} phút</span>
        {data.forecast?.reference_at&&<small>Khoảng {new Date(new Date(data.forecast.reference_at).getTime()+item.horizon_minutes*60000).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'})}</small>}
        <strong>{item.congestion_label?trafficText[item.congestion_label]:densityText[item.label]}</strong>
        {item.congestion_probability!=null?<><b className="camera-jam-probability">{percentage(item.congestion_probability)}</b><small>khả năng ùn tắc trong dữ liệu mẫu</small></>:<small>Chưa có xác suất phù hợp</small>}
        <button type="button" className="text-button" aria-label={`Giải thích dự báo sau ${item.horizon_minutes} phút`} onClick={()=>{setExplainFrame(sample);onExplain();setExplaining(item);}}><HelpCircle size={14}/>Vì sao?</button>
      </article>)}</div>:<p>Chưa có dự báo cho thời điểm này.</p>}
      <p className="micro">Tỷ lệ được tính từ mô hình trên lịch sử minh họa, chưa được kiểm chứng ngoài đường. Mật độ cao chưa đủ để kết luận đang ùn tắc.</p>
    </div>}
    <details className="camera-detection-details"><summary>Cách nhận diện và đếm xe</summary>
      <p>Ô tô màu xanh lá, xe máy màu xanh dương, xe buýt màu vàng và xe tải màu tím. Chỉ đếm các xe có ô trong vùng quan sát. Tổng xe bằng tổng bốn loại xe ở cùng khung hình.</p>
      <p>Hệ thống nhận diện từng khung hình, loại các ô chồng trùng và chỉ xét vùng mặt đường. Kết quả cần đối chiếu với nhãn thủ công để biết độ chính xác; không cam kết đếm đúng mọi xe trong cảnh bị che khuất.</p>
      <p className="micro">Nhận diện bằng {data.method}. Mức mật độ xét số xe so với sức chứa vùng đường và diện tích có xe. Không dùng số đếm này thay cho tốc độ hoặc tổng xe duy nhất qua đường.</p>
      {data.counting_method&&<p className="micro">Cộng dồn bằng {data.counting_method}, theo dõi mã # trên video. Không cộng tổng số ô của tất cả khung hình vì sẽ đếm lại cùng xe nhiều lần.</p>}
    </details>
    {data.source&&<div className="camera-video-credit"><b>Video minh họa</b><p>{data.source.location_note}</p>{data.source.scenario_note&&<p>{data.source.scenario_note}</p>}<p>{data.source.title} · {data.source.author} · Công bố {data.source.published_date}</p><div><a href={data.source.page_url} target="_blank" rel="noreferrer">Video gốc<ExternalLink size={12}/></a><a href={data.source.license_url} target="_blank" rel="noreferrer">{data.source.license}</a>{data.source.reference_url&&<a href={data.source.reference_url} target="_blank" rel="noreferrer">Ghi nhận giờ cao điểm Ngã Tư Sở</a>}</div></div>}
    {explaining&&<Modal title={`Vì sao có dự báo sau ${explaining.horizon_minutes} phút?`} onClose={()=>setExplaining(null)}>
      <div className="camera-forecast-explanation"><p><b>{explaining.congestion_label?trafficText[explaining.congestion_label]:densityText[explaining.label]}</b>{explaining.congestion_probability!=null&&<> · Khả năng ùn tắc ước tính <b>{percentage(explaining.congestion_probability)}</b> trong dữ liệu mẫu.</>}</p>
        <h3>Căn cứ hệ thống đã xem</h3><ul><li>Khung hình lúc {timeText(basis.second)} có {basis.count} xe, gồm {basis.vehicle_counts.car} ô tô, {basis.vehicle_counts.motorcycle} xe máy, {basis.vehicle_counts.bus} xe buýt và {basis.vehicle_counts.truck} xe tải.</li>
          <li>Xe chiếm khoảng {Math.round(basis.occupancy*100)}% vùng quan sát. Sức chứa chạy thử của vùng này là {data.capacity??'chưa thiết lập'} xe.</li>
          <li>Đối chiếu lịch sử cùng giờ, cùng thứ trong tuần và diễn biến trước thời điểm dự báo.</li></ul>
        {basis.cumulative_count!=null&&<p>Đã ghi nhận cộng dồn {basis.cumulative_count} mã xe đến thời điểm này. Số cộng dồn không được dùng thay số xe hiện tại; một tuyến đông xe qua lại nhưng vẫn chạy nhanh chưa chắc bị ùn tắc.</p>}
        {explaining.history&&<p>Trong {explaining.history.lookback_days} ngày minh họa gần nhất, có {explaining.history.matching_days} ngày cùng thứ có dữ liệu lúc {explaining.history.hour}; {explaining.history.jam_days} ngày được gắn nhãn ùn tắc. Đây là tần suất lịch sử, không phải chính tỷ lệ dự báo.</p>}
        {explaining.congestion_probabilities&&<div className="camera-probability-breakdown">{(['FREE','SLOW','JAM'] as const).map(state=><div key={state}><span>{trafficText[state]}</span><progress max={1} value={explaining.congestion_probabilities![state]}/><b>{percentage(explaining.congestion_probabilities![state])}</b></div>)}</div>}
        <h3>Hiểu đúng tỷ lệ này</h3><p>Con số được tính từ các trạng thái mà mô hình đã học, sau khi hiệu chỉnh trên phần dữ liệu riêng. Ví dụ 90% là mức khả năng dự báo cho một tình huống; không có nghĩa hệ thống đếm đúng 90% số xe hoặc luôn dự đoán đúng 90%.</p>
        <p>Video hiện tại chưa xác minh đúng tuyến đang chọn. Lịch sử 60 phút dùng 11 mốc minh họa và mốc mới nhất từ video. Chưa có tốc độ thực hoặc nhãn ùn tắc đã kiểm chứng, nên chỉ dùng để chạy thử cách hoạt động.</p>
      </div>
    </Modal>}
  </section>;
}
