import {useEffect,useRef,useState} from 'react';
import {type Route} from './types';
declare global {interface Window {google:any;}}
let loading:Promise<void>|null=null;
function load(key:string){
  if(window.google?.maps?.Map)return Promise.resolve();
  if(!loading)loading=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&loading=async&language=vi&region=VN`;script.onload=()=>resolve();script.onerror=()=>{loading=null;reject(new Error('Không tải được Google Maps. Kiểm tra khóa bản đồ và kết nối.'));};document.head.append(script);});
  return loading;
}
export default function GoogleStreetMap({browserKey,routes,selected,onSelect}:{browserKey:string;routes:Route[];selected:string;onSelect:(id:string)=>void}){
  const host=useRef<HTMLDivElement>(null);const [error,setError]=useState('');
  useEffect(()=>{let disposed=false;const overlays:any[]=[];
    load(browserKey).then(()=>{if(disposed||!host.current)return;const map=new window.google.maps.Map(host.current,{center:{lat:21.03,lng:105.82},zoom:14,mapTypeControl:false,streetViewControl:false,fullscreenControl:true});const bounds=new window.google.maps.LatLngBounds();
      for(const route of routes){const active=route.id===selected;const path=route.geometry.map(([lat,lng])=>({lat,lng}));const line=new window.google.maps.Polyline({map,path,strokeColor:active?'#147d72':'#99aab7',strokeWeight:active?6:4,zIndex:active?2:1});line.addListener('click',()=>onSelect(route.id));overlays.push(line);
        if(active){path.forEach((point:{lat:number;lng:number})=>bounds.extend(point));for(const interval of route.traffic_intervals)overlays.push(new window.google.maps.Polyline({map,path:path.slice(interval.start,interval.end+1),strokeColor:interval.speed==='TRAFFIC_JAM'?'#e45b64':interval.speed==='SLOW'?'#e7a42d':'#16a780',strokeWeight:6,zIndex:3}));if(path.length)for(const[index,label]of[[0,'A'],[path.length-1,'B']]as const)overlays.push(new window.google.maps.Marker({position:path[index],map,label}));}}
      if(!bounds.isEmpty())map.fitBounds(bounds,60);setError('');
    }).catch(e=>{if(!disposed)setError(e.message);});return()=>{disposed=true;overlays.forEach(overlay=>overlay.setMap(null));};
  },[browserKey,routes,selected,onSelect]);
  return <><div ref={host} className="street-map google-map" aria-label="Bản đồ Google Maps"/>{error&&<p className="map-error">{error}</p>}</>;
}
