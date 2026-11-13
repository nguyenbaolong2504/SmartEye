import {useEffect,useRef,useState} from 'react';
import {ArrowRight,CheckCircle2,Clock3,HelpCircle,TriangleAlert} from 'lucide-react';
import {api,json} from './api';
import {Modal,Notice,Spinner} from './components';
import {ConditionsSummary} from './CameraConditions';
import type {CameraAnalysisData,CameraForecast,CameraPrediction} from './cameraAnalysisData';

const states=['FREE','SLOW','JAM'] as const;
type TrafficState=typeof states[number];
const trafficText:Record<TrafficState,string>={FREE:'Thông thoáng',SLOW:'Di chuyển chậm',JAM:'Ùn tắc'};
// Keep a value below the 80% threshold below 80% when displaying it, too.
const percentage=(value:number)=>value>0&&value<.001?'<0.1%':`${Math.floor((value*100+1e-7)*10)/10}%`;
const timeText=(second:number)=>`${String(Math.floor(second/60)).padStart(2,'0')}:${String(Math.floor(second%60)).padStart(2,'0')}`;
function distribution(item:CameraPrediction){
  const p=item.congestion_probabilities;
  if(!p||states.some(key=>!Number.isFinite(p[key])||p[key]<0||p[key]>1))return null;
  if(Math.abs(states.reduce((sum,key)=>sum+p[key],0)-1)>.001)return null;
  return p;
}

