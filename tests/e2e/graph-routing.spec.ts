import {test,expect,type Page} from '@playwright/test';
async function address(page:Page,label:string,text:string){await page.getByRole('combobox',{name:label,exact:true}).fill(text);await page.getByRole('listbox',{name:`Kết quả ${label.toLowerCase()}`}).getByRole('button').first().click();}
test('simple route form, automatic source and weighted time/distance ranking',async({page},info)=>{
  await page.goto('/#routes');
  await expect(page.getByRole('heading',{name:'Tìm tuyến đường tối ưu.'})).toBeVisible();
  await expect(page.getByLabel('Nguồn định tuyến',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Thuật toán tìm tuyến',{exact:true})).toHaveCount(0);
  await address(page,'Điểm xuất phát','12 Đường kiểm thử');await address(page,'Điểm đến','84 Đường kiểm thử');
  const request=page.waitForRequest(r=>r.url().endsWith('/api/routes/search')&&r.method()==='POST');
  await page.getByRole('button',{name:'Ưu tiên thời gian',exact:true}).click();await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  const sent=(await request).postDataJSON();expect(sent.algorithm).toBe('astar');expect(sent.provider).toBe('auto');
  await expect(page.locator('.route-option').first()).toContainText('Tuyến kiểm thử nhanh');
  await page.getByRole('button',{name:'Ưu tiên khoảng cách',exact:true}).click();await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  await expect(page.locator('.route-option').first()).toContainText('Tuyến kiểm thử ngắn');
  await expect(page.locator('.route-optimization')).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.screenshot({path:info.outputPath('simplified-routing.png'),fullPage:true});
});
test('configured network still defaults to A* and obeys one-way roads',async({request})=>{
  await request.post('/api/auth/login',{data:{email:'e2e-admin@example.invalid',password:'test-only-password-123'}});
  const suffix=Date.now();const start=`west_${suffix}`,end=`east_${suffix}`;
  const created=await request.post('/api/segments',{data:{name:`Đường kiểm thử ${suffix}`,start_node:start,end_node:end,distance_km:2,geometry:[[21.04,105.79],[21.04,105.81]],one_way:true}});expect(created.status()).toBe(201);
  const a={node:start,name:'Đầu đường',lat:21.04,lng:105.79},b={node:end,name:'Cuối đường',lat:21.04,lng:105.81};
  const response=await request.post('/api/routes/search',{data:{origin:a,destination:b,provider:'demo'}});
  expect(response.ok()).toBe(true);expect((await response.json()).optimization.algorithm).toBe('astar');
  const reverse=await request.post('/api/routes/search',{data:{origin:b,destination:a,provider:'demo'}});expect(reverse.status()).toBe(404);
});
