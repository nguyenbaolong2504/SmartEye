import type {RoadProfile} from './types';
export default function RoadProfileFields({value,onChange}:{value:RoadProfile|null;onChange:(value:RoadProfile|null)=>void}){
  return <div className="camera-profile-fields"><label className="check"><input type="checkbox" checked={Boolean(value)} onChange={e=>onChange(e.target.checked?{lanes:2,road_width_m:7,observed_length_m:70,usable_fraction:.85,calibration:'estimated'}:null)}/>Đánh giá theo kích thước vùng đường</label>
    {value&&<><div className="two-columns"><label className="field">Số làn trong vùng quan sát<input type="number" required min={1} max={12} value={value.lanes} onChange={e=>onChange({...value,lanes:Number(e.target.value)})}/></label>
      <label className="field">Tổng bề rộng mặt đường (m)<input type="number" required min={2} max={60} step="0.1" value={value.road_width_m} onChange={e=>onChange({...value,road_width_m:Number(e.target.value)})}/></label>
      <label className="field">Chiều dài nhìn thấy (m)<input type="number" required min={5} max={500} step="0.1" value={value.observed_length_m} onChange={e=>onChange({...value,observed_length_m:Number(e.target.value)})}/></label>
      <label className="field">Phần diện tích có thể sử dụng (%)<input type="number" required min={10} max={100} value={Math.round(value.usable_fraction*100)} onChange={e=>onChange({...value,usable_fraction:Number(e.target.value)/100})}/></label></div>
      <label className="field">Nguồn kích thước<select value={value.calibration} onChange={e=>onChange({...value,calibration:e.target.value as RoadProfile['calibration']})}><option value="estimated">Ước lượng để chạy thử</option><option value="measured">Đã đo tại vùng đường này</option></select></label>
      <p className="micro">Chỉ khai báo phần mặt đường trong vùng quan sát; loại vỉa hè, dải phân cách và phần bị che. Sức chứa được tính theo diện tích sử dụng và loại xe, thay cho số xe cố định. Thay kích thước cần phân tích lại video.</p></>}
  </div>;
}
