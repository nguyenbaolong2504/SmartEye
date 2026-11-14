import {test,expect,type Page} from '@playwright/test';

const analysisId='10000000-0000-4000-8000-000000000001';
const frame=(index:number)=>{
  const count=index>=6?18:index===1?3:2;
  return {second:index/2,frame_index:index,width:640,height:360,count,score:count/20,occupancy:.2,
    equivalent_count:Math.min(count,3)+Math.max(count-3,0)*.25,load_ratio:.9,motion_known:false,
    cumulative_count:999,density:count>10?'HIGH':'LOW',
    boxes:Array.from({length:count},(_,i)=>({label:i<3?'car':'motorcycle',confidence:.88,
      box:[20+i%6*95+index,70+Math.floor(i/6)*75,80+i%6*95+index,120+Math.floor(i/6)*75]})),
    vehicle_counts:{car:Math.min(count,3),motorcycle:Math.max(count-3,0),bus:0,truck:0}};
};
const geometry={lanes:1,road_width_m:3.5,observed_length_m:45,usable_fraction:1,calibration:'estimated',
  usable_area_m2:157.5,capacity_pcu:7.5,car_space_m2:21,high_density_pcu:4.5,
  equivalents:{car:1,motorcycle:.25,bus:3,truck:2.5},calibration_note:'Kích thước minh họa.'};
const camera={id:'recording-1',name:'Camera video kiểm thử',segment_id:1,segment_name:'Tràng Thi – Điện Biên Phủ',
  area:'Hà Nội',location_name:'Giao lộ kiểm thử',position:[21.03,105.84],position_exact:true,is_demo:true,
  direction:'forward',state:'archive',active:true,segment_active:true,source_name:'Video kiểm thử',
  source_host:null,source_url:null,captured_at:null,checked_at:null,refresh_seconds:0,image_url:null,
  video_url:'http://127.0.0.1:8013/camera-demo.mp4',analysis_url:'/api/traffic/cameras/recordings/1/analysis?v=test',media_kind:'recording'};
async function setup(page:Page){
  await page.route('**/api/traffic/cameras',route=>route.fulfill({json:{cameras:[camera,{...camera,id:'recording-2',name:'Camera thứ hai',analysis_url:'/api/traffic/cameras/recordings/2/analysis?v=test',location_name:'Vị trí thứ hai'}],generated_at:new Date().toISOString()}}));
  await page.route(url=>/\/recordings\/[12]\/analysis$/.test(url.pathname),route=>{
    expect(new URL(route.request().url()).searchParams.get('include_forecast')).toBe('false');
    return route.fulfill({json:{state:'completed',analysis_id:analysisId,progress:100,is_demo:true,method:'YOLO11',message:'Kết quả nhận diện',
      frames:Array.from({length:12},(_,i)=>frame(i)),fps:2,roi:[0,0,1,1],capacity:20,road_geometry:geometry,
      samples:[frame(0),frame(6)],duration_seconds:6,average_count:10,peak_count:18,high_threshold:.6,
      forecast:{is_demo:true,timeline:[],message:'Dự báo minh họa'},source:{title:'Video giao thông thử nghiệm',author:'Test fixture',page_url:'https://www.pexels.com/',
        license:'Pexels License',license_url:'https://www.pexels.com/license/',published_date:'2025-05-01',location_note:'Chưa xác minh tuyến đường thực tế.'}}});
  });
}
function forecast(horizon:number,p:{FREE:number;SLOW:number;JAM:number}){
  return {is_demo:true,scope:'video',analysis_id:analysisId,reference_at:'2026-11-12T17:00:00+07:00',message:'Dự báo chạy thử',
    basis:frame(6),road_geometry:geometry,summary:{start_second:0,end_second:6,frames:12,observed_seconds:6,median_count:10,median_score:.5,median_load_ratio:.9,motion_known:false,representative_second:3},
    conditions:{weather:{known:true,rain_mm:7,visibility_km:2,wind_kmh:10,source:'Open-Meteo'},
      road:{checked:true,accident:true,source:'published_warnings',message:'Cảnh báo đã công bố.'},location_note:'Điều kiện theo tuyến chạy thử.'},
    timeline:[{second:5.5,predictions:[{horizon_minutes:horizon,label:'HIGH',congestion_probabilities:p,
      history:{lookback_days:100,matching_days:14,jam_days:12,hour:'17:00',is_demo:true}}]}]};
}

