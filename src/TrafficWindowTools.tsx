import {useState} from 'react';
import {api} from './api';
import {Notice,Spinner} from './components';
import {dateTime} from './types';
import type {TrafficMetrics} from './cameraAnalysisData';

type ImportResult={rows:number;updates:number;usable:number;message:string;preview?:{window_end:string;metrics:TrafficMetrics;verified_state?:string;usable:boolean}[]};
const stateText:Record<string,string>={FREE:'Thông thoáng',SLOW:'Di chuyển chậm',JAM:'Ùn tắc'};
const value=(n:number|null|undefined,unit='')=>n==null?'Chưa có':`${n.toLocaleString('vi-VN',{maximumFractionDigits:1})}${unit}`;

export default function TrafficWindowTools({road,direction,onUpdated}:{road:number;direction:string;onUpdated:()=>void}){
  const [file,setFile]=useState<File|null>(null),[result,setResult]=useState<ImportResult|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [forecast,setForecast]=useState<{state:string;message:string;issue_at?:string;predictions:{horizon_minutes:number;predicted_at:string;label:string;jam_probability:number;predicted_speed_kmh?:number;predicted_congestion_index?:number}[]}|null>(null);
  const [outcomes,setOutcomes]=useState<{issued:number;evaluated:number;accuracy:number|null;message:string}|null>(null);
  async function run(action:()=>Promise<void>){setBusy(true);setError('');try{await action();}catch(reason){setError((reason as Error).message);}finally{setBusy(false);}}
  async function upload(commit=false){if(!file)return;const form=new FormData();form.append('file',file);const data=await api<ImportResult>(`/forecast/traffic/import?dry_run=${!commit}`,{method:'POST',body:form});setResult(data);if(commit)onUpdated();}
  return <section className="card forecast-data-tools">
    <h2>Quan trắc giao thông mỗi 5 phút</h2>
    <p>Mỗi dòng thuộc một đường, một chiều và một mốc kết thúc. Tách số xe đang có trong đoạn đường và số lượt xe qua vạch. Chỉ dùng dữ liệu có quyền huấn luyện, tốc độ đã hiệu chuẩn, kích thước đã đo và ít nhất 240 giây quan trắc trong mỗi ô.</p>
    <p>Nhãn Thông thoáng / Di chuyển chậm / Ùn tắc phải được xác minh riêng. Không lấy kết quả mô hình để làm nhãn. Quan trắc thực cần gắn vào tuyến đường thực, không nhập vào tuyến minh họa.</p>
    {error&&<Notice kind="error">{error}</Notice>}
    <a className="text-button" href="/api/forecast/templates/traffic.csv">Tải mẫu CSV có tốc độ, lưu lượng và nhãn thực tế</a>
    <details className="help-details"><summary>Cách điền dữ liệu</summary><p>present_count: số xe trung bình đang hiện diện; crossing_count: số xe qua vạch trong coverage_seconds. avg_speed_kmh: tốc độ đã đo; free_flow_speed_kmh: tốc độ thông thoáng của đúng chiều đường. observed_length_m: chiều dài đã đo; lanes: số làn. window_end dùng thời gian có múi giờ, ví dụ 2026-11-01T17:05:00+07:00.</p><p>speed_calibrated, length_verified, training_allowed dùng true / false. verified_state dùng FREE / SLOW / JAM; verification_note ghi căn cứ đối chiếu thực tế. source ghi nguồn được phép dùng. Các cột mưa, tầm nhìn và sự cố có thể để trống nếu chưa biết; không điền 0 thay cho thiếu thông tin.</p></details>
    <label className="field">Tệp quan trắc CSV<input type="file" accept=".csv,text/csv" onChange={e=>{setFile(e.target.files?.[0]||null);setResult(null);}}/></label>
    <button type="button" className="button" disabled={busy||!file} onClick={()=>void run(()=>upload())}>{busy&&<Spinner/>}Kiểm tra tệp</button>
    {result&&<><Notice>{result.message} {result.rows} dòng · {result.usable} dòng đủ chất lượng · {result.updates} dòng đã tồn tại.</Notice>{result.preview&&<><div className="table-wrap"><table><thead><tr><th>Kết thúc ô</th><th>Tốc độ</th><th>Lưu lượng</th><th>Mật độ</th><th>Giảm tốc</th><th>Nhãn đã xác minh</th></tr></thead><tbody>{result.preview.map((row,i)=><tr key={i}><td>{dateTime(row.window_end)}</td><td>{value(row.metrics.avg_speed_kmh,' km/h')}</td><td>{value(row.metrics.flow_veh_per_hour,' xe/giờ')}</td><td>{value(row.metrics.density_veh_per_km,' xe/km')}</td><td>{value(row.metrics.congestion_index==null?null:row.metrics.congestion_index*100,'%')}</td><td>{stateText[row.verified_state||'']||'Chưa xác minh'}</td></tr>)}</tbody></table></div><button type="button" className="button primary" disabled={busy} onClick={()=>void run(()=>upload(true))}>Xác nhận nhập và thay thế các ô đã có</button></>}</>}
    <details className="help-details"><summary>Kiểm tra phục vụ và đối chiếu kết quả</summary><div className="button-row"><button className="button" disabled={busy||!road} onClick={()=>void run(async()=>{setForecast(await api(`/forecast/predict?target=traffic&segment_id=${road}&direction=${direction}`));})}>Xem dự báo từ quan trắc mới nhất</button><button className="button" disabled={busy||!road} onClick={()=>void run(async()=>{setOutcomes(await api(`/forecast/traffic/outcomes?segment_id=${road}&direction=${direction}`));})}>Đối chiếu khi đã có kết quả thực tế</button></div>
      {forecast&&<><Notice>{forecast.message}</Notice>{forecast.predictions.map(item=><p key={item.horizon_minutes}><b>Sau {item.horizon_minutes} phút: {stateText[item.label]}</b> · Khả năng ùn tắc {value(item.jam_probability*100,'%')} · Tốc độ {value(item.predicted_speed_kmh,' km/h')} · Giảm tốc {value(item.predicted_congestion_index==null?null:item.predicted_congestion_index*100,'%')} · {dateTime(item.predicted_at)}</p>)}</>}
      {outcomes&&<p>{outcomes.message} Đã chấm {outcomes.evaluated}/{outcomes.issued} lượt; tỷ lệ đúng {value(outcomes.accuracy==null?null:outcomes.accuracy*100,'%')}.</p>}
    </details>
  </section>;
}
