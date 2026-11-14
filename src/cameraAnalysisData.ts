import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import type {Density,RoadProfile} from './types';

export type VehicleCounts={car:number;motorcycle:number;bus:number;truck:number};
export type DetectionBox={box:[number,number,number,number];label:keyof VehicleCounts;confidence:number;track_id?:number|null;counted_as?:string|null};
export type TrafficMetrics={flow_veh_per_hour:number|null;density_veh_per_km:number|null;density_veh_per_km_per_lane:number|null;avg_speed_kmh:number|null;free_flow_speed_kmh:number|null;congestion_index:number|null;travel_time_index:number|null;quality?:{speed_calibrated?:boolean;length_verified?:boolean;short_window?:boolean;observation_seconds?:number;count_line_verified?:boolean}};
export type VideoMeasurements={count_line:number[][];crossings:number;count_line_verified:boolean;speed_calibration_available:boolean;note:string};
export type DetectionFrame={second:number;frame_index?:number;count:number;score:number;occupancy:number;density:Density;vehicle_counts:VehicleCounts;boxes?:DetectionBox[];width?:number;height?:number;cumulative_count?:number;cumulative_vehicle_counts?:VehicleCounts;
  equivalent_count?:number;capacity_pcu?:number;load_ratio?:number;motion_known?:boolean;stopped_share?:number|null;motion_samples?:number;motion_coverage?:number;queue_seconds?:number;persistent_queue?:boolean;traffic_metrics?:TrafficMetrics;crossing_count?:number};
export type RoadGeometry=RoadProfile&{usable_area_m2:number;capacity_pcu:number;car_space_m2:number;equivalents:VehicleCounts;high_density_pcu:number;calibration_note:string};
export type CameraPrediction={horizon_minutes:number;label:Density;congestion_label?:'FREE'|'SLOW'|'JAM';congestion_probability?:number;
  predicted_speed_kmh?:number;predicted_congestion_index?:number;predicted_travel_time_index?:number|null;free_flow_speed_kmh?:number;numeric_prediction_source?:string;
  congestion_probabilities?:Record<'FREE'|'SLOW'|'JAM',number>;history?:{lookback_days:number;matching_days:number;jam_days:number;hour:string;is_demo:boolean}};
export type CameraConditions={weather:{known:boolean;rain_mm?:number|null;visibility_km?:number|null;wind_kmh?:number|null;source:string;source_url?:string;at?:string|null;message?:string};
  road:{checked:boolean;accident?:boolean;roadwork?:boolean;obstruction?:boolean;flood?:boolean;wet_surface?:boolean;source:string;notice_count?:number;message?:string};
  reference_at?:string;location_note?:string;overrides?:{weather?:string;road_condition?:string;incident?:string}};
export type CameraForecast={is_demo:boolean;reference_at?:string;message:string;probability_kind?:string;real_world_validated?:boolean;
  analysis_id?:string;scope?:'video'|'frames';basis?:DetectionFrame|null;road_geometry?:RoadGeometry|null;
  measurements?:VideoMeasurements;
  summary?:{start_second:number;end_second:number;observed_seconds:number;frames:number;median_count:number;median_score:number;median_load_ratio?:number;motion_known:boolean;stopped_share?:number|null;representative_second:number;traffic_metrics?:TrafficMetrics}|null;
  evaluation?:Record<string,{test:{accuracy:number;samples:number};test_calibration_error:number;accuracy_target_met:boolean;speed?:{test_mae_kmh:number;persistence_mae_kmh:number;samples:number}}>;
  conditions?:CameraConditions;timeline:{second:number;predictions:CameraPrediction[]}[]};
export type CameraAnalysisData={state:string;progress:number;message:string;is_demo:boolean;analysis_id?:string;samples?:DetectionFrame[];frames?:DetectionFrame[];fps?:number;roi?:number[];capacity?:number;duration_seconds?:number;high_threshold?:number;
  road_geometry?:RoadGeometry|null;capacity_version?:number;measurements?:VideoMeasurements;
  average_count?:number;peak_count?:number;frame_url?:string;method?:string;detection_version?:number;
  counting_method?:string;total_unique_count?:number;
  source?:{title:string;author:string;page_url:string;license:string;license_url:string;published_date:string;location_note:string;scenario_hour?:string;scenario_note?:string;reference_url?:string};
  forecast?:CameraForecast|null};
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
        const compactUrl=url!.replace(/^\/api(?=\/)/,'')+(url!.includes('?')?'&':'?')+'include_forecast=false';
        const data=await api<CameraAnalysisData>(compactUrl,{signal:controller.signal});
        if(controller.signal.aborted)return;
        setValue({url,data,error:''});
        if(['queued','processing'].includes(data.state))timer=setTimeout(load,2500);
      }catch(error){if(!controller.signal.aborted)setValue({url,data:emptyAnalysis,error:(error as Error).message});}
    }
    void load();return()=>{controller.abort();clearTimeout(timer);};
  },[url,version]);
  return {data:value.url===url?value.data:emptyAnalysis,error:value.url===url?value.error:'',reload};
}
