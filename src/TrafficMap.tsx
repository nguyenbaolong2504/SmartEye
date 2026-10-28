import { useEffect, useRef, useState } from 'react';
import { Plus, Minus, LocateFixed, Layers } from 'lucide-react';
import { type Point, type Place, type Segment, type Route, densityColor } from './types';

declare global { interface Window { google: any; } }
let mapsPromise: Promise<void>|null = null;
function loadMaps(key: string) {
  if (!mapsPromise) mapsPromise = new Promise((resolve,reject) => {
    if (window.google?.maps) {resolve();return;}
    const script=document.createElement('script'); script.src=`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&loading=async&language=vi&region=VN`;
    script.onload=() => resolve(); script.onerror=() => {mapsPromise=null;reject(new Error('Không tải được Google Maps. Kiểm tra kết nối và khóa bản đồ.'));}; document.head.append(script);
  });
  return mapsPromise;
}

export function TrafficMap({places,segments,routes,selected,onSelect,browserKey,provider}: {places: Place[];segments: Segment[];routes: Route[];selected: string;onSelect: (id: string)=>void;browserKey: string;provider: string}) {
  const [zoom,setZoom]=useState(1); const [mapError,setMapError]=useState(''); const googleRef=useRef<HTMLDivElement>(null);
  const route=routes.find(r=>r.id===selected); const isGoogle=provider==='google';
  useEffect(() => {
    let disposed=false; const overlays:any[]=[];
    if (!isGoogle || !browserKey) return;
    loadMaps(browserKey).then(() => {
      if (disposed || !googleRef.current) return;
      const map=new window.google.maps.Map(googleRef.current,{center:{lat:21.03,lng:105.82},zoom:13,mapTypeControl:false,streetViewControl:false,fullscreenControl:false});
      const bounds=new window.google.maps.LatLngBounds();
      for (const r of routes) {
        const active=r.id===selected; const path=r.geometry.map(([lat,lng])=>({lat,lng}));
        const poly=new window.google.maps.Polyline({path,strokeColor:active?'#147d72':'#a3b4c2',strokeWeight:active?6:4,strokeOpacity:active?1:.6,map,zIndex:active?2:1});
        poly.addListener('click',()=>onSelect(r.id)); overlays.push(poly);
        if (active) {
          for (const p of path) bounds.extend(p);
          for (const interval of r.traffic_intervals) {
            const color=interval.speed==='TRAFFIC_JAM'?'#e45b64':interval.speed==='SLOW'?'#e7a42d':'#16a780';
            overlays.push(new window.google.maps.Polyline({path:path.slice(interval.start,interval.end+1),strokeColor:color,strokeWeight:6,map,zIndex:3}));
          }
          if (path.length) for (const [index,label] of [[0,'A'],[path.length-1,'B']] as const) overlays.push(new window.google.maps.Marker({position:path[index],map,label}));
        }
      }
      if (!bounds.isEmpty()) map.fitBounds(bounds,70);
      setMapError('');
    }).catch(e=>{if(!disposed)setMapError(e.message);});
    return ()=>{disposed=true;overlays.forEach(x=>x.setMap(null));};
  },[isGoogle,browserKey,routes,selected,onSelect]);
  const project=([lat,lng]:Point):Point=>[(lng-105.756)/.115*1000,650-(lat-20.997)/.082*650];
  const line=(points:Point[])=>points.map(p=>project(p).join(',')).join(' ');
  const viewSize=1000/zoom;
  return <div className="map-panel">
    <div className="map-top"><span className="map-label"><span className="live-dot"/>{isGoogle?'GOOGLE MAPS':'HÀ NỘI · SƠ ĐỒ MINH HỌA'}</span><span className="map-layer"><Layers size={14}/> Giao thông</span></div>
    {isGoogle ? <><div ref={googleRef} className="google-map"/>{mapError && <div className="map-error">{mapError}</div>}</> : <svg className="traffic-map" viewBox={`${(1000-viewSize)/2} ${(650-650/zoom)/2} ${viewSize} ${650/zoom}`} aria-label="Sơ đồ các tuyến đường minh họa tại Hà Nội">
      <defs><pattern id="city-grid" width="55" height="42" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)"><rect width="55" height="42" fill="#edf1ec"/><rect x="5" y="5" width="43" height="31" rx="3" fill="#e3e8e1" stroke="#d9e0d6" strokeWidth=".5"/></pattern><filter id="marker-shadow"><feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity=".15"/></filter></defs>
      <rect x="-500" y="-500" width="2000" height="1600" fill="url(#city-grid)"/>
      <path d="M570 -70 C520 -30 515 45 550 87 C580 115 602 173 654 150 C695 113 711 70 702 12 C685 -33 615 -60 570 -70Z" fill="#c8e4e5" stroke="#b4d7db" strokeWidth="2"/>
      <text x="610" y="65" className="lake-label">HỒ TÂY</text>
      <path d="M985 -70 C865 55 866 162 949 230 C1022 306 1027 362 1060 468" fill="none" stroke="#c8e4e5" strokeWidth="60"/>
      {[100,220,350,470,590,720,850].map(x=><path key={x} d={`M${x} -20 L${x-80} 700`} stroke="#fafbf7" strokeWidth="11"/>)}
      {[120,260,380,490,570].map(y=><path key={y} d={`M-20 ${y} Q450 ${y-50} 1050 ${y+30}`} fill="none" stroke="#fafbf7" strokeWidth="12"/>)}
      {segments.map(s=><g key={s.id}><polyline points={line(s.geometry)} fill="none" stroke="#fcfdf9" strokeWidth="15" strokeLinejoin="round"/><polyline points={line(s.geometry)} fill="none" stroke={s.observation?densityColor[s.observation.density]:'#c8d0c4'} strokeWidth="5" strokeLinejoin="round"/></g>)}
      {routes.filter(r=>r.id!==selected).map(r=><polyline key={r.id} points={line(r.geometry)} fill="none" stroke="#84a8ab" strokeWidth="7" strokeOpacity=".55" strokeLinejoin="round" onClick={()=>onSelect(r.id)} style={{cursor:'pointer'}}/>)}
      {route?.segments.map((s,i)=><g key={i}><polyline points={line(s.geometry)} fill="none" stroke="white" strokeWidth="13" strokeLinejoin="round"/><polyline points={line(s.geometry)} fill="none" stroke={s.density?densityColor[s.density]:'#72888b'} strokeWidth="7" strokeDasharray={s.density?undefined:'9 5'} strokeLinejoin="round"/></g>)}
      {places.map(p=>{const [x,y]=project([p.lat,p.lng]);return <g key={p.node}><circle cx={x} cy={y} r="5" fill="#fff" stroke="#b1bdb2" strokeWidth="2"/><text x={x+11} y={y-10} className="place-label"><title>{p.name}</title>{p.name.length>20?p.name.slice(0,19)+'…':p.name}</text></g>;})}
      {route && [route.geometry[0],route.geometry.at(-1)!].map((p,i)=>{const[x,y]=project(p);return <g key={i} filter="url(#marker-shadow)"><circle cx={x} cy={y} r="18" fill={i?'#172d33':'#177c71'} stroke="white" strokeWidth="4"/><text x={x} y={y+5} textAnchor="middle" fill="white" fontSize="14" fontWeight="700">{i?'B':'A'}</text></g>;})}
    </svg>}
    {!isGoogle && <div className="map-controls"><button onClick={()=>setZoom(z=>Math.min(2,z+.25))} aria-label="Phóng to"><Plus size={18}/></button><button onClick={()=>setZoom(z=>Math.max(.75,z-.25))} aria-label="Thu nhỏ"><Minus size={18}/></button><button onClick={()=>setZoom(1)} aria-label="Đặt lại bản đồ"><LocateFixed size={18}/></button></div>}
    <div className="map-bottom"><span>● <b>{isGoogle?'Tốc độ bình thường':'Thấp'}</b></span><span>● <b>{isGoogle?'Đi chậm':'Bình thường'}</b></span><span>● <b>{isGoogle?'Ùn tắc':'Cao'}</b></span><span>● <b>Chưa có dữ liệu</b></span></div>
    {!isGoogle&&<div className="map-credit">SmartEye · Mạng đường nghiên cứu, không dùng để dẫn đường</div>}
  </div>;
}
