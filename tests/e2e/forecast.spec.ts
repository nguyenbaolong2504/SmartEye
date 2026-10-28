import {test,expect,type Page} from '@playwright/test';

async function navigate(page:Page,label:string){
  const menu=page.getByRole('button',{name:'Mở menu',exact:true});
  if(await menu.isVisible())await menu.click();
  await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:label,exact:true}).click();
}

test('overview, forecast empty state, privacy and responsive navigation',async({page},testInfo)=>{
  await page.goto('/',{waitUntil:'domcontentloaded'});
  await expect(page.getByRole('heading',{name:/Hiểu đường đi/})).toBeVisible();
  await expect(page.getByRole('img',{name:'Sơ đồ các đoạn đường đang theo dõi'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.screenshot({path:testInfo.outputPath('overview-redesign.png'),fullPage:true});
  await navigate(page,'Dự báo giao thông');
  await expect(page.getByRole('heading',{name:'Dự báo giao thông.'})).toBeVisible();
  await expect(page.locator('.forecast-card')).toHaveCount(2);
  await expect(page.getByRole('heading',{name:'Chưa có dự báo',exact:true})).toHaveCount(2);
  await expect(page.getByRole('button',{name:'Dữ liệu & mô hình',exact:true})).toHaveCount(0);
  await expect(page.getByText('Chưa có mô hình được Admin kích hoạt.',{exact:true})).toBeVisible();
  await page.getByLabel('Nội dung dự báo').selectOption('congestion');
  await expect(page.getByText('Mô hình ùn tắc học từ nhãn thực tế',{exact:false})).toBeVisible();
  await page.reload({waitUntil:'domcontentloaded'});
  await expect(page.getByRole('heading',{name:'Dự báo giao thông.'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.screenshot({path:testInfo.outputPath('forecast-public.png'),fullPage:true});
});

test('admin dataset checks, CSV preview/commit and independent congestion labels',async({page},testInfo)=>{
  await page.goto('/#forecast',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).first().click();
  await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');
  await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button',{name:'Dữ liệu & mô hình',exact:true}).click();
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

test('forecast cards respect target and timestamps from API contract',async({page})=>{
  // Contract fixture only: never inserts synthetic forecasts into a database.
  await page.route('**/api/forecast/predict?*',async route=>{
    const target=new URL(route.request().url()).searchParams.get('target');
    await route.fulfill({json:{state:'ready',message:'Contract fixture',issue_at:new Date().toISOString(),predictions:[
      {horizon_minutes:15,predicted_at:new Date(Date.now()+900000).toISOString(),label:target==='congestion'?'JAM':'HIGH',model:'XGBoost',test_macro_f1:.6},
      {horizon_minutes:30,predicted_at:new Date(Date.now()+1800000).toISOString(),label:target==='congestion'?'SLOW':'NORMAL',model:'GRU',test_macro_f1:.5},
    ]}});
  });
  await page.goto('/#forecast',{waitUntil:'domcontentloaded'});
  await expect(page.locator('.forecast-card').first()).toContainText('Mật độ cao');
  await expect(page.locator('.forecast-card').first()).toContainText('XGBoost');
  await expect(page.locator('.forecast-card').last()).toContainText('GRU');
  await page.getByLabel('Nội dung dự báo').selectOption('congestion');
  await expect(page.locator('.forecast-card').first()).toContainText('Ùn tắc');
  await expect(page.locator('.forecast-card').last()).toContainText('Đông, di chuyển chậm');
  await expect(page.getByRole('heading',{name:'Chưa có dự báo',exact:true})).toHaveCount(0);
});
