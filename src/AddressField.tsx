import {useEffect,useId,useRef,useState} from 'react';
import {CheckCircle2,MapPin,Search,X} from 'lucide-react';
import {api} from './api';
import {type AddressPlace,type Waypoint} from './types';

export default function AddressField({label,value,onChange,onPick,picking}:{label:string;value:Waypoint|null;onChange:(place:Waypoint|null)=>void;onPick:()=>void;picking:boolean}) {
  const id=useId();const [text,setText]=useState(value?.name||'');const [results,setResults]=useState<AddressPlace[]>([]);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [open,setOpen]=useState(false);const [active,setActive]=useState(-1);
  const [attempt,setAttempt]=useState(0);const request=useRef(0);const dirty=useRef(false);const focused=useRef(false);
  useEffect(()=>{if(value){setText(value.name);setResults([]);setOpen(false);setError('');dirty.current=false;}else if(!dirty.current){setText('');setResults([]);setOpen(false);}},[value]);
  useEffect(()=>{
    if(!dirty.current||text.trim().length<3||value)return;
    const controller=new AbortController();const current=++request.current;
    const timer=setTimeout(async()=>{
      setBusy(true);setError('');
      try {
        const data=await api<{places:AddressPlace[]}>('/map/places?q='+encodeURIComponent(text.trim()),{signal:controller.signal});
        if(current!==request.current)return;setResults(data.places);setOpen(focused.current);setActive(-1);
        if(!data.places.length)setError('Chưa tìm thấy địa chỉ. Thử thêm tên đường, phường hoặc chọn ghim trên bản đồ.');
      } catch(e) {if(!controller.signal.aborted&&current===request.current){setError((e as Error).message);setResults([]);}}
      finally {if(current===request.current)setBusy(false);}
    },650);
    return()=>{clearTimeout(timer);controller.abort();};
  },[text,value,attempt]);
  function choose(place:AddressPlace){dirty.current=false;request.current++;onChange({lat:place.lat,lng:place.lng,name:place.name});setResults([]);setOpen(false);setError('');setBusy(false);setText(place.name);}
  return <div className="address-field" onFocus={()=>{focused.current=true;}} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget)){focused.current=false;setOpen(false);}}}>
    <label htmlFor={id}>{label}</label>
    <div className={`address-input ${value?'confirmed':''}`}>
      <MapPin size={16}/><input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open&&results.length>0} aria-controls={open&&results.length>0?id+'-results':undefined} aria-activedescendant={open&&active>=0?id+'-'+active:undefined}
        autoComplete="off" maxLength={240} placeholder="Số nhà, ngõ, tên đường, phường…" value={text} title={text}
        onChange={e=>{dirty.current=true;request.current++;setBusy(false);setText(e.target.value);setOpen(true);setActive(-1);setError('');setResults([]);onChange(null);}}
        onFocus={()=>{if(results.length)setOpen(true);}}
        onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);return;}if(e.key==='ArrowDown'){e.preventDefault();setOpen(true);setActive(i=>Math.min(results.length-1,i+1));}else if(e.key==='ArrowUp'){e.preventDefault();setActive(i=>Math.max(0,i-1));}else if(e.key==='Enter'){e.preventDefault();if(open&&active>=0&&results[active])choose(results[active]);else{dirty.current=true;setAttempt(a=>a+1);}}}}/>
      {text&&<button type="button" aria-label={`Xóa ${label.toLowerCase()}`} onClick={()=>{request.current++;dirty.current=false;setBusy(false);setText('');setResults([]);setOpen(false);setError('');onChange(null);}}><X size={14}/></button>}
      <button type="button" aria-label={`Tìm ${label.toLowerCase()}`} disabled={text.trim().length<3||busy} onClick={()=>{dirty.current=true;setAttempt(a=>a+1);}}><Search size={16}/></button>
    </div>
    {open&&results.length>0&&<ul id={id+'-results'} className="address-suggestions" role="listbox" aria-label={`Kết quả ${label.toLowerCase()}`}>{results.map((place,i)=><li id={id+'-'+i} key={place.id} role="option" aria-selected={i===active}><button type="button" onClick={()=>choose(place)}><MapPin size={15}/><span>{place.name}<small>{place.accuracy==='house'?'Có số nhà':place.accuracy==='street'?'Vị trí đường · kiểm tra ghim':'Địa điểm · kiểm tra ghim'}</small></span></button></li>)}</ul>}
    <div className="address-actions"><button type="button" className={picking?'active':''} onClick={onPick}><MapPin size={13}/>{picking?'Đang chọn trên bản đồ…':'Chọn trên bản đồ'}</button>{busy?<span role="status">Đang tìm địa chỉ…</span>:value?<span className="address-confirmed"><CheckCircle2 size={12}/>Đã chọn ghim</span>:null}</div>
    {value&&<p className="address-selected-label">{value.name}</p>}
    {error&&<p className="address-error" role="status">{error}</p>}
  </div>;
}
