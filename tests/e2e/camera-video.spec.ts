import {test,expect} from '@playwright/test';

test('video playback, density timeline and three forecast horizons stay synchronized',async({page},info)=>{
  const camera={id:'recording-1',name:'Camera video kiểm thử',segment_id:1,segment_name:'Tràng Thi – Điện Biên Phủ',
    area:'Hà Nội',location_name:'Giao lộ kiểm thử',position:[21.03,105.84],position_exact:true,is_demo:true,
    direction:'forward',state:'archive',active:true,segment_active:true,source_name:'Video kiểm thử',
    source_host:null,source_url:null,captured_at:null,checked_at:null,refresh_seconds:0,image_url:null,
    video_url:'http://127.0.0.1:8013/camera-demo.mp4',analysis_url:'/api/traffic/cameras/recordings/1/analysis?v=test',media_kind:'recording'};
  await page.route('**/api/traffic/cameras',route=>route.fulfill({json:{cameras:[camera],generated_at:new Date().toISOString()}}));
  await page.route(url=>url.pathname==='/api/traffic/cameras/recordings/1/analysis',route=>route.fulfill({json:{
    state:'completed',progress:100,is_demo:true,method:'YOLO11',message:'Phân tích chạy thử',
    samples:[{second:0,count:2,score:.1,occupancy:.1,density:'LOW',vehicle_counts:{car:2,motorcycle:0,bus:0,truck:0}},
      {second:3,count:18,score:.95,occupancy:.6,density:'HIGH',vehicle_counts:{car:3,motorcycle:15,bus:0,truck:0}}],
    duration_seconds:6,average_count:10,peak_count:18,high_threshold:.6,
    forecast:{is_demo:true,message:'Kết hợp mật độ trong video với lịch sử minh họa của tuyến đường.',
      timeline:[{second:0,predictions:[15,30,60].map(h=>({horizon_minutes:h,label:'LOW'}))},
        {second:3,predictions:[15,30,60].map(h=>({horizon_minutes:h,label:'HIGH'}))}]},
    source:{title:'Video giao thông thử nghiệm',author:'Test fixture',page_url:'https://www.pexels.com/',
      license:'Pexels License',license_url:'https://www.pexels.com/license/',published_date:'2025-05-01',
      location_note:'Video minh họa. Chưa xác minh tuyến đường thực tế.'}
  }}));
  await page.goto('/#cameras');
  await expect(page.getByRole('heading',{name:'Mật độ trong video',exact:true})).toBeVisible();
  await expect(page.locator('.camera-counts article').first().locator('b')).toHaveText('2');
  await expect(page.locator('.camera-forecast-cards article')).toHaveCount(3);
  await expect(page.locator('.camera-forecast-cards article span')).toHaveText(['Sau 15 phút','Sau 30 phút','Sau 60 phút']);
  await page.getByRole('button',{name:'Xem giây 3, mật độ cao',exact:true}).click();
  await expect(page.locator('.camera-counts article').first().locator('b')).toHaveText('18');
  await expect(page.locator('.camera-density')).toHaveText('Rất cao');
  await expect(page.locator('.camera-forecast-cards strong')).toHaveText(['Cao','Cao','Cao']);
  await expect.poll(()=>page.locator('video').evaluate(video=>(video as HTMLVideoElement).currentTime)).toBeGreaterThanOrEqual(2.9);
  await expect(page.getByText('Video minh họa. Chưa xác minh tuyến đường thực tế.')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:`test-results/camera-analysis-${info.project.name}.png`,fullPage:true});
});
