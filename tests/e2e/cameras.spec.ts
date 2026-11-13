import {test,expect} from '@playwright/test';

test('public cameras filter by city and road, show map and image, recover connection and open matching forecast',async({page,request},info)=>{
  const suffix=Date.now().toString();
  const created:{id:number;body:Record<string,unknown>}[]=[];
  let roadId=0;
  expect((await request.post('/api/auth/login',{data:{email:'e2e-admin@example.invalid',password:'test-only-password-123'}})).status()).toBe(200);
  try{
    const roadResponse=await request.post('/api/segments',{data:{name:`Nguyễn Huệ ${suffix}`,area:'Hồ Chí Minh',
      start_node:`camera_start_${suffix}`,end_node:`camera_end_${suffix}`,distance_km:.8,
      geometry:[[10.775,106.704],[10.773,106.706]],active:true,is_demo:false,one_way:false}});
    expect(roadResponse.status()).toBe(201);
    roadId=(await roadResponse.json()).id;
    for(const [index,sid] of [1,roadId].entries()){
      const body={name:`Camera E2E ${index} ${suffix}`,kind:'camera',format:'image',segment_id:sid,
        direction:index?'forward':'reverse',url:`http://127.0.0.1:8013/camera.png?camera=${suffix}-${index}`,
        authorized:true,public_preview:true,location_name:`Giao lộ E2E ${index} ${suffix}`,
        position:index?[10.775,106.704]:[21.03,105.84],interval_seconds:10};
      const response=await request.post('/api/management/sources',{data:body});
      expect(response.status()).toBe(201);
      let source=await response.json();
      created.push({id:source.id,body});
      const checked=await request.post(`/api/management/sources/${source.id}/test`,{data:{revision:source.revision}});
      expect(checked.status()).toBe(200);
      source=await checked.json();
      expect((await request.post(`/api/management/sources/${source.id}/toggle`,{data:{revision:source.revision,active:true,confirmed:true}})).status()).toBe(200);
    }
    await page.goto('/#cameras');
    await expect(page.getByRole('heading',{name:'Camera giao thông.'})).toBeVisible();
    await page.getByRole('combobox',{name:'Tỉnh/thành phố',exact:true}).selectOption('Hồ Chí Minh');
    const road=page.getByRole('combobox',{name:'Tuyến đường',exact:true});
    await road.selectOption(String(roadId));
    const position=page.getByRole('combobox',{name:'Vị trí camera',exact:true});
    await expect(position.locator('option')).toHaveCount(1);
    await expect(position).toHaveValue(`source-${created[1].id}`);
    const cityImage=page.getByRole('img',{name:`Hình ảnh Camera E2E 1 ${suffix}`,exact:true});
    await expect(cityImage).toBeVisible();
    await expect(cityImage).toHaveJSProperty('naturalWidth',1);
    await expect(page.getByText(/Nhận ảnh từ nguồn lúc/)).toBeVisible();
    await page.getByRole('button',{name:'Tạm dừng cập nhật',exact:true}).click();
    await page.getByRole('button',{name:'Phóng to hình ảnh',exact:true}).click();
    await expect(page.locator('.camera-viewer.expanded')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.camera-viewer.expanded')).toHaveCount(0);
    await page.getByRole('combobox',{name:'Tỉnh/thành phố',exact:true}).selectOption('Hà Nội');
    await expect(road).toHaveValue('');
    await position.selectOption(`source-${created[0].id}`);
    await page.getByRole('button',{name:'Xem bản đồ camera',exact:true}).click();
    await page.getByRole('button',{name:`Xem Camera E2E 0 ${suffix}`,exact:true}).click();
    await expect(page.locator('.camera-details h2')).toHaveText(`Camera E2E 0 ${suffix}`);
    const failure=`**/api/traffic/cameras/sources/${created[0].id}/frame?*`;
    await page.route(failure,route=>route.fulfill({status:503,body:'unavailable'}));
    await page.getByRole('button',{name:'Thử tải lại',exact:true}).click();
    await expect(page.getByText('Chưa lấy được hình ảnh mới. Vui lòng thử lại sau.')).toBeVisible();
    await page.unroute(failure);
    await page.getByRole('button',{name:'Thử tải lại',exact:true}).click();
    await expect(page.getByText('Chưa lấy được hình ảnh mới. Vui lòng thử lại sau.')).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await page.screenshot({path:`test-results/camera-${info.project.name}.png`,fullPage:true});
    await page.getByText('Thông tin camera và nguồn video',{exact:true}).click();
    await page.getByRole('button',{name:'Xem dự báo tuyến đường',exact:true}).click();
    await expect(page).toHaveURL(/#forecast$/);
    await expect(page.getByLabel('Chiều di chuyển')).toHaveValue('reverse');
    await expect(page.getByLabel('Đường, tỉnh hoặc thành phố')).toHaveValue(/Tràng Thi/);
  }finally{
    for(const item of created){
      const response=await request.get('/api/management/sources');
      const current=(await response.json()).find((source:{id:number})=>source.id===item.id);
      if(current)await request.patch(`/api/management/sources/${item.id}`,{data:{...item.body,public_preview:false,revision:current.revision}});
    }
    if(roadId)await request.delete(`/api/segments/${roadId}`);
    await request.post('/api/auth/logout');
  }
});
