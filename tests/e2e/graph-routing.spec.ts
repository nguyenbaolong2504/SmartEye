import {test,expect,type Page} from '@playwright/test';

async function navigate(page:Page,label:string){
  const menu=page.getByRole('button',{name:'Mở menu',exact:true});if(await menu.isVisible())await menu.click();
  await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:label,exact:true}).click();
}
async function search(page:Page){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/routes/search')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Tìm tuyến tối ưu',exact:true}).click();
  const result=await response;return {status:result.status(),body:await result.json()};
}

test('Dijkstra and A* use combined priorities, comparison and visible cost breakdown',async({page},testInfo)=>{
  await page.goto('/#routes',{waitUntil:'domcontentloaded'});
  await expect(page.getByLabel('Thuật toán tìm tuyến',{exact:true})).toHaveValue('compare');
  await page.getByRole('button',{name:'Cân bằng 50/50',exact:true}).click();
  const compare=await search(page);
  expect(compare.status).toBe(200);expect(compare.body.optimization.agreement).toBe(true);
  expect(compare.body.optimization.normalized_weights).toEqual({time:.5,distance:.5,density:0});
  expect(compare.body.optimization.primary_search.dijkstra.cost).toBeCloseTo(compare.body.optimization.primary_search.astar.cost,9);
  await expect(page.getByText('Hai thuật toán cùng điểm tối ưu',{exact:true})).toBeVisible();
  await page.getByText('Cách tính và kết quả thuật toán',{exact:true}).click();
  await expect(page.locator('.route-optimization table tbody tr')).toHaveCount(2);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:testInfo.outputPath('dijkstra-astar-compare.png'),fullPage:true});
  await page.getByLabel('Thuật toán tìm tuyến',{exact:true}).selectOption('dijkstra');
  await page.getByRole('button',{name:'Ưu tiên thời gian',exact:true}).click();
  const dijkstra=await search(page);
  expect(dijkstra.body.optimization.algorithm).toBe('dijkstra');
  expect(Object.keys(dijkstra.body.optimization.primary_search)).toEqual(['dijkstra']);
  expect(dijkstra.body.optimization.normalized_weights.time).toBe(.75);
  await page.getByLabel('Thuật toán tìm tuyến',{exact:true}).selectOption('astar');
  await page.getByRole('button',{name:'Ưu tiên khoảng cách',exact:true}).click();
  const astar=await search(page);
  expect(astar.body.optimization.algorithm).toBe('astar');
  expect(astar.body.optimization.normalized_weights.distance).toBe(.75);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:testInfo.outputPath('dijkstra-astar-routing.png'),fullPage:true});
});

test('admin configures one-way road and endpoints become available without reload',async({page})=>{
  await page.goto('/#routes',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill('e2e-admin@example.invalid');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password-123');
  await page.getByRole('dialog').getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Quản trị hệ thống');
  await page.getByRole('button',{name:'Đoạn đường',exact:true}).click();
  await page.getByRole('button',{name:'Thêm đoạn đường',exact:true}).click();
  const suffix=Date.now();const west=`test_west_${suffix}`,east=`test_east_${suffix}`;
  await page.getByLabel('Tên đoạn đường',{exact:true}).fill(`Đường kiểm thử một chiều ${suffix}`);
  await page.getByLabel('Mã nút đầu',{exact:true}).fill(west);await page.getByLabel('Mã nút cuối',{exact:true}).fill(east);
  await page.getByLabel('Khoảng cách khảo sát (km)',{exact:true}).fill('2');
  await page.getByLabel('Tọa độ đường',{exact:true}).fill('[[21.04,105.79],[21.04,105.81]]');
  await page.getByLabel('Đường một chiều: chỉ đi từ nút đầu đến nút cuối',{exact:true}).check();
  await page.getByRole('button',{name:'Lưu đoạn đường',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);
  await navigate(page,'Tìm tuyến đường');
  await expect(page.getByLabel('Điểm xuất phát',{exact:true}).locator(`option[value="${west}"]`)).toHaveCount(1);
  await page.getByLabel('Điểm xuất phát',{exact:true}).selectOption(west);await page.getByLabel('Điểm đến',{exact:true}).selectOption(east);
  const forward=await search(page);expect(forward.status).toBe(200);expect(forward.body.routes).toHaveLength(1);
  await page.getByRole('button',{name:'Đổi chiều hành trình',exact:true}).click();
  const reverse=await search(page);expect(reverse.status).toBe(404);
  await expect(page.getByText('Không có tuyến đi được theo chiều đường đã cấu hình.',{exact:true})).toBeVisible();
});
