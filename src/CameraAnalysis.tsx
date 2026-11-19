import {useEffect,useRef,useState} from 'react';
import {ArrowRight,CheckCircle2,Clock3,HelpCircle,TriangleAlert} from 'lucide-react';
import {api,json} from './api';
import {Modal,Notice,Spinner} from './components';
import {ConditionsSummary} from './CameraConditions';
import type {CameraAnalysisData,CameraForecast,CameraPrediction} from './cameraAnalysisData';

const states=['FREE','SLOW','JAM'] as const;
// Keep a value below the 80% threshold below 80% when displaying it, too.
const percentage=(value:number)=>value>0&&value<.001?'<0.1%':`${Math.floor((value*100+1e-7)*10)/10}%`;
const timeText=(second:number)=>`${String(Math.floor(second/60)).padStart(2,'0')}:${String(Math.floor(second%60)).padStart(2,'0')}`;
function distribution(item:CameraPrediction){
  const p=item.congestion_probabilities;
  if(!p||states.some(key=>!Number.isFinite(p[key])||p[key]<0||p[key]>1))return null;
  if(Math.abs(states.reduce((sum,key)=>sum+p[key],0)-1)>.001)return null;
  return p;
}

export default function CameraAnalysis({view,forecastUrl,allowForecast}:{
  view:{data:CameraAnalysisData;error:string;reload:()=>void};forecastUrl?:string;allowForecast:boolean;
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
    setBusy(true);setError('');setResult(null);
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
  const decision=item?.decision;
  const finalState=decision?.state||winner;
  const finalProbability=decision?.probability??(p?p[finalState]:0);
  // The backend turns the available evidence into one actionable FREE/JAM
  // result.  Older saved analyses still use the former threshold fallback.
  const high=decision?true:!!p&&finalState!=='SLOW'&&finalProbability>=.8;
  const basis=result?.basis;
  const summary=result?.summary;
  const geometry=result?.road_geometry;
  const metrics=summary?.traffic_metrics;
  const show=(value:number|null|undefined,unit='')=>value==null?'Chưa đủ dữ liệu':`${value.toLocaleString('vi-VN',{maximumFractionDigits:1})}${unit}`;
  return <section className="camera-analysis" aria-label="Phân tích video camera">
    <div className="camera-analysis-intro"><Clock3 size={20}/><div><h3>Đường sắp tới thế nào?</h3><p>Chọn thời gian bạn muốn xem trước.</p></div></div>
    <div className="camera-horizons" role="group" aria-label="Thời gian dự báo">{[15,30,60].map(minutes=><button type="button" key={minutes} aria-pressed={horizon===minutes} onClick={()=>select(minutes)}>{minutes===60?'1 giờ':`${minutes} phút`}</button>)}</div>
    <button type="button" className="button primary camera-analyze-button" disabled={busy||!data.analysis_id||!forecastUrl} onClick={()=>void analyze()}>{busy?<><Spinner/>Đang phân tích…</>:<>Phân tích<ArrowRight size={16}/></>}</button>
    {error&&<Notice kind="error">{error}</Notice>}
    {!result&&!error&&!busy&&<p className="camera-analysis-hint">Nhấn Phân tích để xem khả năng thông thoáng hoặc ùn tắc sau {horizon===60?'1 giờ':`${horizon} phút`}.</p>}
    {result&&item&&p&&<div className={`camera-result ${high?finalState:'uncertain'}`} role="status" aria-live="polite">
      <div className="camera-result-kicker">Sau {horizon===60?'1 giờ':`${horizon} phút`}{result.reference_at&&<> · {new Date(new Date(result.reference_at).getTime()+horizon*60000).toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'})}</>}</div>
      <div className="camera-result-signal">{high?(finalState==='FREE'?<CheckCircle2 size={18}/>:<TriangleAlert size={18}/>):<HelpCircle size={18}/>}<span>{high?'Kết quả dự báo':'Chưa đủ căn cứ'}</span></div>
      <h4>{high?(finalState==='FREE'?'Khả năng thông thoáng':'Khả năng ùn tắc'):'Chưa kết luận'}</h4>
      {high&&<strong className="camera-result-percentage">{percentage(finalProbability)}</strong>}
      <p>{high?(finalState==='FREE'?'Xe đang di chuyển và lịch sử cùng giờ thuận lợi. Bạn có thể chọn khung giờ này, nhưng vẫn nên kiểm tra lại trước khi xuất phát.':'Mật độ, chuyển động và lịch sử cùng giờ cho thấy nguy cơ tăng. Nên cân nhắc đổi giờ đi hoặc chọn tuyến khác.'):'Video và lịch sử chưa cùng tạo ra mức tin cậy từ 80% trở lên, nên hệ thống không đưa ra dự báo chắc chắn.'}</p>
      <button type="button" className="text-button camera-why" onClick={()=>setExplaining(true)}><HelpCircle size={15}/>Xem vì sao</button>
    </div>}
    <p className="camera-analysis-note">Bản chạy thử dùng video minh họa. Tỷ lệ là khả năng dự báo của tình huống đang xem, không phải cam kết độ chính xác ngoài thực tế.</p>
    {explaining&&result&&item&&p&&<Modal title={`Vì sao có kết quả sau ${horizon===60?'1 giờ':`${horizon} phút`}?`} onClose={()=>setExplaining(false)}>
      <div className="camera-forecast-explanation">
        <p>{high?<><b>{finalState==='FREE'?'Khả năng thông thoáng':'Khả năng ùn tắc'}: {percentage(finalProbability)}.</b> Đây là kết luận duy nhất để bạn quyết định có nên đi vào khung giờ này hay không.</>:<>Chưa có kết luận đủ chắc chắn. Hệ thống không hiển thị các tỷ lệ nhỏ lẻ để tránh khiến người xem hiểu nhầm.</>}</p>
        <h3>Video đã cho thấy gì?</h3>
        {summary&&<p>Xem đoạn {timeText(summary.start_second)}–{timeText(summary.end_second)} ở cuối video ({summary.frames} khung hình). Số xe điển hình là {summary.median_count}; mức mật độ điển hình {Math.round(summary.median_score*100)}%. Lấy trung vị của đoạn này để giảm ảnh hưởng của một khung hình bất thường.</p>}
        {basis&&<p>Khung hình đại diện lúc {timeText(basis.second)} có {basis.count} xe: {basis.vehicle_counts.car} ô tô, {basis.vehicle_counts.motorcycle} xe máy, {basis.vehicle_counts.bus} xe buýt, {basis.vehicle_counts.truck} xe tải. Số này minh họa một khung hình; kết quả phân tích dùng cả đoạn nêu trên.</p>}
        <p>Xe được nhận diện và theo dõi trong vùng đường. Không cộng xe của các khung hình thành mật độ, vì cùng một xe có thể xuất hiện nhiều lần. Xe bị che khuất hoặc quá nhỏ vẫn có thể bị bỏ sót.</p>
        {metrics&&<><h3>Các phép đo từ video</h3><div className="table-wrap"><table><thead><tr><th>Thông tin</th><th>Kết quả</th><th>Cách tính</th></tr></thead><tbody>
          <tr><td>Xe qua vạch</td><td>{result.measurements?.crossings??'—'} lượt</td><td>Mỗi mã xe cắt vạch được tính một lần</td></tr>
          <tr><td>Lưu lượng quy đổi</td><td>{show(metrics.flow_veh_per_hour,' xe/giờ')}</td><td>Lượt xe qua vạch ÷ số giây quan sát × 3.600</td></tr>
          <tr><td>Mật độ trên đoạn đường</td><td>{show(metrics.density_veh_per_km,' xe/km')}</td><td>Xe đang hiện diện ÷ chiều dài đã đo</td></tr>
          <tr><td>Tốc độ đang quan sát</td><td>{show(metrics.avg_speed_kmh,' km/h')}</td><td>Quãng đường đã hiệu chuẩn ÷ thời gian × 3,6</td></tr>
          <tr><td>Mức giảm tốc</td><td>{show(metrics.congestion_index==null?null:metrics.congestion_index*100,'%')}</td><td>1 − tốc độ quan sát ÷ tốc độ thông thoáng</td></tr>
          <tr><td>Thời gian so với thông thoáng</td><td>{show(metrics.travel_time_index,' lần')}</td><td>Tốc độ thông thoáng ÷ tốc độ quan sát</td></tr>
        </tbody></table></div><p>Clip ngắn chưa phải một ô quan trắc đủ 5 phút. {result.measurements?.count_line_verified?'Vạch đếm đã được xác nhận.':'Vạch đếm đang dùng để chạy thử.'} {!metrics.quality?.speed_calibrated&&'Chưa có hiệu chuẩn mặt đường để công bố tốc độ thực; không đổi chuyển động trong ảnh thành km/h.'}</p></>}
        {item.predicted_speed_kmh!=null&&<><h3>Dự tính sau {horizon} phút</h3><p>Tốc độ khoảng <b>{show(item.predicted_speed_kmh,' km/h')}</b>; mức giảm tốc khoảng <b>{show((item.predicted_congestion_index??0)*100,'%')}</b> so với mức thông thoáng {item.free_flow_speed_kmh} km/h. {item.predicted_travel_time_index!=null&&`Thời gian đi qua cùng đoạn đường khoảng ${item.predicted_travel_time_index.toLocaleString('vi-VN',{maximumFractionDigits:1})} lần khi thông thoáng.`}</p><p>Đây là dự tính từ lịch sử minh họa. Tốc độ được dự báo riêng; mức giảm tốc không phải xác suất ùn tắc {percentage(p.JAM)}.</p></>}
        {geometry&&<><h3>Đã xét đường rộng hay hẹp thế nào?</h3><p>Vùng quan sát rộng {geometry.road_width_m} m, dài {geometry.observed_length_m} m; sức chứa ước tính {geometry.capacity_pcu} ô tô quy đổi.</p><p>Xe quy đổi = ô tô + 0,25 × xe máy + 3 × xe buýt + 2,5 × xe tải. Sức chứa = diện tích mặt đường sử dụng ÷ {geometry.car_space_m2} m². Mức sử dụng = xe quy đổi ÷ sức chứa.</p>{summary?.median_load_ratio!=null&&<p>Mức sử dụng điển hình trong đoạn đã xem: {Math.round(summary.median_load_ratio*100)}%. {summary.motion_known?`Khoảng ${Math.round((summary.stopped_share??0)*100)}% xe đủ dữ liệu theo dõi đang đứng hoặc nhích chậm.`:'Chưa đủ dữ liệu để đánh giá chuyển động.'}</p>}<p>Đây là kích thước và hệ số chạy thử. Nhiều xe trên đường rộng chưa đủ để kết luận ùn tắc; cần xét cả chuyển động và diễn biến theo thời gian.</p></>}
        <h3>Lịch sử và điều kiện xung quanh</h3>
        {item.history&&<p>Trong {item.history.lookback_days} ngày trước mốc dự báo, có {item.history.matching_days} {item.history.day_type?.toLowerCase()||'ngày tương tự'} có dữ liệu lúc {item.history.hour}: {item.history.free_days??0} ngày thông thoáng, {item.history.slow_days??0} ngày di chuyển chậm và {item.history.jam_days} ngày ùn tắc. Lịch sử chỉ hỗ trợ kết luận, không thể thay thế hình ảnh đang xem.</p>}
      {decision&&<p>Mức nguy cơ được tổng hợp từ: mô hình {percentage(decision.evidence.model_jam)} ùn tắc, lịch sử cùng giờ {percentage(decision.evidence.monthly_jam)}, video hiện tại {percentage(decision.evidence.video_congestion)} và điều kiện đường/thời tiết {percentage(decision.evidence.conditions)}. {decision.evidence.stopped_share!=null&&`Xe đứng hoặc nhích chậm trong video: ${percentage(decision.evidence.stopped_share)}.`}</p>}
        <ConditionsSummary value={result.conditions}/>
        <details className="camera-explanation-details"><summary>Cách tính tỷ lệ và giới hạn</summary><p>Mô hình XGBoost nhận mật độ đã chuẩn hóa theo sức chứa đường, lịch sử, chuyển động, thời tiết và sự cố có thông tin. Bản chạy thử tính nguy cơ ùn tắc từ 32% điểm mô hình, 28% lịch sử 30 ngày cùng giờ, 27% video hiện tại và 13% điều kiện đường/thời tiết.</p><p>Nếu nhiều nguồn cùng chỉ ra đường sắp quá tải, hệ thống cộng thêm mức đồng thuận; nếu video ít xe và đang di chuyển thì nguy cơ ùn tắc giảm mạnh. Tỷ lệ không được đặt sẵn thành 80% hay 90%.</p>
          {result.evaluation?.[String(horizon)]&&<p>Trên phần dữ liệu minh họa giữ riêng để kiểm tra, mô hình sau {horizon} phút phân loại đúng khoảng {Math.round(result.evaluation[String(horizon)].test.accuracy*100)}% trường hợp. Đây là kết quả thử mô hình, không phải độ chính xác của riêng lượt phân tích này.</p>}
          {result.evaluation?.[String(horizon)]?.speed&&<p>Sai số tốc độ trung bình trên dữ liệu minh họa giữ riêng: {show(result.evaluation[String(horizon)].speed!.test_mae_kmh,' km/h')}. So với giữ nguyên tốc độ hiện tại: {show(result.evaluation[String(horizon)].speed!.persistence_mae_kmh,' km/h')}.</p>}
          <p>Lịch sử 60 phút dùng 11 mốc minh họa và mốc mới nhất được tổng hợp từ video. Tỷ lệ của cách ghép này chưa được kiểm chứng ngoài đường; không khẳng định đếm đúng mọi xe hoặc dự báo thực tế chính xác 80–90%.</p>
          {result.reference_at&&<p>Mốc tình huống video chạy thử: {new Date(result.reference_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})}. Đây không phải thời điểm quay đã xác minh.</p>}
        </details>
      </div>
    </Modal>}
  </section>;
}
