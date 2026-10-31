import {test,expect,type Page} from '@playwright/test';
async function navigate(page:Page,label:string){const menu=page.getByRole('button',{name:'Mở menu',exact:true});if(await menu.isVisible())await menu.click();await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:label,exact:true}).click();}
test('day-ahead forecasts explain recurring congestion without technical banners',async({page,request},info)=>{
  test.setTimeout(240000);
  await expect.poll(async()=>{const r=await request.get('/api/demo/status');return (await r.json()).planning_ready;},{timeout:180000,intervals:[2000]}).toBe(true);
  await page.goto('/');await expect(page.getByRole('heading',{name:/Hiểu đường đi/})).toBeVisible();
  await expect(page.getByRole('img',{name:'Sơ đồ các đoạn đường đang theo dõi'})).toBeVisible();
  await expect(page.locator('.data-mode-bar')).toHaveCount(0);await expect(page.getByLabel('Nguồn dữ liệu',{exact:true})).toHaveCount(0);
  await expect(page.getByText('XGBoost',{exact:false})).toHaveCount(0);await expect(page.getByRole('link',{name:'Mã nguồn dự án',exact:true})).toHaveCount(0);
  await navigate(page,'Dự báo giao thông');
  await expect(page.locator('.outlook-state')).toBeVisible();await expect(page.locator('.outlook-hours button')).toHaveCount(24);
  await expect(page.getByText(/ngày cùng thứ đã qua/)).toBeVisible();await expect(page.getByText('365',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Quản lý dữ liệu',exact:true})).toHaveCount(0);
  await page.getByLabel('Giờ dự định đi').selectOption('18');await page.getByRole('button',{name:'Xem dự báo',exact:true}).click();await expect(page.locator('.outlook-summary')).toContainText('18:00–19:00');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+1)).toBe(false);
  await page.screenshot({path:info.outputPath('day-ahead-forecast.png'),fullPage:true});
  await page.getByRole('button',{name:'Xem lịch sử tuyến đường',exact:true}).click();await expect(page.getByRole('heading',{name:'So sánh các tháng trong năm',exact:true})).toBeVisible();
});
test('admin dataset checks, CSV preview/commit and independent congestion labels',async({page},testInfo)=>{
  await page.goto('/#forecast',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).first().click();
  await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');
  await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button',{name:'Quản lý dữ liệu',exact:true}).click();
  await page.getByRole('button',{name:'Kiểm tra dữ liệu',exact:true}).click();
  await expect(page.getByText('Cần dữ liệu ít nhất 7 ngày khác nhau.',{exact:true})).toHaveCount(2);
  await expect(page.getByRole('button',{name:'Huấn luyện XGBoost + GRU',exact:true})).toBeDisabled();
  await page.getByText('Nhập dữ liệu lịch sử bằng CSV',{exact:true}).click();
  const at=new Date(Date.now()-86400000).toISOString();
  await page.getByLabel('Tệp dữ liệu CSV',{exact:true}).setInputFiles({name:'observations.csv',mimeType:'text/csv',buffer:Buffer.from(`segment_id,observed_at,score,count,density\n1,${at},0.4,8,NORMAL\n`)});
  await page.getByRole('button',{name:'Kiểm tra CSV trước khi nhập',exact:true}).click();
  await expect(page.getByText('Đã kiểm tra. Chưa ghi dữ liệu.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Xác nhận nhập dữ liệu',exact:true}).click();
  await expect(page.getByText('Đã nhập mẫu lịch sử. CSV không tự tạo nhãn ùn tắc.',{exact:true}).first()).toBeVisible();
  await page.getByText('Xác nhận nhãn ùn tắc thực tế',{exact:true}).click();
  const label=new Date(Date.now()-3600000);label.setMinutes(Math.floor(label.getMinutes()/5)*5,0,0);
  const labelCSV=`segment_id,observed_at,state,note\n1,${label.toISOString()},SLOW,Reviewed label in isolated E2E database only\n`;
  await page.getByLabel('Tệp nhãn thực tế CSV',{exact:true}).setInputFiles({name:'labels.csv',mimeType:'text/csv',buffer:Buffer.from(labelCSV)});
  await page.getByRole('button',{name:'Kiểm tra CSV nhãn',exact:true}).click();
  await expect(page.getByText('Đã kiểm tra nhãn, chưa ghi dữ liệu.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Xác nhận nhập nhãn đã kiểm chứng',exact:true}).click();
  await expect(page.getByText('Đã lưu nhãn thực tế từ CSV.',{exact:false}).first()).toBeVisible();
  await page.getByLabel('Thời điểm kết thúc ô 5 phút',{exact:true}).fill(new Date(label.getTime()+7*3600000).toISOString().slice(0,16));
  await page.getByLabel('Trạng thái thực tế',{exact:true}).selectOption('SLOW');
  await page.getByLabel('Căn cứ xác nhận',{exact:true}).fill('Nhãn thử trong DB E2E riêng, không phải dữ liệu triển khai');
  await page.getByRole('button',{name:'Lưu nhãn thực tế',exact:true}).click();
  await expect(page.getByText('Đã lưu nhãn thực tế.',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:testInfo.outputPath('forecast-management.png'),fullPage:true});
});

test('future congestion, avoidance window and lower-risk departure come from API contract',async({page})=>{
  await page.route('**/api/traffic/outlook?*',async route=>{
    const d=new URL(route.request().url()).searchParams.get('date');
    const selected={hour:17,label:'JAM',text:'Dễ ùn tắc',similar_days:52,jam_days:43,jam_frequency:43/52};
    await route.fulfill({json:{state:'ready',is_demo:true,date:d,hour:17,segment_id:14,segment_name:'Hoàng Quốc Việt',selected,
      hourly:Array.from({length:24},(_,hour)=>({...selected,hour,label:hour===17?'JAM':'FREE',text:hour===17?'Dễ ùn tắc':'Thông thoáng'})),
      avoid_windows:[{start_hour:17,end_hour:18}],alternatives:[{...selected,hour:18,label:'FREE',text:'Thông thoáng'}],
      explanation:'Trong 52 ngày cùng thứ đã qua, có 43 ngày dễ ùn tắc ở khung giờ này.',advice:'Nên cân nhắc đi vào giờ khác để tránh 17:00–18:00.',history_days:365}});
  });
  await page.goto('/#forecast');await expect(page.locator('.outlook-state')).toContainText('Dễ ùn tắc');await expect(page.locator('.outlook-windows')).toContainText('17:00–18:00');await expect(page.locator('.outlook-alternatives')).toContainText('18:00');
  await expect(page.getByText('XGBoost',{exact:false})).toHaveCount(0);
});
