import {CloudRain,Construction} from 'lucide-react';
import type {CameraConditions as Conditions} from './cameraAnalysisData';

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
