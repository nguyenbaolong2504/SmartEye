import {useEffect,useRef,useState} from 'react';
import {CloudRain,Construction,TriangleAlert} from 'lucide-react';
import {api,json} from './api';
import {Notice} from './components';
import type {CameraConditions as Conditions,CameraForecast} from './cameraAnalysisData';

const roadNames={accident:'Tai nạn',roadwork:'Đang thi công',obstruction:'Có vật cản',flood:'Ngập đường',wet_surface:'Mặt đường có thể ướt'};
export function ConditionsSummary({value}:{value?:Conditions}){
  if(!value)return <p className="micro">Chưa có thông tin thời tiết và điều kiện đường cho lượt phân tích này.</p>;
  const weather=value.weather;
  const flags=(Object.keys(roadNames) as (keyof typeof roadNames)[]).filter(key=>value.road[key]);
  const simulated=weather.source==='demo_override'||value.road.source.includes('demo_override');
  return <div className="camera-condition-summary">
    <article><h4><CloudRain size={16}/>Thời tiết</h4>{weather.known?<><b>{(weather.visibility_km??10)<1?'Tầm nhìn hạn chế':(weather.rain_mm??0)>=5?'Mưa lớn':weather.rain_mm?'Có mưa':'Không mưa'}</b>
      <p>Mưa {weather.rain_mm} mm · Tầm nhìn {weather.visibility_km} km · Gió {weather.wind_kmh} km/h</p>
      {weather.at&&<small>Mốc {new Date(weather.at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})}</small>}</>:<b>Chưa có dữ liệu</b>}
      <small>{weather.source==='demo_override'?'Giả định để chạy thử':<a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Thời tiết khu vực · Open-Meteo</a>}</small></article>
    <article><h4><Construction size={16}/>Sự cố và mặt đường</h4><b>{flags.length?flags.map(key=>roadNames[key]).join(' · '):value.road.checked?'Chưa ghi nhận cảnh báo phù hợp':'Chưa có dữ liệu'}</b><p>{value.road.message}</p></article>
    <p className="micro">{simulated?'Có điều kiện giả định do bạn chọn. ':''}{value.location_note}</p>
  </div>;
}

export default function CameraConditions({value,url,onResult,onPause}:{value?:Conditions;url?:string;onResult:(forecast:CameraForecast)=>void;onPause:()=>void}){
  const [weather,setWeather]=useState('auto'),[road,setRoad]=useState('auto'),[incident,setIncident]=useState('auto');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function apply(){
    if(!url)return;
    request.current?.abort();const controller=new AbortController();request.current=controller;
    setBusy(true);setError('');onPause();
    try{
      const data=await api<CameraForecast>(url.replace(/^\/api(?=\/)/,''),{...json({weather,road_condition:road,incident}),signal:controller.signal});
      if(!controller.signal.aborted)onResult(data);
    }catch(error){if(!controller.signal.aborted)setError((error as Error).message);}
    finally{if(!controller.signal.aborted)setBusy(false);}
  }
  return <section className="camera-conditions" aria-label="Điều kiện dùng để dự báo"><h3><TriangleAlert size={18}/>Điều kiện đang được xét</h3>
    <ConditionsSummary value={value}/>
    {url&&<details><summary>Thử thay đổi thời tiết hoặc tình trạng đường</summary><p>Chọn tình huống để xem dự báo thay đổi thế nào. Chỉ áp dụng cho lần xem của bạn.</p>
      <div className="camera-condition-inputs"><label className="field">Thời tiết<select aria-label="Thời tiết" value={weather} onChange={e=>setWeather(e.target.value)}><option value="auto">Lấy theo khu vực</option><option value="dry">Không mưa</option><option value="light">Mưa nhẹ</option><option value="heavy">Mưa lớn</option><option value="fog">Sương mù, tầm nhìn kém</option></select></label>
        <label className="field">Mặt đường<select aria-label="Mặt đường" value={road} onChange={e=>setRoad(e.target.value)}><option value="auto">Theo cảnh báo đã công bố</option><option value="normal">Bình thường (giả định)</option><option value="roadwork">Đang thi công</option><option value="obstruction">Có vật cản</option><option value="flood">Ngập đường</option></select></label>
        <label className="field">Sự cố<select aria-label="Sự cố" value={incident} onChange={e=>setIncident(e.target.value)}><option value="auto">Theo cảnh báo đã công bố</option><option value="none">Không có (giả định)</option><option value="accident">Tai nạn</option></select></label>
        <button className="button primary" disabled={busy} onClick={()=>void apply()}>{busy?'Đang xem xét…':'Cập nhật dự báo'}</button></div>
      {error&&<Notice kind="error">{error}</Notice>}
    </details>}
  </section>;
}
