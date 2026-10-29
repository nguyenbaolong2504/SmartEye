import {test,expect,type Page} from '@playwright/test';
async function navigate(page:Page,label:string){const menu=page.getByRole('button',{name:'Mở menu',exact:true});if(await menu.isVisible())await menu.click();await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:label,exact:true}).click();}
async function choose(page:Page,label:string,text:string){await page.getByRole('combobox',{name:label,exact:true}).fill(text);await page.getByRole('listbox',{name:`Kết quả ${label.toLowerCase()}`}).getByRole('button').first().click();}
test('registration, save route, follow road, edit profile and logout',async({page})=>{
  await page.goto('/#routes');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.getByRole('button',{name:'Tạo tài khoản mới',exact:true}).click();
  await page.getByLabel('Họ và tên').fill('Người dùng E2E');await page.getByLabel('Email',{exact:true}).fill(`e2e-${Date.now()}@example.invalid`);await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-user-password');await page.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await choose(page,'Điểm xuất phát','12 Đường kiểm thử');await choose(page,'Điểm đến','84 Đường kiểm thử');await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await page.getByRole('button',{name:'Lưu hành trình',exact:true}).click();await page.getByLabel('Tên hành trình').fill('Đi học buổi sáng');await page.getByRole('dialog').getByRole('button',{name:'Lưu hành trình',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Hành trình & dữ liệu');await expect(page.getByRole('heading',{name:'Đi học buổi sáng'})).toBeVisible();
  await navigate(page,'Cảnh báo giao thông');await page.getByRole('button',{name:'Thêm theo dõi',exact:true}).click();await expect(page.getByText('Mật độ cao',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Quản trị hệ thống'})).toHaveCount(0);
  await page.getByRole('button',{name:/Hồ sơ Người dùng E2E/}).click();await page.getByLabel('Họ và tên').fill('Hồ sơ E2E mới');await page.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();await expect(page.getByText('Đã cập nhật hồ sơ.')).toBeVisible();await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await expect(page.getByRole('button',{name:'Đăng nhập',exact:true})).toBeVisible();
});
test('admin road management, reports and audit remain available',async({page,request})=>{
  await page.goto('/');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Quản trị hệ thống');await page.getByRole('button',{name:'Đoạn đường',exact:true}).click();await expect(page.getByRole('button',{name:'Thêm đoạn đường',exact:true})).toBeVisible();
  const response=await page.request.post('/api/observations',{data:{segment_id:1,score:.7,count:12,note:'Quan sát E2E trong database thử riêng',observed_at:new Date().toISOString()}});expect(response.status()).toBe(201);
  await navigate(page,'Hành trình & dữ liệu');await expect(page.getByRole('heading',{name:'Báo cáo quan sát giao thông'})).toBeVisible();await expect(page.getByRole('link',{name:'Xuất CSV'})).toBeVisible();await expect(page.getByText('Thủ công',{exact:true}).first()).toBeVisible();
  await navigate(page,'Quản trị hệ thống');await page.getByRole('button',{name:'Hệ thống & nhật ký',exact:true}).click();await expect(page.getByText('manual_observation',{exact:true}).first()).toBeVisible();
});
test('policy dialog and retired URL recover to overview without overflow',async({page})=>{
  await page.goto('/#video');await expect(page.getByRole('heading',{name:/Hiểu đường đi/})).toBeVisible();await page.getByRole('button',{name:'Điều khoản & quyền riêng tư'}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
});
