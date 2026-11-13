import {useEffect,useRef,type RefObject} from 'react';
import {atTime,type CameraAnalysisData,type VehicleCounts} from './cameraAnalysisData';

const names:Record<keyof VehicleCounts,string>={car:'Ô tô',motorcycle:'Xe máy',bus:'Xe buýt',truck:'Xe tải'};
const colors:Record<keyof VehicleCounts,string>={car:'#24edaa',motorcycle:'#64c8ff',bus:'#ffd265',truck:'#e3a0ff'};

export default function CameraDetectionOverlay({videoRef,data,visible,onTime}:{videoRef:RefObject<HTMLVideoElement|null>;data:CameraAnalysisData;visible:boolean;onTime:(value:number)=>void}){
  const canvasRef=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{
    const video=videoRef.current,canvas=canvasRef.current;
    if(!video||!canvas||!data.frames?.length||data.state!=='completed')return;
    let callback=0,animation=0,active=true;
    function draw(second=video!.currentTime){
      if(!active)return;
      const frame=atTime(data.frames!,second),ctx=canvas!.getContext('2d');
      if(!ctx||!frame?.width||!frame.height)return;
      const {width,height}=canvas!.getBoundingClientRect(),ratio=devicePixelRatio||1;
      if(canvas!.width!==Math.round(width*ratio)||canvas!.height!==Math.round(height*ratio)){
        canvas!.width=Math.round(width*ratio);canvas!.height=Math.round(height*ratio);
      }
      ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
      if(!video!.seeking&&video!.readyState>=2){
        onTime(frame.second);
        canvas!.dataset.frameIndex=String(frame.frame_index??0);
        canvas!.dataset.boxCount=String(frame.boxes?.length||0);
        if(!visible)return;
        const scale=Math.min(width/frame.width,height/frame.height);
        const left=(width-frame.width*scale)/2,top=(height-frame.height*scale)/2;
        ctx.lineWidth=1.5;ctx.font='600 11px system-ui, sans-serif';
        if(data.roi){
          const [a,b,c,d]=data.roi;ctx.strokeStyle='#ffffffaa';ctx.setLineDash([5,4]);
          ctx.strokeRect(left+a*frame.width*scale,top+b*frame.height*scale,(c-a)*frame.width*scale,(d-b)*frame.height*scale);ctx.setLineDash([]);
        }
        for(const box of frame.boxes||[]){
          const [a,b,c,d]=box.box,color=colors[box.label]||'#24edaa',label=`${names[box.label]||'Xe'}${box.track_id!=null?` #${box.track_id}`:''}`;
          const x=left+a*scale,y=top+b*scale,w=(c-a)*scale,h=(d-b)*scale;
          ctx.strokeStyle=color;ctx.strokeRect(x,y,w,h);
          const textWidth=ctx.measureText(label).width+7,textX=Math.min(Math.max(left,x),left+frame.width*scale-textWidth);
          const textY=Math.max(top,y-17);ctx.fillStyle=color;ctx.fillRect(textX,textY,textWidth,17);
          ctx.fillStyle='#063244';ctx.fillText(label,textX+3,textY+12);
        }
      }
    }
    function frameCallback(_now:number,metadata:VideoFrameCallbackMetadata){draw(metadata.mediaTime);if(active)callback=video!.requestVideoFrameCallback(frameCallback);}
    function fallback(){draw();if(active)animation=requestAnimationFrame(fallback);}
    const refresh=()=>{if(video.paused||video.seeking||!('requestVideoFrameCallback' in video))draw();};
    for(const event of ['loadeddata','seeked','seeking','pause','play','timeupdate'])video.addEventListener(event,refresh);
    const observer=new ResizeObserver(refresh);observer.observe(canvas);draw();
    if('requestVideoFrameCallback' in video)callback=video.requestVideoFrameCallback(frameCallback);else fallback();
    return()=>{active=false;observer.disconnect();if(callback)video.cancelVideoFrameCallback(callback);cancelAnimationFrame(animation);
      for(const event of ['loadeddata','seeked','seeking','pause','play','timeupdate'])video.removeEventListener(event,refresh);};
  },[videoRef,data,visible,onTime]);
  return <canvas ref={canvasRef} className="camera-detection-overlay" aria-label="Ô nhận diện ô tô, xe máy, xe buýt và xe tải"/>;
}
