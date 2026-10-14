import { X, AlertCircle, CheckCircle2, LoaderCircle } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { densityLabel, type Density } from './types';
export function DensityBadge({value}: {value: Density|null}) {return <span className={`density ${value || 'unknown'}`}><i/>{value ? densityLabel[value] : 'Chưa có dữ liệu'}</span>;}
export function Notice({children, kind = 'info'}: {children: ReactNode; kind?: 'info'|'error'|'success'}) {return <div className={`notice ${kind}`}>{kind === 'success' ? <CheckCircle2 size={17}/> : <AlertCircle size={17}/>}<span>{children}</span></div>;}
export function Empty({children}: {children: ReactNode}) {return <div className="empty"><div className="empty-icon">◎</div>{children}</div>;}
export function Spinner() {return <LoaderCircle size={17} className="spin"/>;}
export function Modal({title,children,onClose}: {title: string; children: ReactNode; onClose: () => void}) {
  const ref=useRef<HTMLElement>(null);const closeRef=useRef(onClose);closeRef.current=onClose;
  useEffect(()=>{const previous=document.activeElement as HTMLElement;const node=ref.current;const focusable=()=>Array.from(node?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]')||[]);focusable()[0]?.focus();function key(e:KeyboardEvent){if(e.key==='Escape')closeRef.current();if(e.key==='Tab'){const list=focusable();if(!list.length)return;const first=list[0],last=list[list.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus();};},[]);
  return <div className="modal-backdrop" onMouseDown={e => {if (e.target === e.currentTarget) onClose();}}><section ref={ref} role="dialog" aria-modal="true" aria-label={title} className="modal"><div className="modal-head"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={20}/></button></div>{children}</section></div>;
}
