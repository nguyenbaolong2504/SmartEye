import {test,expect,type Page} from '@playwright/test';

async function addresses(page:Page){
  for(const [label,text] of [['Điểm xuất phát','12 Đường kiểm thử'],['Điểm đến','84 Đường kiểm thử']]){
    await page.getByRole('combobox',{name:label,exact:true}).fill(text);
    await page.getByRole('listbox',{name:`Kết quả ${label.toLowerCase()}`}).getByRole('button').first().click();
  }
}

test('motorcycle routes show progress, use the motorcycle source and rerank priorities',async({page},info)=>{
  await page.goto('/#routes');await addresses(page);
  await page.getByRole('button',{name:'Xe máy',exact:true}).click();
  await page.getByRole('button',{name:'Ưu tiên thời gian',exact:true}).click();
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/routes/search',async route=>{await gate;await route.continue();});
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/routes/search')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Đang tìm và so sánh các tuyến đường');
  await expect(page.getByRole('button',{name:'Đang so sánh tuyến…'})).toBeDisabled();
  await expect(page.getByText('Một hành trình tốt bắt đầu từ dữ liệu.')).toHaveCount(0);
  release();const response=await pending;expect(response.status()).toBe(200);
  const data=await response.json();expect(data.optimization.scope).toBe('valhalla_candidates');
  expect(response.request().postDataJSON().mode).toBe('TWO_WHEELER');
  await expect(page.locator('.route-option').first()).toContainText('Tuyến xe máy nhanh');
  await expect(page.getByRole('status')).toHaveCount(0);
  await page.getByRole('button',{name:'Ưu tiên khoảng cách',exact:true}).click();
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.locator('.route-option').first()).toContainText('Tuyến xe máy ngắn');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.screenshot({path:info.outputPath('motorcycle-routing.png'),fullPage:true});
});

test('route failure has a clear recovery action and retry succeeds',async({page})=>{
  await page.goto('/#routes');await addresses(page);
  await page.getByRole('button',{name:'Xe máy',exact:true}).click();
  let attempts=0;
  await page.route('**/api/routes/search',async route=>{
    if(attempts++===0)await route.fulfill({status:504,contentType:'application/json',body:JSON.stringify({detail:'Chưa nhận được tuyến xe máy. Vui lòng thử lại sau vài giây.'})});
    else await route.continue();
  });
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Chưa tìm được tuyến đường',exact:true})).toBeVisible();
  await expect(page.getByText('Chưa nhận được tuyến xe máy. Vui lòng thử lại sau vài giây.',{exact:true})).toBeVisible();
  await expect(page.locator('.route-option')).toHaveCount(0);
  await page.getByRole('button',{name:'Tìm lại tuyến đường',exact:true}).click();
  await expect(page.locator('.route-option')).toHaveCount(2);
  await expect(page.getByRole('heading',{name:'Chưa tìm được tuyến đường',exact:true})).toHaveCount(0);
  expect(attempts).toBe(2);
});
