import {useState} from 'react';
import {Modal} from './components';
import type {DetectionFrame,RoadGeometry} from './cameraAnalysisData';

export default function CameraRoadAssessment({geometry,frame}:{geometry?:RoadGeometry|null;frame:DetectionFrame}){
  const [open,setOpen]=useState(false);
  if(!geometry||frame.load_ratio==null)return null;
  return <section className="camera-road-assessment" aria-label="Đánh giá theo kích thước đường">
    <div className="camera-analysis-heading"><h3>Đường rộng hay hẹp được xét thế nào?</h3><button className="text-button" onClick={()=>setOpen(true)}>Xem cách tính</button></div>
    <div className="camera-road-metrics"><article><span>Vùng đường đang quan sát</span><b>{geometry.road_width_m} m × {geometry.observed_length_m} m</b><small>{geometry.lanes} làn · {geometry.calibration==='measured'?'Đã khai báo đo đạc':'Kích thước ước lượng'}</small></article>
      <article><span>Xe sau khi quy đổi theo loại</span><b>{frame.equivalent_count?.toLocaleString('vi-VN')} / {geometry.capacity_pcu.toLocaleString('vi-VN',{maximumFractionDigits:1})}</b><small>ô tô quy đổi / sức chứa ước tính</small></article>
      <article><span>Mức sử dụng sức chứa</span><b>{Math.round(frame.load_ratio*100)}%</b><small>{frame.motion_known?`${Math.round((frame.stopped_share??0)*100)}% xe theo dõi đang đứng hoặc nhích chậm`:'Chưa đủ xe được theo dõi để xét chuyển động'}</small></article></div>
    <p className="micro">Với cấu hình vùng đường này, khoảng {Math.ceil(geometry.high_density_pcu)} ô tô hoặc {Math.ceil(geometry.high_density_pcu/geometry.equivalents.motorcycle)} xe máy đã đạt mức mật độ cao nếu chỉ có một loại xe. Đây chưa phải kết luận ùn tắc.</p>
    <p className="micro">{frame.persistent_queue?'Có dấu hiệu hàng xe chờ kéo dài trên 30 giây; cần kiểm tra đèn tín hiệu và sự cố.':frame.motion_known&&(frame.stopped_share??0)>=.5?'Nhiều xe đang dừng hoặc nhích chậm; cần quan sát lâu hơn để phân biệt chờ đèn với ùn tắc.':'Hệ thống xét thêm chuyển động, lịch sử, thời tiết và sự cố khi dự báo.'}</p>
    {open&&<Modal title="Cách xét sức chứa từng vùng đường" onClose={()=>setOpen(false)}><div className="camera-forecast-explanation">
      <p>Vùng quan sát rộng <b>{geometry.road_width_m} m</b>, dài <b>{geometry.observed_length_m} m</b>. Phần có thể sử dụng được ước tính <b>{Math.round(geometry.usable_fraction*100)}%</b>, tương đương <b>{geometry.usable_area_m2} m²</b>.</p>
      <p>Sức chứa ước tính = diện tích sử dụng ÷ {geometry.car_space_m2} m² cho mỗi ô tô kể cả khoảng cách chờ, bằng <b>{geometry.capacity_pcu.toLocaleString('vi-VN',{maximumFractionDigits:1})} ô tô quy đổi</b>.</p>
      <p>Quy ước chạy thử: 1 ô tô = 1; 1 xe máy = {geometry.equivalents.motorcycle}; 1 xe buýt = {geometry.equivalents.bus}; 1 xe tải = {geometry.equivalents.truck} ô tô quy đổi.</p>
      <p>Khung hình này: {frame.vehicle_counts.car} ô tô + {frame.vehicle_counts.motorcycle} xe máy + {frame.vehicle_counts.bus} xe buýt + {frame.vehicle_counts.truck} xe tải = <b>{frame.equivalent_count} ô tô quy đổi</b>. Chia cho sức chứa được <b>{Math.round(frame.load_ratio!*100)}%</b>.</p>
      <p>Với cùng loại xe và chiều dài quan sát, đường rộng gấp đôi sẽ có sức chứa gấp đôi. Xe đông nhưng vẫn di chuyển được chưa đủ để gọi là ùn tắc. Chuyển động được ước lượng từ mã xe trong ảnh, chưa phải vận tốc km/h đã đo.</p>
      <p>{geometry.calibration_note} Không áp dụng các con số này như tiêu chuẩn chung cho mọi con đường.</p>
    </div></Modal>}
  </section>;
}
