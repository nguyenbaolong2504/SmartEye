import {useEffect,useRef,useState} from 'react';
import {type Route,type Waypoint} from './types';
declare global {interface Window {google:any;__smartEyeGoogleReady?:()=>void;}}
let loading:Promise<void>|null=null;
function load(key:string){
  if(window.google?.maps?.Map)return Promise.resolve();
  if(!loading)loading=new Promise<void>((resolve,reject)=>{
    const script=document.createElement('script');
    const timeout=setTimeout(()=>{loading=null;script.remove();reject(new Error('Bản đồ đang phản hồi chậm. Vui lòng thử lại.'));},12000);
    window.__smartEyeGoogleReady=()=>{clearTimeout(timeout);resolve();};
    script.src=`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&loading=async&callback=__smartEyeGoogleReady&language=vi&region=VN`;
    script.onerror=()=>{clearTimeout(timeout);loading=null;reject(new Error('Chưa tải được Google Maps. Vui lòng thử lại sau.'));};document.head.append(script);
  });
  return loading;
}
export default function GoogleStreetMap({browserKey,routes,selected,onSelect,origin,destination,picking,onPick}:{browserKey:string;routes:Route[];selected:string;onSelect:(id:string)=>void;origin?:Waypoint|null;destination?:Waypoint|null;picking?:'origin'|'destination'|null;onPick?:(p:[number,number])=>void}){
  const host=useRef<HTMLDivElement>(null);const map=useRef<any>(null);const callbacks=useRef({onPick,picking});callbacks.current={onPick,picking};
  const[error,setError]=useState('');const[ready,setReady]=useState(false);
  useEffect(()=>{let disposed=false;setReady(false);
    load(browserKey).then(()=>{if(disposed||!host.current)return;
      map.current=new window.google.maps.Map(host.current,{center:{lat:21.03,lng:105.82},zoom:14,mapTypeControl:false,streetViewControl:false,fullscreenControl:true});
      map.current.addListener('click',(event:any)=>{if(callbacks.current.picking&&event.latLng)callbacks.current.onPick?.([event.latLng.lat(),event.latLng.lng()]);});setReady(true);setError('');
    }).catch(e=>{if(!disposed)setError(e.message);});
    return()=>{disposed=true;if(map.current)window.google?.maps?.event?.clearInstanceListeners(map.current);map.current=null;};
  },[browserKey]);
  useEffect(()=>{if(!ready||!map.current)return;const overlays:any[]=[];const bounds=new window.google.maps.LatLngBounds();
    for(const route of routes){const active=route.id===selected;const path=route.geometry.map(([lat,lng])=>({lat,lng}));
      const line=new window.google.maps.Polyline({map:map.current,path,strokeColor:active?'#286bd2':'#99aab7',strokeWeight:active?6:4,zIndex:active?2:1});line.addListener('click',()=>onSelect(route.id));overlays.push(line);
      if(active){path.forEach((p:{lat:number;lng:number})=>bounds.extend(p));for(const interval of route.traffic_intervals)overlays.push(new window.google.maps.Polyline({map:map.current,path:path.slice(interval.start,interval.end+1),strokeColor:interval.speed==='TRAFFIC_JAM'?'#e45b64':interval.speed==='SLOW'?'#e7a42d':'#16a780',strokeWeight:6,zIndex:3}));}
    }
    [origin,destination].forEach((point,index)=>{if(!point)return;const position={lat:point.lat,lng:point.lng};bounds.extend(position);overlays.push(new window.google.maps.Marker({position,map:map.current,label:index?'B':'A'}));});
    if(!bounds.isEmpty())map.current.fitBounds(bounds,60);
    return()=>{overlays.forEach(overlay=>overlay.setMap(null));};
  },[ready,routes,selected,onSelect,origin,destination]);
  return <><div ref={host} className="street-map google-map" role="region" aria-label="Bản đồ Google Maps"/>{error&&<p className="map-error">{error}</p>}</>;
}
