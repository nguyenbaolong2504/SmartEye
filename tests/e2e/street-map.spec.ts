import {test,expect,type Page} from '@playwright/test';

async function address(page:Page,label:string,text:string){
  await page.getByRole('combobox',{name:label,exact:true}).fill(text);
  await page.getByRole('listbox',{name:`Kết quả ${label.toLowerCase()}`}).getByRole('button').first().click();
}
async function search(page:Page){
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/routes/search')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  const response=await pending;expect(response.status()).toBe(200);return response.json();
}

test('full address selection, OSM road routing, comparisons and stale text',async({page},testInfo)=>{
  await page.goto('/#routes',{waitUntil:'domcontentloaded'});
  await expect(page.getByLabel('Nguồn định tuyến',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.getByText('Chọn kết quả địa chỉ hoặc ghim cho cả điểm xuất phát và điểm đến.',{exact:true})).toBeVisible();
  await address(page,'Điểm xuất phát','12 Đường kiểm thử Hà Nội');
  await address(page,'Điểm đến','84 Đường kiểm thử Hà Nội');
  const data=await search(page);
  expect(data.provider).toBe('auto');expect(data.optimization.scope).toBe('osrm_candidates');expect(data.optimization.algorithm).toBe(null);
  expect(data.routes[0].geometry.length).toBeGreaterThan(2);
  await expect(page.locator('.route-optimization')).toHaveCount(0);
  await expect(page.locator('.street-pin')).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:testInfo.outputPath('street-map-fixture.png'),fullPage:true});
  await page.getByRole('button',{name:'Đổi chiều hành trình',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Điểm xuất phát',exact:true})).toHaveValue(/84/);
  await page.getByRole('combobox',{name:'Điểm xuất phát',exact:true}).fill('Địa chỉ chưa chọn');
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.getByText('Chọn kết quả địa chỉ hoặc ghim cho cả điểm xuất phát và điểm đến.',{exact:true})).toBeVisible();
  await expect(page.locator('.route-option')).toHaveCount(0);
});

test('map zoom, expanding, picking a pin and address failure recovery',async({page})=>{
  await page.goto('/#routes',{waitUntil:'domcontentloaded'});
  const map=page.getByRole('region',{name:'Bản đồ đường phố OpenStreetMap'});
  await expect(map).toBeVisible();
  await page.getByRole('button',{name:'Phóng to',exact:true}).click();
  await page.getByRole('button',{name:'Thu nhỏ',exact:true}).click();
  await page.getByRole('button',{name:'Mở rộng bản đồ',exact:true}).click();
  await expect(page.locator('.map-expanded')).toBeVisible();
  await page.keyboard.press('Escape');await expect(page.locator('.map-expanded')).toHaveCount(0);
  await page.locator('.address-field').first().getByRole('button',{name:'Chọn trên bản đồ',exact:true}).click();
  await expect(page.getByText('Chạm bản đồ để chọn điểm xuất phát.',{exact:true})).toBeVisible();
  await map.click({position:{x:130,y:150}});
  await expect(page.getByRole('combobox',{name:'Điểm xuất phát',exact:true})).toHaveValue(/Điểm đi trên bản đồ/);
  await expect(page.locator('.street-pin')).toHaveCount(1);
  await page.getByRole('combobox',{name:'Điểm đến',exact:true}).fill('không tìm thấy');
  await expect(page.getByText(/Chưa tìm thấy địa chỉ/)).toBeVisible();
  await address(page,'Điểm đến','84 Đường kiểm thử Hà Nội');
  await expect(page.locator('.street-pin')).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
});

test('saved OSM journey retains addresses, coordinates and provider',async({page})=>{
  await page.goto('/#routes',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');
  await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await address(page,'Điểm xuất phát','12 Đường kiểm thử Hà Nội');await address(page,'Điểm đến','84 Đường kiểm thử Hà Nội');
  await search(page);await page.getByRole('button',{name:'Lưu hành trình',exact:true}).click();
  const name='Hành trình OSM '+Date.now();await page.getByLabel('Tên hành trình',{exact:true}).fill(name);
  await page.getByRole('dialog').getByRole('button',{name:'Lưu hành trình',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  const menu=page.getByRole('button',{name:'Mở menu',exact:true});if(await menu.isVisible())await menu.click();
  await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:'Hành trình & dữ liệu',exact:true}).click();
  const card=page.locator('.favorite-card').filter({has:page.getByRole('heading',{name,exact:true})});
  await expect(card.getByText('Ô tô · OpenStreetMap',{exact:true})).toBeVisible();
  await card.getByRole('button',{name:'Tìm lại tuyến',exact:true}).click();
  await expect(page.getByLabel('Nguồn định tuyến',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('combobox',{name:'Điểm xuất phát',exact:true})).toHaveValue(/12/);
  await expect(page.getByRole('combobox',{name:'Điểm đến',exact:true})).toHaveValue(/84/);
  const result=await search(page);expect(result.provider).toBe('auto');
});
