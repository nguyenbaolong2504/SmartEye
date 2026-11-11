import {useEffect,useRef,useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {Expand,Layers,LocateFixed,MapPin,Minimize,X} from 'lucide-react';
import {type Waypoint,type Place,type Segment,type Route,densityColor} from './types';
import GoogleStreetMap from './GoogleStreetMap';

type Props={places:Place[];segments:Segment[];routes:Route[];selected:string;onSelect:(id:string)=>void;browserKey:string;provider:string;
  origin?:Waypoint|null;destination?:Waypoint|null;picking?:'origin'|'destination'|null;onPick?:(point:[number,number])=>void;tileUrl?:string;
  cameraMarkers?:{id:string;name:string;position:[number,number];available:boolean}[];selectedCameraId?:string;onCameraSelect?:(id:string)=>void;};
const textNode=(text:string)=>{const element=document.createElement('span');element.textContent=text;return element;};
export function TrafficMap({segments,routes,selected,onSelect,browserKey,provider,origin,destination,picking,onPick,tileUrl,cameraMarkers,selectedCameraId,onCameraSelect}:Props){
  const host=useRef<HTMLDivElement>(null);const map=useRef<L.Map|null>(null);const drawings=useRef<L.LayerGroup|null>(null);
  const callbacks=useRef({picking,onPick,onSelect,onCameraSelect});callbacks.current={picking,onPick,onSelect,onCameraSelect};
  const [expanded,setExpanded]=useState(false);const [tilesFailed,setTilesFailed]=useState(false);const [trafficVisible,setTrafficVisible]=useState(true);
  const google=provider==='google'&&!!browserKey;const fitted=useRef('');
  const cameraMode=cameraMarkers!==undefined;
  useEffect(()=>{
    if(google||!host.current)return;
    const instance=L.map(host.current,{center:[21.033,105.827],zoom:14,minZoom:cameraMode?5:10,maxZoom:19,zoomControl:false,preferCanvas:true,scrollWheelZoom:false});
    map.current=instance;drawings.current=L.layerGroup().addTo(instance);
    L.control.zoom({position:'bottomright',zoomInTitle:'Phóng to',zoomOutTitle:'Thu nhỏ'}).addTo(instance);
    instance.getContainer().querySelector('.leaflet-control-zoom-in')?.setAttribute('aria-label','Phóng to');instance.getContainer().querySelector('.leaflet-control-zoom-out')?.setAttribute('aria-label','Thu nhỏ');
    L.control.scale({position:'bottomleft',imperial:false}).addTo(instance);
    const tiles=L.tileLayer(tileUrl||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'}).addTo(instance);
    tiles.on('tileerror',()=>setTilesFailed(true));tiles.on('tileload',()=>setTilesFailed(false));
    instance.on('click',(event:L.LeafletMouseEvent)=>{if(callbacks.current.picking)callbacks.current.onPick?.([event.latlng.lat,event.latlng.lng]);});
    const resize=new ResizeObserver(()=>instance.invalidateSize());resize.observe(host.current);
    return()=>{resize.disconnect();instance.remove();map.current=null;drawings.current=null;fitted.current='';};
  },[google,tileUrl,cameraMode]);
  useEffect(()=>{
    const instance=map.current,layer=drawings.current;if(!instance||!layer)return;
    layer.clearLayers();
    if(cameraMarkers){
      for(const camera of cameraMarkers){
        const chosen=camera.id===selectedCameraId;
        const icon=L.divIcon({className:`camera-map-pin ${chosen?'chosen':''} ${camera.available?'available':'unavailable'}`,
          html:'<span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="6" width="13" height="12" rx="3"/><path d="m16 10 5-3v10l-5-3"/></svg></span>',
          iconSize:[36,36],iconAnchor:[18,18]});
        const marker=L.marker(camera.position,{icon,keyboard:true,title:camera.name,alt:camera.name,zIndexOffset:chosen?1000:0})
          .bindTooltip(textNode(camera.name)).on('click',()=>callbacks.current.onCameraSelect?.(camera.id)).addTo(layer);
        marker.getElement()?.setAttribute('aria-label',`Xem ${camera.name}`);
        marker.getElement()?.setAttribute('aria-pressed',String(chosen));
      }
      const signature=JSON.stringify(cameraMarkers.map(camera=>[camera.id,camera.position]));
      if(signature!==fitted.current&&cameraMarkers.length){
        instance.fitBounds(L.latLngBounds(cameraMarkers.map(camera=>camera.position)),{padding:[48,60],maxZoom:15});
        fitted.current=signature;
      }
      const chosen=cameraMarkers.find(camera=>camera.id===selectedCameraId);
      if(chosen&&!instance.getBounds().contains(chosen.position))instance.panTo(chosen.position);
      return;
    }
    if(trafficVisible)for(const segment of segments.filter(segment=>segment.active&&!segment.is_demo)){
      L.polyline(segment.geometry,{color:segment.observation?densityColor[segment.observation.density]:'#8497a3',weight:5,opacity:.8,dashArray:segment.observation?undefined:'5 5'}).bindTooltip(textNode(segment.name+(segment.observation?'':' · chưa có quan sát mới'))).addTo(layer);
    }
    const active=routes.find(route=>route.id===selected);
    for(const route of [...routes].sort((a,b)=>Number(a.id===selected)-Number(b.id===selected))){
      const chosen=route.id===selected;
      L.polyline(route.geometry,{color:chosen?'#ffffff':'#637eaa',weight:chosen?10:5,opacity:chosen?1:.55}).addTo(layer);
      L.polyline(route.geometry,{color:chosen?'#286bd2':'#728cb5',weight:chosen?6:4,opacity:chosen?1:.7}).on('click',()=>callbacks.current.onSelect(route.id)).bindTooltip(textNode(route.name)).addTo(layer);
      if(chosen&&trafficVisible)for(const segment of route.segments.filter(segment=>segment.density&&segment.geometry.length>1))L.polyline(segment.geometry,{color:densityColor[segment.density!],weight:6}).addTo(layer);
    }
    const points=[origin||active&&{lat:active.geometry[0][0],lng:active.geometry[0][1],name:'Điểm xuất phát'},destination||active&&{lat:active.geometry.at(-1)![0],lng:active.geometry.at(-1)![1],name:'Điểm đến'}];
    points.forEach((point,index)=>{if(!point)return;const icon=L.divIcon({className:'street-pin',html:`<span class="${index?'destination':'origin'}"><b>${index?'B':'A'}</b></span>`,iconSize:[34,42],iconAnchor:[17,40]});L.marker([point.lat,point.lng],{icon}).bindTooltip(textNode(point.name)).addTo(layer);});
    const signature=active?selected+JSON.stringify(active.geometry):JSON.stringify(points);
    if(signature!==fitted.current){
      const bounds=active?.geometry.length?L.latLngBounds(active.geometry):L.latLngBounds(points.filter(Boolean).map(point=>[point!.lat,point!.lng]));
      if(bounds.isValid())instance.fitBounds(bounds,{padding:[45,65],maxZoom:17});fitted.current=signature;
    }
  },[segments,routes,selected,origin,destination,trafficVisible,google,cameraMarkers,selectedCameraId]);
  useEffect(()=>{map.current?.getContainer().classList.toggle('map-picking',!!picking);},[picking,google]);
  useEffect(()=>{if(!expanded)return;const previous=document.body.style.overflow;document.body.style.overflow='hidden';const key=(e:KeyboardEvent)=>{if(e.key==='Escape')setExpanded(false);};window.addEventListener('keydown',key);return()=>{document.body.style.overflow=previous;window.removeEventListener('keydown',key);};},[expanded]);
  function reset(){const active=routes.find(route=>route.id===selected);if(cameraMarkers?.length)map.current?.fitBounds(L.latLngBounds(cameraMarkers.map(camera=>camera.position)),{padding:[48,60],maxZoom:15});else if(active?.geometry.length)map.current?.fitBounds(L.latLngBounds(active.geometry),{padding:[50,60]});else map.current?.setView([21.033,105.827],14);}
  return <div className={`map-panel street-map-panel ${expanded?'map-expanded':''}`}>
    {google?<GoogleStreetMap browserKey={browserKey} routes={routes} selected={selected} onSelect={onSelect} origin={origin} destination={destination} picking={picking} onPick={onPick}/>:<div ref={host} className="street-map" role="region" aria-label={cameraMode?'Bản đồ camera giao thông':'Bản đồ đường phố OpenStreetMap'}/>}
    <div className="street-map-toolbar"><span className="map-label"><span className="live-dot"/>{google?'Google Maps':cameraMode?'OpenStreetMap':'OpenStreetMap · Hà Nội'}</span><div>
      {!google&&<>{!cameraMode&&<button type="button" className={trafficVisible?'active':''} aria-label="Ẩn hoặc hiện quan sát giao thông" aria-pressed={trafficVisible} onClick={()=>setTrafficVisible(v=>!v)}><Layers size={16}/><span>Giao thông</span></button>}<button type="button" aria-label={cameraMode?'Xem toàn bộ camera':'Xem toàn bộ hành trình'} onClick={reset}><LocateFixed size={17}/></button></>}
      <button type="button" aria-label={expanded?'Thu gọn bản đồ':'Mở rộng bản đồ'} onClick={()=>setExpanded(v=>!v)}>{expanded?<Minimize size={17}/>:<Expand size={17}/>}</button>
    </div></div>
    {picking&&<div className="map-pick-hint" role="status"><MapPin size={17}/>Chạm bản đồ để chọn {picking==='origin'?'điểm xuất phát':'điểm đến'}.</div>}
    {tilesFailed&&!google&&<div className="map-network-error" role="status">Chưa tải được nền bản đồ. Kiểm tra Internet; ghim và tuyến vẫn giữ nguyên.<button type="button" aria-label="Đóng thông báo bản đồ" onClick={()=>setTilesFailed(false)}><X size={14}/></button></div>}
    {!google&&<div className="street-map-legend">{cameraMode?<><span><i style={{background:'#168b75'}}/>Có hình ảnh</span><span><i style={{background:'#8497a3'}}/>Chưa có hình ảnh hoặc đã tắt</span></>:<><span><i style={{background:'#286bd2'}}/>Tuyến đang chọn</span><span><i style={{background:densityColor.LOW}}/>Thấp</span><span><i style={{background:densityColor.NORMAL}}/>Bình thường</span><span><i style={{background:densityColor.HIGH}}/>Cao</span><span><i style={{background:'#8497a3'}}/>Chưa có quan sát</span></>}</div>}
    {provider==='demo'&&<div className="street-demo-note">Tuyến minh họa · không phải hình học đường thực</div>}
  </div>;
}