test('explanation separates measured flow, density, speed loss and forecast probability',async({page})=>{
  await setup(page);
  await page.route('**/recordings/1/forecast',route=>{
    const base=forecast(route.request().postDataJSON().horizon_minutes,{FREE:.02,SLOW:.08,JAM:.9});
    return route.fulfill({json:{...base,
      measurements:{count_line:[[0,.5],[1,.5]],crossings:150,count_line_verified:true,speed_calibration_available:true},
      summary:{...base.summary,traffic_metrics:{flow_veh_per_hour:1800,density_veh_per_km:160,density_veh_per_km_per_lane:80,
        avg_speed_kmh:20,free_flow_speed_kmh:40,congestion_index:.5,travel_time_index:2,quality:{speed_calibrated:true}}},
      timeline:[{second:5.5,predictions:[{...base.timeline[0].predictions[0],predicted_speed_kmh:14,predicted_congestion_index:.65,
        predicted_travel_time_index:2.857,free_flow_speed_kmh:40,numeric_prediction_source:'synthetic_speed_regression'}]}]}});
  });
  await page.goto('/#cameras');await page.getByRole('button',{name:'Phân tích',exact:true}).click();
  await expect(page.locator('.camera-result-percentage')).toHaveText('90%');
  await expect(page.getByRole('table')).toHaveCount(0);
  await page.getByRole('button',{name:'Vì sao?',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByRole('row').filter({hasText:'Lưu lượng quy đổi'})).toContainText('1.800 xe/giờ');
  await expect(dialog.getByRole('row').filter({hasText:'Mật độ trên đoạn đường'})).toContainText('160 xe/km');
  await expect(dialog.getByRole('row').filter({hasText:'Tốc độ đang quan sát'})).toContainText('20 km/h');
  await expect(dialog.getByRole('row').filter({hasText:'Mức giảm tốc'})).toContainText('50%');
  await expect(dialog).toContainText('mức giảm tốc không phải xác suất ùn tắc 90%');
  await expect(dialog).toContainText('14 km/h');await expect(dialog).toContainText('65%');
  await page.keyboard.press('Escape');await expect(page.locator('.camera-result-percentage')).toHaveText('90%');
});

test('one requested result highlights free, jam and slow equally; explanation and video remain usable',async({page},info)=>{
  await setup(page);const requests:number[]=[];
  await page.route('**/recordings/1/forecast',route=>{
    const body=route.request().postDataJSON();requests.push(body.horizon_minutes);
    expect(body).toEqual({horizon_minutes:body.horizon_minutes,whole_video:true,analysis_id:analysisId});
    const p=body.horizon_minutes===15?{FREE:.9,SLOW:.08,JAM:.02}:body.horizon_minutes===30?{FREE:.02,SLOW:.08,JAM:.9}:{FREE:.05,SLOW:.85,JAM:.1};
    return route.fulfill({json:forecast(body.horizon_minutes,p)});
  });
  await page.goto('/#cameras');
  const analyze=page.getByRole('button',{name:'Phân tích',exact:true});
  await expect(analyze).toBeEnabled();
  await expect(page.locator('.camera-result')).toHaveCount(0);
  await expect(page.locator('.camera-current-counts,.camera-cumulative,.camera-video-timeline,.camera-forecast-cards')).toHaveCount(0);
  await expect(page.locator('.street-map-panel')).toHaveCount(0);
  await analyze.click();
  const result=page.locator('.camera-result');
  await expect(result).toHaveClass(/FREE/);
  await expect(result.locator('h4')).toHaveText('Thông thoáng');
  await expect(result.locator('.camera-result-percentage')).toHaveText('90%');
  await expect(result.getByRole('progressbar',{name:'Khả năng thông thoáng'})).toHaveAttribute('value','0.9');
  await expect(result).toContainText('Khả năng cao');
  await page.locator('video').evaluate(v=>{v.currentTime=.6;});
  await expect(page.locator('canvas.camera-detection-overlay')).toHaveAttribute('data-box-count','3');
  await page.locator('video').evaluate(v=>{v.currentTime=3.1;});
  await expect(page.locator('canvas.camera-detection-overlay')).toHaveAttribute('data-box-count','18');
  await expect(result.locator('.camera-result-percentage')).toHaveText('90%');
  const painted=()=>page.locator('canvas').evaluate(c=>{const canvas=c as HTMLCanvasElement;return canvas.getContext('2d')!.getImageData(0,0,canvas.width,canvas.height).data.some((v,i)=>i%4===3&&v>0);});
  await expect.poll(painted).toBe(true);
  await page.getByRole('button',{name:'Ẩn ô nhận diện',exact:true}).click();
  await expect.poll(painted).toBe(false);
  await page.getByRole('button',{name:'Hiện ô nhận diện',exact:true}).click();
  await expect.poll(painted).toBe(true);
  await result.getByRole('button',{name:'Vì sao?',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('18 xe: 3 ô tô, 15 xe máy');
  await expect(page.getByRole('dialog')).toContainText('Số xe điển hình là 10');
  await expect(page.getByRole('dialog')).toContainText('3.5 m');
  await expect(page.getByRole('dialog')).toContainText('14 ngày cùng thứ');
  await expect(page.getByRole('dialog')).toContainText('Mưa lớn');
  await expect(page.getByRole('dialog')).toContainText('Tai nạn');
  await page.getByText('Cách tính tỷ lệ và giới hạn',{exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('Không đặt sẵn tỷ lệ 80% hay 90%');
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'30 phút',exact:true}).click();
  await expect(result).toHaveCount(0);await analyze.click();
  await expect(result).toHaveClass(/JAM/);await expect(result.locator('h4')).toHaveText('Ùn tắc');
  await expect(result.locator('.camera-result-percentage')).toHaveText('90%');
  await page.getByRole('button',{name:'1 giờ',exact:true}).click();await analyze.click();
  await expect(result).toHaveClass(/SLOW/);await expect(result.locator('.camera-result-percentage')).toHaveText('85%');
  expect(requests).toEqual([15,30,60]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:`test-results/camera-simple-${info.project.name}.png`,fullPage:true});
  await page.getByText('Thông tin camera và nguồn video',{exact:true}).click();
  await expect(page.getByText('Chưa xác minh tuyến đường thực tế.',{exact:true})).toBeVisible();
});

test('errors can retry; weak evidence and a value below 80% never trigger a high probability message',async({page})=>{
  await setup(page);let calls=0;
  await page.route('**/recordings/1/forecast',route=>{
    calls++;const horizon=route.request().postDataJSON().horizon_minutes;
    if(calls===1)return route.fulfill({status:503,json:{detail:'Chưa phân tích được. Vui lòng thử lại.'}});
    const p=calls===2?{FREE:.9,SLOW:.8,JAM:.1}:calls===3?{FREE:.37,SLOW:.1,JAM:.53}:calls===4?{FREE:.79999,SLOW:.1,JAM:.10001}:{FREE:.8,SLOW:.19999,JAM:.00001};
    return route.fulfill({json:forecast(horizon,p)});
  });
  await page.goto('/#cameras');const button=page.getByRole('button',{name:'Phân tích',exact:true});
  await button.click();await expect(page.getByText('Chưa phân tích được. Vui lòng thử lại.')).toBeVisible();
  await button.click();await expect(page.getByText('Chưa có tỷ lệ phù hợp cho video này. Vui lòng thử phân tích lại.')).toBeVisible();
  await button.click();await expect(page.locator('.camera-result')).toHaveClass(/uncertain/);
  await expect(page.locator('.camera-result')).toContainText('53%');
  await expect(page.locator('.camera-result')).toContainText('Xu hướng chưa rõ');
  await button.click();await expect(page.locator('.camera-result')).toHaveClass(/uncertain/);
  await expect(page.locator('.camera-result-percentage')).toHaveText('79.9%');
  await button.click();await expect(page.locator('.camera-result')).toHaveClass(/FREE/);
  await expect(page.locator('.camera-result-percentage')).toHaveText('80%');
  await expect(page.locator('.camera-probability-breakdown .JAM b')).toHaveText('<0.1%');
});

test('changing horizon or camera cancels old work so an obsolete result cannot overwrite the screen',async({page})=>{
  await setup(page);let started=false,finished=false;
  await page.route('**/recordings/1/forecast',async route=>{
    const h=route.request().postDataJSON().horizon_minutes;started=true;
    await new Promise(resolve=>setTimeout(resolve,500));
    await route.fulfill({json:forecast(h,{FREE:.02,SLOW:.08,JAM:.9})}).catch(()=>{});
    finished=true;
  });
  await page.route('**/recordings/2/forecast',route=>route.fulfill({json:forecast(15,{FREE:.9,SLOW:.08,JAM:.02})}));
  await page.goto('/#cameras');
  await page.getByRole('button',{name:'Phân tích',exact:true}).click();
  await expect.poll(()=>started).toBe(true);
  await page.getByRole('button',{name:'30 phút',exact:true}).click();
  await expect(page.locator('.camera-result')).toHaveCount(0);
  await page.getByRole('combobox',{name:'Vị trí camera',exact:true}).selectOption('recording-2');
  await page.getByRole('button',{name:'Phân tích',exact:true}).click();
  await expect(page.locator('.camera-result')).toHaveClass(/FREE/);
  await expect(page.getByRole('button',{name:'15 phút',exact:true})).toHaveAttribute('aria-pressed','true');
  // Let the previous delayed response finish; the new camera's result must remain.
  await expect.poll(()=>finished).toBe(true);
  await expect(page.locator('.camera-result h4')).toHaveText('Thông thoáng');
});
