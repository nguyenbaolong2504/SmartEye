import {test,expect,type Page} from '@playwright/test';

async function open(page:Page,configured=false){
  if(configured){
    const response=await page.request.get('/api/bootstrap?data_mode=demo');const value=await response.json();
    await page.route('**/api/bootstrap?*',route=>route.fulfill({json:{...value,config:{...value.config,password_reset_available:true,password_reset_channels:{email:true,sms:true}}}}));
  }
  await page.goto('/#overview');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Chào mừng trở lại'})).toBeVisible();
  return page.getByRole('dialog');
}

test('glass sign-in and registration create an account and sign in with the existing API',async({page},info)=>{
  const dialog=await open(page);const key=Date.now();
  await page.screenshot({path:info.outputPath('login-glass.png'),fullPage:true});
  await dialog.getByLabel('Mật khẩu',{exact:true}).fill('test-signup-password-2026');
  await dialog.getByRole('button',{name:'Hiện mật khẩu',exact:true}).click();
  await expect(dialog.getByLabel('Mật khẩu',{exact:true})).toHaveAttribute('type','text');
  await dialog.getByRole('button',{name:'Tạo tài khoản mới',exact:true}).click();
  await dialog.getByLabel('Họ và tên',{exact:true}).fill('Người kiểm thử giao diện');
  await dialog.getByLabel('Tên đăng nhập',{exact:true}).fill(`auth-${key}`);
  await dialog.getByLabel('Email',{exact:true}).fill(`auth-${key}@example.invalid`);
  await dialog.getByLabel('Số điện thoại (không bắt buộc)',{exact:true}).fill(`09${String(key).slice(-8)}`);
  await dialog.getByLabel('Mật khẩu',{exact:true}).fill('test-signup-password-2026');
  await dialog.getByLabel('Xác nhận mật khẩu',{exact:true}).fill('different-password-2026');
  await dialog.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();
  await expect(dialog).toContainText('Mật khẩu và xác nhận không khớp.');
  await dialog.getByLabel('Xác nhận mật khẩu',{exact:true}).fill('test-signup-password-2026');
  expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  await page.screenshot({path:info.outputPath('registration-glass.png'),fullPage:true});
  await dialog.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();
  await expect(dialog).toContainText('Tạo tài khoản thành công.');
  await dialog.getByLabel('Mật khẩu',{exact:true}).fill('test-signup-password-2026');
  await dialog.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Hồ sơ Người kiểm thử giao diện',exact:true})).toBeVisible();
});

for(const delivery of ['email','sms'] as const){
  test(`password recovery via ${delivery} requires OTP, handles expiry and resend, then sets a new password`,async({page},info)=>{
    await page.clock.install();const dialog=await open(page,true);
    const identifier=delivery==='email'?'recovery@example.invalid':'0911111111';
    let sends=0,checks=0,resets=0;
    await page.route('**/api/auth/forgot-password',route=>{
      expect(route.request().postDataJSON()).toEqual({identifier,delivery});sends++;
      return route.fulfill({json:{challenge:String(sends).repeat(43),expires_in:600,resend_after:60,delivery,message:'Nếu thông tin hợp lệ, mã sẽ được gửi.'}});
    });
    await page.route('**/api/auth/verify-reset-otp',route=>{
      checks++;const body=route.request().postDataJSON();expect(body.challenge).toBe(String(sends).repeat(43));
      if(body.code!=='123456')return route.fulfill({status:400,json:{detail:'Mã xác nhận không đúng hoặc đã hết hạn.'}});
      return route.fulfill({json:{token:'t'.repeat(43),expires_in:300}});
    });
    await page.route('**/api/auth/reset-password',route=>{
      resets++;expect(route.request().postDataJSON()).toEqual({token:'t'.repeat(43),password:'new-password-after-otp',password_confirmation:'new-password-after-otp'});
      return route.fulfill({json:{message:'Đã đặt lại mật khẩu. Vui lòng đăng nhập.'}});
    });
    await dialog.getByRole('button',{name:'Quên mật khẩu?',exact:true}).click();
    if(delivery==='sms')await dialog.getByRole('button',{name:'Qua SMS',exact:true}).click();
    await dialog.getByLabel(delivery==='email'?'Email đã đăng ký':'Số điện thoại đã đăng ký',{exact:true}).fill(identifier);
    await dialog.getByRole('button',{name:'Gửi mã OTP',exact:true}).click();
    await expect(dialog.getByLabel('Mã OTP',{exact:true})).toBeVisible();
    await expect(dialog.getByRole('button',{name:/Gửi lại sau/})).toBeDisabled();
    expect(resets).toBe(0);
    await dialog.getByLabel('Mã OTP',{exact:true}).fill('000000');
    await dialog.getByRole('button',{name:'Xác nhận mã',exact:true}).click();
    await expect(dialog).toContainText('Mã xác nhận không đúng hoặc đã hết hạn.');
    await page.clock.fastForward(601000);
    await expect(dialog.getByRole('button',{name:'Xác nhận mã',exact:true})).toBeDisabled();
    await expect(dialog).toContainText('Mã đã hết hạn.');
    await dialog.getByRole('button',{name:'Gửi lại mã',exact:true}).click();
    await expect(dialog.getByLabel('Mã OTP',{exact:true})).toHaveValue('');expect(sends).toBe(2);
    await page.screenshot({path:info.outputPath(`otp-${delivery}.png`),fullPage:true});
    await dialog.getByLabel('Mã OTP',{exact:true}).fill('123456');
    await dialog.getByRole('button',{name:'Xác nhận mã',exact:true}).click();
    await dialog.getByLabel('Mật khẩu mới',{exact:true}).fill('new-password-after-otp');
    await dialog.getByLabel('Xác nhận mật khẩu mới',{exact:true}).fill('new-password-after-otp');
    await dialog.getByRole('button',{name:'Đặt lại mật khẩu',exact:true}).click();
    await expect(dialog).toContainText('Đã đặt lại mật khẩu. Vui lòng đăng nhập.');
    expect(checks).toBe(2);expect(resets).toBe(1);
    expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  });
}

test('forgot password remains clickable when providers are missing and reports the missing service',async({page})=>{
  const dialog=await open(page);
  await expect(dialog.getByRole('button',{name:'Quên mật khẩu?',exact:true})).toBeEnabled();
  await dialog.getByRole('button',{name:'Quên mật khẩu?',exact:true}).click();
  await expect(dialog).toContainText('Cách nhận mã này hiện chưa sẵn sàng.');
  await dialog.getByLabel('Email đã đăng ký',{exact:true}).fill('absent@example.invalid');
  await dialog.getByRole('button',{name:'Gửi mã OTP',exact:true}).click();
  await expect(dialog).toContainText('Gửi mã qua email tạm chưa sẵn sàng.');
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('');
});
