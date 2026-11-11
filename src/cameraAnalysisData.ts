import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import type {Density} from './types';

export type VehicleCounts={car:number;motorcycle:number;bus:number;truck:number};
export type DetectionBox={box:[number,number,number,number];label:keyof VehicleCounts;confidence:number};
export type DetectionFrame={second:number;frame_index?:number;count:number;score:number;occupancy:number;density:Density;vehicle_counts:VehicleCounts;boxes?:DetectionBox[];width?:number;height?:number};
export type CameraPrediction={horizon_minutes:number;label:Density;congestion_label?:'FREE'|'SLOW'|'JAM';congestion_probability?:number;
  congestion_probabilities?:Record<'FREE'|'SLOW'|'JAM',number>;history?:{lookback_days:number;matching_days:number;jam_days:number;hour:string;is_demo:boolean}};
export type CameraAnalysisData={state:string;progress:number;message:string;is_demo:boolean;samples?:DetectionFrame[];frames?:DetectionFrame[];fps?:number;roi?:number[];capacity?:number;duration_seconds?:number;high_threshold?:number;
  average_count?:number;peak_count?:number;frame_url?:string;method?:string;detection_version?:number;
  source?:{title:string;author:string;page_url:string;license:string;license_url:string;published_date:string;location_note:string};
  forecast?:{is_demo:boolean;reference_at?:string;message:string;probability_kind?:string;real_world_validated?:boolean;
    timeline:{second:number;predictions:CameraPrediction[]}[]}|null};
export const emptyAnalysis:CameraAnalysisData={state:'queued',progress:0,message:'Đang tải kết quả nhận diện.',is_demo:true};
export function atTime<T extends {second:number}>(items:T[],second:number):T|undefined {
  let low=0,high=items.length;
  while(low<high){const middle=(low+high)>>>1;if(items[middle].second<=second+.0005)low=middle+1;else high=middle;}
  return items[Math.max(0,low-1)];
}
export function useCameraAnalysis(url?:string){
  const [version,setVersion]=useState(0);
  const [value,setValue]=useState<{url?:string;data:CameraAnalysisData;error:string}>({data:emptyAnalysis,error:''});
  const reload=useCallback(()=>setVersion(v=>v+1),[]);
  useEffect(()=>{
    if(!url)return;
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
    async function load(){
      try{
        const data=await api<CameraAnalysisData>(url!.replace(/^\/api(?=\/)/,''),{signal:controller.signal});
        if(controller.signal.aborted)return;
        setValue({url,data,error:''});
        if(['queued','processing'].includes(data.state))timer=setTimeout(load,2500);
      }catch(error){if(!controller.signal.aborted)setValue({url,data:emptyAnalysis,error:(error as Error).message});}
    }
    void load();return()=>{controller.abort();clearTimeout(timer);};
  },[url,version]);
  return {data:value.url===url?value.data:emptyAnalysis,error:value.url===url?value.error:'',reload};
}
