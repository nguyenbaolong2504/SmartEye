import {test,expect,type Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import path from 'node:path';

async function navigate(page:Page,label:string){const menu=page.getByRole('button',{name:'Mở menu',exact:true});if(await menu.isVisible())await menu.click();await page.getByRole('button',{name:label,exact:true}).click();}
test('public route search, alternatives, reverse, validation',async({page},testInfo)=>{
  await page.goto('/');await expect(page.getByRole('heading',{name:'Tìm tuyến đường tối ưu.'})).toBeVisible();
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.getByText('3 tuyến đường được so sánh')).toBeVisible();await expect(page.locator('.route-option')).toHaveCount(3);
  await expect(page.getByText(/chưa thể khẳng định không tắc/)).toBeVisible();
  await page.keyboard.press('Control+Home');
  await page.screenshot({path:testInfo.outputPath('smarteye-routes.png'),fullPage:true});
  await page.getByRole('button',{name:'Đổi chiều hành trình'}).click();await expect(page.getByLabel('Điểm xuất phát',{exact:true})).toHaveValue('caugiay');
  await page.getByLabel('Điểm đến',{exact:true}).selectOption('caugiay');await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.getByText(/Điểm đi và điểm đến phải khác nhau/)).toBeVisible();
});
test('account registration, saved journey, alert and profile',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.getByRole('button',{name:'Tạo tài khoản mới',exact:true}).click();
  await page.getByLabel('Họ và tên').fill('Người dùng E2E');await page.getByLabel('Email',{exact:true}).fill(`e2e-${Date.now()}@example.invalid`);await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-user-password');await page.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();await page.getByRole('button',{name:'Lưu hành trình',exact:true}).click();await page.getByLabel('Tên hành trình').fill('Đi học buổi sáng');await page.getByRole('dialog').getByRole('button',{name:'Lưu hành trình',exact:true}).click();
  await navigate(page,'Hành trình & dữ liệu');await expect(page.getByRole('heading',{name:'Đi học buổi sáng'})).toBeVisible();
  await navigate(page,'Cảnh báo giao thông');await page.getByRole('button',{name:'Thêm theo dõi',exact:true}).click();await expect(page.getByText('Mật độ cao',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Quản trị hệ thống'})).toHaveCount(0);
  await page.getByRole('button',{name:/Người dùng E2E/}).click();await page.getByLabel('Họ và tên').fill('Hồ sơ E2E mới');await page.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();await expect(page.getByText('Đã cập nhật hồ sơ.')).toBeVisible();
  await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await expect(page.getByRole('button',{name:'Đăng nhập',exact:true})).toBeVisible();
});
test('admin camera editing, manual observation, report and audit',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await navigate(page,'Quản trị hệ thống');await page.getByRole('button',{name:'Thêm camera',exact:true}).click();await page.getByLabel('Tên camera').fill(`Camera E2E ${Date.now()}`);await page.getByRole('button',{name:'Lưu cấu hình',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Nhận dạng video');await page.getByLabel('Ghi chú / căn cứ').fill('Quan sát kiểm thử E2E tại đường');await page.getByRole('button',{name:'Ghi nhận',exact:true}).click();await expect(page.getByText(/Đã ghi nhận quan sát thủ công/)).toBeVisible();
  await navigate(page,'Hành trình & dữ liệu');await expect(page.getByRole('heading',{name:'Báo cáo quan sát giao thông'})).toBeVisible();await expect(page.getByRole('link',{name:'Xuất CSV'})).toBeVisible();await expect(page.getByText('Thủ công',{exact:true}).first()).toBeVisible();
  await navigate(page,'Quản trị hệ thống');await page.getByRole('button',{name:'Hệ thống & nhật ký',exact:true}).click();await expect(page.getByText('manual_observation',{exact:true}).first()).toBeVisible();
});
test('responsive layout and public policy dialog',async({page})=>{
  await page.goto('/');await expect(page.getByRole('heading',{name:'Tìm tuyến đường tối ưu.'})).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);expect(overflow).toBe(false);
  await page.getByRole('button',{name:'Điều khoản & quyền riêng tư'}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Nhận dạng video');await expect(page.getByRole('heading',{name:'Nhận dạng giao thông.'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1)).toBe(false);
});

test('video upload, real inference and private history',async({page,request})=>{
  test.setTimeout(60000);
  const config=await (await request.get('/api/config')).json();
  test.skip(!config.video_available,'Download YOLO weights to run the real video workflow.');
  execFileSync(process.platform==='win32'?'.venv\\Scripts\\python.exe':'python',['scripts/make_test_video.py']);
  await page.goto('/');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await navigate(page,'Nhận dạng video');await page.getByLabel('Chọn video camera',{exact:true}).setInputFiles(path.resolve('backend/data/e2e-empty-road.avi'));
  await page.getByRole('button',{name:'Phân tích mật độ giao thông',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Mật độ thấp',exact:true})).toBeVisible({timeout:45000});
  await expect(page.getByText('Chưa khai báo thời điểm ghi hình.',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Xác nhận cập nhật đoạn đường',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'e2e-empty-road.avi',exact:true}).first()).toBeVisible();
  await page.getByRole('button',{name:'e2e-empty-road.avi',exact:true}).first().click();
  await expect(page.locator('.timeline button')).toHaveCount(2);
});
