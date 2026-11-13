import {test,expect} from '@playwright/test';

test('video playback, density timeline and three forecast horizons stay synchronized',async({page},info)=>{
  const frame=(index:number)=>{
    const count=index>=6?18:index===1?3:2;
    const boxes=Array.from({length:count},(_,i)=>({label:i<3?'car':'motorcycle',confidence:.88,
      box:[20+i%6*95+index,70+Math.floor(i/6)*75,80+i%6*95+index,120+Math.floor(i/6)*75]}));
    return {second:index/2,frame_index:index,width:640,height:360,count,score:count/20,occupancy:.2,
      cumulative_count:index<1?2:index<6?3:21,
      cumulative_vehicle_counts:{car:index<1?2:index<6?3:6,motorcycle:index>=6?15:0,bus:0,truck:0},
      density:count>10?'HIGH':'LOW',boxes,vehicle_counts:{car:Math.min(count,3),motorcycle:Math.max(count-3,0),bus:0,truck:0}};
  };
  const camera={id:'recording-1',name:'Camera video kiểm thử',segment_id:1,segment_name:'Tràng Thi – Điện Biên Phủ',
    area:'Hà Nội',location_name:'Giao lộ kiểm thử',position:[21.03,105.84],position_exact:true,is_demo:true,
    direction:'forward',state:'archive',active:true,segment_active:true,source_name:'Video kiểm thử',
    source_host:null,source_url:null,captured_at:null,checked_at:null,refresh_seconds:0,image_url:null,
    video_url:'http://127.0.0.1:8013/camera-demo.mp4',analysis_url:'/api/traffic/cameras/recordings/1/analysis?v=test',media_kind:'recording'};
  await page.route('**/api/traffic/cameras',route=>route.fulfill({json:{cameras:[camera],generated_at:new Date().toISOString()}}));
  await page.route(url=>url.pathname==='/api/traffic/cameras/recordings/1/analysis',route=>route.fulfill({json:{
    state:'completed',progress:100,is_demo:true,method:'YOLO11',message:'Phân tích chạy thử',
    frames:Array.from({length:12},(_,i)=>frame(i)),fps:2,roi:[0,0,1,1],capacity:20,
    samples:[{second:0,count:2,score:.1,occupancy:.1,density:'LOW',vehicle_counts:{car:2,motorcycle:0,bus:0,truck:0}},
      {second:3,count:18,score:.95,occupancy:.6,density:'HIGH',vehicle_counts:{car:3,motorcycle:15,bus:0,truck:0}}],
    duration_seconds:6,average_count:10,peak_count:18,high_threshold:.6,
    forecast:{is_demo:true,message:'Kết hợp mật độ trong video với lịch sử minh họa của tuyến đường.',
      timeline:[{second:0,predictions:[15,30,60].map(h=>({horizon_minutes:h,label:'LOW',congestion_label:'FREE',
          congestion_probability:.1,congestion_probabilities:{FREE:.7,SLOW:.2,JAM:.1}}))},
        {second:3,predictions:[15,30,60].map(h=>({horizon_minutes:h,label:'HIGH',congestion_label:'JAM',
          congestion_probability:.9,congestion_probabilities:{FREE:.02,SLOW:.08,JAM:.9},
          history:{lookback_days:100,matching_days:14,jam_days:12,hour:'17:00',is_demo:true}}))}]},
    source:{title:'Video giao thông thử nghiệm',author:'Test fixture',page_url:'https://www.pexels.com/',
      license:'Pexels License',license_url:'https://www.pexels.com/license/',published_date:'2025-05-01',
      location_note:'Video minh họa. Chưa xác minh tuyến đường thực tế.'}
  }}));
  await page.goto('/#cameras');
  await expect(page.getByRole('heading',{name:'Xe đang xuất hiện trong video',exact:true})).toBeVisible();
  await expect(page.locator('.camera-current-counts article').first().locator('b')).toHaveText('2');
  await expect(page.locator('.camera-cumulative .camera-counts article b')).toHaveText(['2','2','0','0','0']);
  await expect(page.locator('canvas.camera-detection-overlay')).toHaveAttribute('data-box-count','2');
  await page.locator('video').evaluate(v=>{v.currentTime=.6;});
  await expect(page.locator('.camera-current-counts article').first().locator('b')).toHaveText('3');
  await expect(page.locator('canvas.camera-detection-overlay')).toHaveAttribute('data-box-count','3');
  await expect(page.locator('.camera-forecast-cards article')).toHaveCount(3);
  await expect(page.locator('.camera-forecast-cards article span')).toHaveText(['Sau 15 phút','Sau 30 phút','Sau 60 phút']);
  await page.getByRole('button',{name:'Xem giây 3, mật độ cao',exact:true}).click();
  await expect(page.locator('.camera-current-counts article').first().locator('b')).toHaveText('18');
  await expect(page.locator('.camera-density')).toHaveText('Rất cao');
  await expect(page.locator('.camera-forecast-cards strong')).toHaveText(['Dễ ùn tắc','Dễ ùn tắc','Dễ ùn tắc']);
  await expect(page.locator('canvas.camera-detection-overlay')).toHaveAttribute('data-box-count','18');
  await expect(page.locator('.camera-current-counts article b')).toHaveText(['18','3','15','0','0']);
  await expect(page.locator('.camera-cumulative .camera-counts article b')).toHaveText(['21','6','15','0','0']);
  const hasPaint=()=>page.locator('canvas.camera-detection-overlay').evaluate(c=>{
    const canvas=c as HTMLCanvasElement;return canvas.getContext('2d')!.getImageData(0,0,canvas.width,canvas.height).data.some((v,i)=>i%4===3&&v>0);
  });
  await expect.poll(hasPaint).toBe(true);
  await page.getByRole('button',{name:'Ẩn ô nhận diện',exact:true}).click();
  await expect.poll(hasPaint).toBe(false);
  await expect(page.locator('.camera-current-counts article').first().locator('b')).toHaveText('18');
  await page.getByRole('button',{name:'Hiện ô nhận diện',exact:true}).click();
  await expect.poll(hasPaint).toBe(true);
  await expect(page.locator('.camera-jam-probability')).toHaveText(['90%','90%','90%']);
  await page.getByRole('button',{name:'Giải thích dự báo sau 15 phút',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Vì sao có dự báo sau 15 phút?'})).toBeVisible();
  await expect(page.getByText(/14 ngày cùng thứ có dữ liệu/)).toBeVisible();
  await expect(page.getByText(/không có nghĩa hệ thống đếm đúng 90%/)).toBeVisible();
  await page.screenshot({path:`test-results/camera-explanation-${info.project.name}.png`,fullPage:true});
  await page.keyboard.press('Escape');
  await expect.poll(()=>page.locator('video').evaluate(video=>(video as HTMLVideoElement).currentTime)).toBeGreaterThanOrEqual(2.9);
  await expect(page.getByText('Video minh họa. Chưa xác minh tuyến đường thực tế.')).toBeVisible();
  await page.locator('video').evaluate(v=>{v.currentTime=.1;});
  await expect(page.locator('.camera-cumulative .camera-counts article b')).toHaveText(['2','2','0','0','0']);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:`test-results/camera-analysis-${info.project.name}.png`,fullPage:true});
});