export default function CameraAnalysis({view,onExplain,forecastUrl,allowForecast}:{
  view:{data:CameraAnalysisData;error:string;reload:()=>void};onExplain:()=>void;forecastUrl?:string;allowForecast:boolean;
}){
  const [horizon,setHorizon]=useState(15);
  const [result,setResult]=useState<CameraForecast|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[explaining,setExplaining]=useState(false);
  const request=useRef<AbortController|null>(null);
  const data=view.data;
  useEffect(()=>()=>request.current?.abort(),[]);
  useEffect(()=>{request.current?.abort();setResult(null);setBusy(false);setError('');setExplaining(false);},[data.analysis_id]);
  function select(minutes:number){
    request.current?.abort();setHorizon(minutes);setResult(null);setBusy(false);setError('');setExplaining(false);
  }
  async function analyze(){
    if(!forecastUrl||!data.analysis_id)return;
    request.current?.abort();const controller=new AbortController();request.current=controller;
    setBusy(true);setError('');setResult(null);onExplain();
    try{
      const value=await api<CameraForecast>(forecastUrl.replace(/^\/api(?=\/)/,''),{
        ...json({horizon_minutes:horizon,analysis_id:data.analysis_id,whole_video:true}),signal:controller.signal,
      });
      if(controller.signal.aborted)return;
      const item=value.timeline?.[0]?.predictions?.[0];
      if(value.analysis_id!==data.analysis_id||value.scope!=='video'||value.timeline.length!==1||value.timeline[0].predictions.length!==1||item?.horizon_minutes!==horizon||!distribution(item)){
        throw new Error('Chưa có tỷ lệ phù hợp cho video này. Vui lòng thử phân tích lại.');
      }
      setResult(value);
    }catch(reason){if(!controller.signal.aborted)setError((reason as Error).message);}
    finally{if(!controller.signal.aborted)setBusy(false);}
  }
  if(!allowForecast)return null;
  if(view.error)return <section className="camera-analysis"><Notice kind="error">{view.error}<button className="text-button" onClick={view.reload}>Thử tải kết quả</button></Notice></section>;
  if(data.state!=='completed')return <section className="camera-analysis"><h3>Phân tích video</h3><p>{['queued','processing'].includes(data.state)&&<Spinner/>} {data.message}</p>{['queued','processing'].includes(data.state)&&<progress aria-label="Tiến độ phân tích" max={100} value={data.progress}/>}</section>;
  const item=result?.timeline[0].predictions[0];
  const p=item?distribution(item):null;
  const winner=p?states.reduce((best,key)=>p[key]>p[best]?key:best):'FREE';
  const high=!!p&&p[winner]>=.8;
  const basis=result?.basis;
  const summary=result?.summary;
  const geometry=result?.road_geometry;
  return <section className="camera-analysis" aria-label="Phân tích video camera">
    <div className="camera-analysis-intro"><Clock3 size={20}/><div><h3>Đường sắp tới thế nào?</h3><p>Chọn thời gian bạn muốn xem trước.</p></div></div>
    <div className="camera-horizons" role="group" aria-label="Thời gian dự báo">{[15,30,60].map(minutes=><button type="button" key={minutes} aria-pressed={horizon===minutes} onClick={()=>select(minutes)}>{minutes===60?'1 giờ':`${minutes} phút`}</button>)}</div>
    <button type="button" className="button primary camera-analyze-button" disabled={busy||!data.analysis_id||!forecastUrl} onClick={()=>void analyze()}>{busy?<><Spinner/>Đang phân tích…</>:<>Phân tích<ArrowRight size={16}/></>}</button>
    {error&&<Notice kind="error">{error}</Notice>}
    {!result&&!error&&!busy&&<p className="camera-analysis-hint">Nhấn Phân tích để xem khả năng thông thoáng hoặc ùn tắc sau {horizon===60?'1 giờ':`${horizon} phút`}.</p>}
    {result&&item&&p&&<div className={`camera-result ${high?winner:'uncertain'}`} role="status" aria-live="polite">
      <div className="camera-result-kicker">Sau {horizon===60?'1 giờ':`${horizon} phút`}{result.reference_at&&<> · {new Date(new Date(result.reference_at).getTime()+horizon*60000).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'})}</>}</div>
      <div className="camera-result-signal">{high?(winner==='FREE'?<CheckCircle2 size={18}/>:<TriangleAlert size={18}/>):<HelpCircle size={18}/>}<span>{high?'Khả năng cao':'Xu hướng chưa rõ'}</span></div>
      <h4>{trafficText[winner]}</h4><strong className="camera-result-percentage">{percentage(p[winner])}</strong>
      <p>{high?(winner==='FREE'?'Nhiều khả năng đường sẽ thông thoáng.':winner==='SLOW'?'Nên dự trù thêm thời gian di chuyển.':'Nên cân nhắc giờ đi hoặc tuyến đường khác.'):'Chưa có trạng thái nào đạt 80%. Nên kiểm tra lại trước khi đi.'}</p>
      <div className="camera-probability-breakdown" aria-label="Khả năng từng tình trạng">{states.map(state=><div key={state} className={state}><span>{trafficText[state]}</span><progress aria-label={`Khả năng ${trafficText[state].toLowerCase()}`} max={1} value={p[state]}/><b>{percentage(p[state])}</b></div>)}</div>
      <button type="button" className="text-button camera-why" onClick={()=>{onExplain();setExplaining(true);}}><HelpCircle size={15}/>Vì sao?</button>
    </div>}
    <p className="camera-analysis-note">Ước tính từ video minh họa, chưa kiểm chứng với giao thông thực tế.</p>
    {explaining&&result&&item&&p&&<Modal title={`Vì sao có kết quả sau ${horizon===60?'1 giờ':`${horizon} phút`}?`} onClose={()=>setExplaining(false)}>
      <div className="camera-forecast-explanation">
        <p><b>{trafficText[winner]}: {percentage(p[winner])}.</b> {high?'Đây là trạng thái có khả năng cao nhất và đã đạt ngưỡng thông báo 80%.':'Đây là trạng thái có tỷ lệ cao nhất, nhưng chưa đạt ngưỡng thông báo 80%.'} Ba khả năng được tính riêng và cộng lại bằng khoảng 100%.</p>
        <h3>Video đã cho thấy gì?</h3>
        {summary&&<p>Xem đoạn {timeText(summary.start_second)}–{timeText(summary.end_second)} ở cuối video ({summary.frames} khung hình). Số xe điển hình là {summary.median_count}; mức mật độ điển hình {Math.round(summary.median_score*100)}%. Lấy trung vị của đoạn này để giảm ảnh hưởng của một khung hình bất thường.</p>}
        {basis&&<p>Khung hình đại diện lúc {timeText(basis.second)} có {basis.count} xe: {basis.vehicle_counts.car} ô tô, {basis.vehicle_counts.motorcycle} xe máy, {basis.vehicle_counts.bus} xe buýt, {basis.vehicle_counts.truck} xe tải. Số này minh họa một khung hình; kết quả phân tích dùng cả đoạn nêu trên.</p>}
        <p>Xe được nhận diện và theo dõi trong vùng đường. Không cộng xe của các khung hình thành mật độ, vì cùng một xe có thể xuất hiện nhiều lần. Xe bị che khuất hoặc quá nhỏ vẫn có thể bị bỏ sót.</p>
        {geometry&&<><h3>Đã xét đường rộng hay hẹp thế nào?</h3><p>Vùng quan sát rộng {geometry.road_width_m} m, dài {geometry.observed_length_m} m; sức chứa ước tính {geometry.capacity_pcu} ô tô quy đổi.</p><p>Xe quy đổi = ô tô + 0,25 × xe máy + 3 × xe buýt + 2,5 × xe tải. Sức chứa = diện tích mặt đường sử dụng ÷ {geometry.car_space_m2} m². Mức sử dụng = xe quy đổi ÷ sức chứa.</p>{summary?.median_load_ratio!=null&&<p>Mức sử dụng điển hình trong đoạn đã xem: {Math.round(summary.median_load_ratio*100)}%. {summary.motion_known?`Khoảng ${Math.round((summary.stopped_share??0)*100)}% xe đủ dữ liệu theo dõi đang đứng hoặc nhích chậm.`:'Chưa đủ dữ liệu để đánh giá chuyển động.'}</p>}<p>Đây là kích thước và hệ số chạy thử. Nhiều xe trên đường rộng chưa đủ để kết luận ùn tắc; cần xét cả chuyển động và diễn biến theo thời gian.</p></>}
        <h3>Lịch sử và điều kiện xung quanh</h3>
        {item.history&&<p>Trong {item.history.lookback_days} ngày minh họa gần nhất, có {item.history.matching_days} ngày cùng thứ có dữ liệu lúc {item.history.hour}; {item.history.jam_days} ngày được gắn nhãn ùn tắc. Tần suất này là một căn cứ tham khảo, không phải chính tỷ lệ dự báo.</p>}
        <ConditionsSummary value={result.conditions}/>
        <details className="camera-explanation-details"><summary>Cách tính tỷ lệ và giới hạn</summary><p>Mô hình XGBoost nhận mức mật độ đã chuẩn hóa theo sức chứa đường, diễn biến lịch sử, chuyển động, thời tiết và sự cố có thông tin. Với mỗi trạng thái, điểm mô hình được hiệu chỉnh trên dữ liệu riêng theo công thức p(k) = exp(z(k)/T) ÷ Σ exp(z(j)/T). T là hệ số hiệu chỉnh, z là điểm của từng trạng thái. Không đặt sẵn tỷ lệ 80% hay 90%.</p><p>Khả năng thông thoáng lấy từ trạng thái Thông thoáng, không lấy 100% trừ khả năng ùn tắc, vì còn trạng thái Di chuyển chậm.</p>
          {result.evaluation?.[String(horizon)]&&<p>Trên phần dữ liệu minh họa giữ riêng để kiểm tra, mô hình sau {horizon} phút phân loại đúng khoảng {Math.round(result.evaluation[String(horizon)].test.accuracy*100)}% trường hợp. Đây là kết quả thử mô hình, không phải độ chính xác của riêng lượt phân tích này.</p>}
          <p>Lịch sử 60 phút dùng 11 mốc minh họa và mốc mới nhất được tổng hợp từ video. Tỷ lệ của cách ghép này chưa được kiểm chứng ngoài đường; không khẳng định đếm đúng mọi xe hoặc dự báo thực tế chính xác 80–90%.</p>
          {result.reference_at&&<p>Mốc thời gian chạy thử: {new Date(result.reference_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})}. Đây không phải thời điểm quay đã xác minh.</p>}
        </details>
      </div>
    </Modal>}
  </section>;
}
