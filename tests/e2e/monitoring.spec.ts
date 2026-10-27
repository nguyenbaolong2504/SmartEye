import {test,expect,type Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import path from 'node:path';

async function navigate(page:Page,label:string){
  const menu=page.getByRole('button',{name:'Mở menu',exact:true});
  if(await menu.isVisible())await menu.click();
  await page.getByRole('button',{name:label,exact:true}).click();
}

test('camera board, road filtering, day/month heatmap and responsive layout',async({page})=>{
  await page.goto('/',{waitUntil:'domcontentloaded'});
  await navigate(page,'Camera & giao thông');
  await expect(page.getByRole('heading',{name:'Camera & giao thông.'})).toBeVisible();
  await expect(page.locator('.monitor-camera').first()).toBeVisible();
  await page.getByLabel('Tìm camera hoặc đường').fill('KHONG-CO-CAMERA-NAO');
  await expect(page.getByText('Chưa tìm thấy camera phù hợp.')).toBeVisible();
  await page.getByLabel('Tìm camera hoặc đường').fill('');
  await page.getByRole('button',{name:'Thống kê từng đường',exact:true}).click();
  await page.getByRole('button',{name:'Theo tháng',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Bản đồ nhiệt ngày × giờ'})).toBeVisible();
  await expect(page.locator('.monitor-heat-cell')).toHaveCount(new Date(new Date().getFullYear(),new Date().getMonth()+1,0).getDate()*24);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.locator('.monitor-heat-cell').first().click();
  await expect(page.getByLabel('Ngày thống kê')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Mật độ theo khung giờ'})).toBeVisible();
});

test('retained video, archive, explicit camera sharing and historical chart',async({page,request},testInfo)=>{
  test.setTimeout(90000);
  const config=await(await request.get('/api/config')).json();
  test.skip(!config.video_available,'YOLO weights required for the real video workflow.');
  execFileSync(process.platform==='win32'?'.venv\\Scripts\\python.exe':'python',['scripts/make_test_video.py','--format','webm']);
  await page.goto('/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');
  await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Nhận dạng video');
  await page.getByLabel('Chọn video camera',{exact:true}).setInputFiles(path.resolve('backend/data/e2e-empty-road.webm'));
  await page.getByLabel('Giữ video để xem lại và có thể chia sẻ lên trang Camera').check();
  const recording=new Date(Date.now()-2*86400000+7*3600000).toISOString().slice(0,16);
  await page.getByLabel('Thời điểm ghi hình').fill(recording);
  await page.getByRole('button',{name:'Phân tích mật độ giao thông',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Mật độ thấp',exact:true})).toBeVisible({timeout:45000});
  await page.getByLabel('Cho phép mọi người xem ảnh và video đã giữ trên trang Camera').check();
  await page.getByRole('button',{name:'Lưu vào lịch sử',exact:true}).click();
  await expect(page.getByText('Video đã được đưa vào dữ liệu giao thông.')).toBeVisible();
  await navigate(page,'Camera & giao thông');
  const card=page.locator('.monitor-camera').filter({has:page.locator('img')}).first();
  await expect(card).toBeVisible();
  await card.locator('.monitor-picture').click();
  const player=page.getByRole('dialog').locator('video');
  await expect(player).toBeVisible();
  await expect.poll(()=>player.evaluate(video=>(video as HTMLVideoElement).readyState)).toBeGreaterThanOrEqual(2);
  await page.getByRole('dialog').getByRole('button',{name:'Xem thống kê đường'}).click();
  await page.getByLabel('Ngày thống kê').fill(recording.slice(0,10));
  await expect(page.locator('.monitor-history-heading')).toContainText(recording.slice(0,10));
  await expect(page.locator('.monitor-kpis').last()).not.toContainText('Mẫu quan sát0');
  await page.screenshot({path:testInfo.outputPath('road-history.png'),fullPage:true});
});

test('monthly recurring high-density hour requires evidence across three days',async({page},testInfo)=>{
  await page.goto('/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');
  await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const previous=new Date();previous.setDate(1);previous.setMonth(previous.getMonth()-1);
  const month=`${previous.getFullYear()}-${String(previous.getMonth()+1).padStart(2,'0')}`;
  for(const day of [5,12,19])for(const minute of [0,10,20,30]){
    const response=await page.request.post('/api/observations',{data:{segment_id:1,score:.9,count:25,
      note:'Synthetic E2E history in isolated test database',
      observed_at:`${month}-${String(day).padStart(2,'0')}T00:${String(minute).padStart(2,'0')}:00+00:00`}});
    expect(response.ok()).toBe(true);
  }
  await navigate(page,'Camera & giao thông');
  await page.getByRole('button',{name:'Thống kê từng đường',exact:true}).click();
  await page.getByRole('button',{name:'Theo tháng',exact:true}).click();
  await page.getByLabel('Tháng thống kê').fill(month);
  await expect(page.locator('.monitor-history-heading')).toContainText(month);
  await expect(page.locator('.monitor-peaks')).toContainText('07:00–08:00');
  await expect(page.locator('.monitor-peaks')).toContainText('3 ngày');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.screenshot({path:testInfo.outputPath('road-month-peaks.png'),fullPage:true});
});
