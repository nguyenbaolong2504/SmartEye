import { CheckCircle2, GitCompareArrows, Route as RouteIcon } from 'lucide-react';
import { type RouteOptimization as Optimization, type Route } from './types';

export default function RouteOptimization({optimization,route}:{optimization:Optimization;route?:Route}) {
  const w=optimization.normalized_weights;
  return <section className="card route-optimization">
    <div className="section-title"><GitCompareArrows size={19}/><h2>{optimization.scope!=='google_candidates'?'Tối ưu thời gian + khoảng cách':'So sánh các tuyến Google cung cấp'}</h2>{optimization.agreement&&<span className="optimization-verified"><CheckCircle2 size={14}/>Hai thuật toán cùng điểm tối ưu</span>}</div>
    <p className="optimization-summary">Ưu tiên thời gian <b>{Math.round(w.time*100)}%</b> · khoảng cách <b>{Math.round(w.distance*100)}%</b>{w.density>0&&<> · phạt rủi ro tích lũy <b>{Math.round(w.density*100)}%</b></>}.</p>
    {route?.cost_components&&<div className="cost-breakdown"><span>Thời gian<strong>{route.cost_components.time.toFixed(3)}</strong></span><span>Khoảng cách<strong>{route.cost_components.distance.toFixed(3)}</strong></span>{w.density>0&&<span>Rủi ro tích lũy<strong>{route.cost_components.density.toFixed(3)}</strong></span>}<span className="total-cost">Điểm chi phí<strong>{route.score.toFixed(3)}</strong></span></div>}
    <p className="micro">Điểm thấp hơn phù hợp hơn với ưu tiên đã chọn. Tuyến có thể dài hơn nhưng tiết kiệm thời gian; điểm chi phí không phải xác suất ùn tắc.</p>
    <details className="help-details"><summary><RouteIcon size={14}/>Cách tính và kết quả thuật toán</summary><p>Điểm = w thời gian × T/T₀ + w khoảng cách × D/D₀{w.density>0?' + w rủi ro × tổng(km × mức rủi ro)/D₀':''}. T₀ = {(optimization.references.time_seconds/60).toFixed(2)} phút, D₀ = {optimization.references.distance_km.toFixed(2)} km.</p><p>{optimization.scope!=='google_candidates'?'T₀ là thời gian nhanh nhất và D₀ là khoảng cách ngắn nhất trên cùng đồ thị. Hai mốc được cố định trước khi tìm tuyến kết hợp.':'Hai mốc lấy từ tập ứng viên Google; không cam kết tối ưu trên toàn bộ mạng đường.'}</p>
    {Object.keys(optimization.primary_search).length>0&&<div className="table-wrap"><table><thead><tr><th>Thuật toán</th><th>Chi phí tối ưu</th><th>Nút đã mở rộng</th><th>Thời gian lượt chính</th></tr></thead><tbody>{Object.entries(optimization.primary_search).map(([name,info])=><tr key={name}><td>{name==='astar'?'A*':'Dijkstra'}</td><td>{info.cost?.toFixed(6)??'—'}</td><td>{info.expanded_nodes}</td><td>{info.elapsed_ms.toFixed(3)} ms</td></tr>)}</tbody></table></div>}
    <p>{optimization.note}</p><p>{optimization.scope==='osm_network'?'ETA dựa trên loại đường, giới hạn tốc độ được gắn thẻ và quan sát phù hợp nếu có; không phải tốc độ giao thông trực tiếp.':'Vận tốc trên mạng cấu hình là tham chiếu theo loại phương tiện và mật độ, chưa phải tốc độ đo từ camera.'} Các thuật toán dùng chi phí cố định trong mỗi lần tìm.</p></details>
  </section>;
}
