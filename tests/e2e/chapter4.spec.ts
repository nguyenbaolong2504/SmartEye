import {test, expect, type Page} from '@playwright/test';

async function navigate(page:Page, label:string) {
  const menu=page.getByRole('button',{name:'Mở menu',exact:true});
  if(await menu.isVisible())await menu.click();
  await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:label,exact:true}).click();
}
async function signIn(page:Page, identifier:string, password:string) {
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).first().click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Email hoặc tên đăng nhập',{exact:true}).fill(identifier);
  await dialog.getByLabel('Mật khẩu',{exact:true}).fill(password);
  await dialog.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(dialog).toHaveCount(0);
}
async function signOut(page:Page) {
  await page.getByRole('button',{name:/^Hồ sơ /}).click();
  await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();
  await expect(page.getByRole('button',{name:'Đăng nhập',exact:true})).toBeVisible();
}

test('chapter IV report verification and warning publication in the UI',async({page,request})=>{
  test.setTimeout(65000);
  const key=Date.now();
  const viewer={name:'Người gửi phản ánh',email:`report-${key}@example.invalid`,username:`report-${key}`,password:'test-report-password-2026',password_confirmation:'test-report-password-2026'};
  const manager={name:'Quản lý phản ánh',email:`manager-${key}@example.invalid`,username:`manager-${key}`,password:'test-manager-password-2026',password_confirmation:'test-manager-password-2026',role:'analyst',managed_segment_ids:[1]};
  expect((await request.post('/api/auth/register',{data:viewer})).status()).toBe(201);
  expect((await request.post('/api/auth/login',{data:{email:'e2e-admin@example.invalid',password:'test-only-password-123'}})).status()).toBe(200);
  expect((await request.post('/api/admin/accounts',{data:manager})).status()).toBe(201);
  expect((await request.post('/api/auth/logout')).status()).toBe(200);
  page.on('dialog',dialog=>dialog.accept());

  await page.goto('/#incidents');
  await expect(page.getByRole('heading',{name:'Phản ánh giao thông.'})).toBeVisible();
  await signIn(page,viewer.username,viewer.password);
  await expect(page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:'Giám sát & xử lý'})).toHaveCount(0);
  await page.getByRole('button',{name:/^Hồ sơ /}).click();
  await page.getByLabel('Nhận thông báo khi có cảnh báo được phát hành').check();
  await page.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();
  await expect(page.getByText('Đã cập nhật hồ sơ.')).toBeVisible();
  await navigate(page,'Phản ánh giao thông');
  await page.getByRole('button',{name:'Gửi phản ánh',exact:true}).click();
  const content=`Có vật cản tại đoạn đường kiểm thử ${key}.`;
  await page.getByRole('dialog').getByLabel('Nội dung phản ánh').fill(content);
  await page.getByRole('dialog').getByRole('button',{name:'Gửi phản ánh',exact:true}).click();
  const viewerDetail=page.getByRole('dialog');
  await expect(viewerDetail.getByText('Chờ tiếp nhận',{exact:true})).toBeVisible();
  const title=await viewerDetail.getByRole('heading',{name:/Phản ánh PA-/}).innerText();
  const id=Number(title.match(/PA-(\d+)/)?.[1]);
  expect(id).toBeGreaterThan(0);
  await page.keyboard.press('Escape');
  await signOut(page);

  await signIn(page,manager.username,manager.password);
  await navigate(page,'Dự báo giao thông');
  await expect(page.getByRole('heading',{name:'Dự báo giao thông.'})).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:'Quản trị hệ thống'})).toHaveCount(0);
  await navigate(page,'Giám sát & xử lý');
  await page.getByRole('button',{name:'Quản lý phản ánh',exact:true}).click();
  await page.getByRole('button',{name:new RegExp(content)}).click();
  let dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:'Tiếp nhận',exact:true}).click();
  await expect(dialog.getByText('Đang xác minh',{exact:true})).toBeVisible();
  await dialog.getByLabel('Ghi chú hoặc căn cứ xử lý').fill('Đã đối chiếu vị trí sự cố và xác nhận phản ánh hợp lệ.');
  await dialog.getByRole('button',{name:'Lưu xác minh',exact:true}).click();
  await expect(dialog.getByText('Đang xử lý',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByRole('button',{name:'Quản lý cảnh báo',exact:true}).click();
  await page.getByRole('button',{name:'Tạo cảnh báo',exact:true}).click();
  dialog=page.getByRole('dialog');
  const warning=`Chú ý vật cản trên đoạn kiểm thử ${key}. Cần giảm tốc độ.`;
  await dialog.getByLabel('Loại cảnh báo').selectOption('obstruction');
  await dialog.getByLabel('Nội dung cảnh báo').fill(warning);
  await dialog.getByLabel('Số phản ánh liên quan (nếu có)').fill(String(id));
  await dialog.getByRole('button',{name:'Lưu chờ xác minh',exact:true}).click();
  const draft=dialog.getByText('Chờ xác minh',{exact:true});
  const duplicate=dialog.getByText(/Đang có cảnh báo tương tự/);
  await expect(draft.or(duplicate)).toBeVisible();
  if(await duplicate.isVisible()){
    await dialog.getByLabel('Lý do tạo thêm nếu đã có cảnh báo tương tự').fill('Sự cố mới có phản ánh riêng cần xác minh.');
    await dialog.getByRole('button',{name:'Lưu chờ xác minh',exact:true}).click();
  }
  await expect(dialog.getByText('Chờ xác minh',{exact:true})).toBeVisible();
  expect(((await request.get('/api/warnings')).ok())).toBeTruthy();
  expect((await (await request.get('/api/warnings')).json()).some((w:{content:string})=>w.content===warning)).toBe(false);
  await dialog.getByLabel('Căn cứ hoặc lý do').fill('Phản ánh liên quan đã được xác minh đúng tuyến và chiều.');
  await dialog.getByRole('button',{name:'Lưu xác minh',exact:true}).click();
  await expect(dialog.getByText('Chờ phát hành',{exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Phát hành',exact:true}).click();
  await expect(dialog.getByText('Đã phát hành',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await signOut(page);

  await signIn(page,viewer.username,viewer.password);
  await navigate(page,'Cảnh báo giao thông');
  await expect(page.getByRole('button',{name:new RegExp(warning)})).toBeVisible();
  await expect(page.getByText(`Cảnh báo giao thông mới: ${warning}`,{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Xem cảnh báo',exact:true}).click();
  await expect(page.getByRole('dialog').getByText(warning,{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('admin checks a source before enabling it and receives a CSV',async({page})=>{
  test.setTimeout(55000);
  page.on('dialog',dialog=>dialog.accept());
  await page.goto('/');
  await signIn(page,'e2e-admin@example.invalid','test-only-password-123');
  await navigate(page,'Quản trị hệ thống');
  await page.getByRole('button',{name:'Thêm nguồn',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Tên nguồn',{exact:true}).fill(`Nguồn tệp kiểm thử ${Date.now()}`);
  await dialog.getByLabel('Nguồn có phương pháp đo vận tốc đã kiểm chứng').check();
  await dialog.getByLabel('Nguồn có tiêu chí phân loại ùn tắc đã kiểm chứng').check();
  await dialog.getByLabel('Tôi xác nhận được phép sử dụng nguồn này').check();
  await dialog.getByRole('button',{name:'Lưu cấu hình nguồn',exact:true}).click();
  await expect(dialog.getByText('Chưa kiểm tra cấu hình · Đang tắt')).toBeVisible();
  await dialog.getByRole('button',{name:'Bật nguồn',exact:true}).click();
  await expect(dialog.getByText(/Nguồn dữ liệu chưa đủ điều kiện hoạt động/)).toBeVisible();
  await dialog.getByLabel('Số phương tiện',{exact:true}).fill('count');
  await dialog.getByLabel('Vận tốc',{exact:true}).fill('speed_kmh');
  await dialog.getByLabel('Tình trạng ùn tắc',{exact:true}).fill('state');
  const at=new Date(Date.now()-60000).toISOString();
  await dialog.getByLabel('Bản ghi mẫu để kiểm tra').fill(JSON.stringify({observed_at:at,segment_id:1,direction:'forward',count:12,speed_kmh:15,state:'SLOW'}));
  await dialog.getByRole('button',{name:'Xác nhận lưu ánh xạ',exact:true}).click();
  await expect(dialog.getByText(/Đã lưu ánh xạ/)).toBeVisible();
  await dialog.getByRole('button',{name:'Kiểm tra nguồn',exact:true}).click();
  await expect(dialog.getByText('Nguồn đã qua kiểm tra.')).toBeVisible();
  await dialog.getByRole('button',{name:'Bật nguồn',exact:true}).click();
  await expect(dialog.getByLabel('Tệp quan trắc')).toBeVisible();
  await dialog.getByLabel('Tệp quan trắc').setInputFiles({name:'observations.csv',mimeType:'text/csv',buffer:Buffer.from(`observed_at,segment_id,direction,count,speed_kmh,state\n${at},1,forward,12,15,SLOW\n`)});
  await dialog.getByRole('button',{name:'Nhập dữ liệu',exact:true}).click();
  await expect(dialog.getByText(/1 hợp lệ · 0 bị loại/)).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
