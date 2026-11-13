import {test,expect,type Page} from '@playwright/test';

async function home(page:Page,permissions?:string[]){
  const road=(id:number,name:string,area:string,density:'LOW'|'HIGH'|null)=>({id,name,area,active:true,is_demo:true,
    start_node:`a${id}`,end_node:`b${id}`,geometry:[[21.03,105.84],[21.04,105.85]],distance_km:1,
    observation:density?{id,segment_id:id,density,score:density==='HIGH'?.8:.1,count:10,source:'demo',note:'',observed_at:new Date().toISOString(),created_at:new Date().toISOString()}:null});
  await page.route('**/api/bootstrap?*',async route=>{
    const response=await route.fetch();const data=await response.json();
    await route.fulfill({json:{...data,user:permissions?{id:999,name:'Người xem camera',email:'viewer@example.invalid',role:'user',active:true,permissions,uses_role_permissions:false,created_at:new Date().toISOString()}:null,
      segments:[road(1,'Tuyến Hà Nội chưa có dữ liệu','Hà Nội',null),road(2,'Tuyến Hà Nội đông xe','Hà Nội','HIGH'),
        road(3,'Tuyến Hồ Chí Minh','TP. Hồ Chí Minh','LOW'),road(4,'Tuyến Đà Nẵng','Đà Nẵng','LOW')]}});
  });
  await page.route(url=>url.pathname==='/api/warnings',route=>route.fulfill({json:[]}));
  await page.goto('/#overview');
  await expect(page.getByRole('heading',{name:/Hiểu đường đi/})).toBeVisible();
}

test('home shortcuts work and selecting an area and road opens that exact road',async({page},info)=>{
  await home(page);
  await expect(page.getByRole('img',{name:'Sơ đồ các đoạn đường đang theo dõi'})).toHaveCount(0);
  await expect(page.locator('.home-road-row')).toHaveCount(2);
  await expect(page.locator('.home-road-row').first()).toContainText('Tuyến Hà Nội đông xe');
  await expect(page.getByRole('button',{name:'Xem tuyến Tuyến Hà Nội chưa có dữ liệu',exact:true})).toContainText('Chưa có dữ liệu');
  await expect(page.getByText('Chưa có cảnh báo mới',{exact:true})).toBeVisible();
  const empty=await page.locator('.home-warnings-empty').boundingBox();expect(empty!.height).toBeLessThan(160);
  await page.getByRole('combobox',{name:'Khu vực theo dõi',exact:true}).selectOption('TP. Hồ Chí Minh');
  await expect(page.locator('.home-road-row')).toHaveCount(1);
  await expect(page.locator('.home-road-row')).toContainText('Tuyến Hồ Chí Minh');
  await page.getByRole('button',{name:'Xem tuyến Tuyến Hồ Chí Minh',exact:true}).click();
  await expect(page).toHaveURL(/#monitor$/);
  await expect(page.getByText('Quan sát trên tuyến Tuyến Hồ Chí Minh theo từng chiều.',{exact:true})).toBeVisible();
  for(const [button,tab] of [['Tìm đường phù hợp','routes'],['Xem camera','cameras'],['Xem dự báo','forecast'],['Xem thống kê','monitor']]){
    await page.goto('/#overview');
    await page.getByRole('button',{name:button,exact:true}).click();
    await expect(page).toHaveURL(new RegExp(`#${tab}$`));
  }
  await page.goto('/#overview');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:info.outputPath('home-redesign.png'),fullPage:true});
});

test('verified warnings open details; expired warnings are hidden and retry works',async({page})=>{
  await home(page);
  const at=Date.now();
  const warning={id:1001,segment_id:2,direction:'forward',kind:'accident',position:[21.03,105.84],severity:'high',
    content:'Có sự cố tại giao lộ, các phương tiện di chuyển chậm.',start_at:new Date(at-60000).toISOString(),end_at:new Date(at+3600000).toISOString(),version:1,published_at:new Date(at-60000).toISOString(),upcoming:false};
  await page.route(url=>url.pathname==='/api/warnings',route=>route.fulfill({json:[warning,{...warning,id:1002,content:'Cảnh báo hết hạn cần ẩn',end_at:new Date(at-1000).toISOString()}]}));
  await page.route('**/api/warnings/1001',route=>route.fulfill({json:warning}));
  await page.reload();
  await expect(page.getByText('Cảnh báo hết hạn cần ẩn',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:new RegExp(warning.content)}).click();
  await expect(page.getByRole('dialog')).toContainText(warning.content);
  await expect(page.getByRole('dialog')).toContainText('Tự hết hiệu lực');
  await expect(page.getByRole('dialog').getByRole('button',{name:/Sửa|Xóa|Phát hành/})).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.route(url=>url.pathname==='/api/warnings',route=>route.fulfill({status:503,json:{detail:'Chưa tải được cảnh báo.'}}));
  await page.reload();
  await expect(page.getByText('Chưa tải được cảnh báo.',{exact:true})).toBeVisible();
  await page.route(url=>url.pathname==='/api/warnings',route=>route.fulfill({json:[]}));
  await page.getByRole('button',{name:'Thử lại',exact:true}).click();
  await expect(page.getByText('Chưa có cảnh báo mới',{exact:true})).toBeVisible();
});

test('home only shows shortcuts and data panels allowed for the signed-in account',async({page})=>{
  await home(page,['cameras.view']);
  await expect(page.getByRole('button',{name:'Xem camera',exact:true})).toBeVisible();
  await expect(page.locator('.home-shortcut')).toHaveCount(1);
  await expect(page.getByRole('button',{name:'Tìm đường phù hợp',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Xem dự báo',exact:true})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Tình hình các tuyến đường'})).toHaveCount(0);
  await expect(page.getByRole('complementary',{name:'Cảnh báo mới'})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
