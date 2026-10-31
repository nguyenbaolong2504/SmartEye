import { defineConfig, devices } from '@playwright/test';
const python=process.platform==='win32'?'".venv\\Scripts\\python.exe"':'python';
const node=`"${process.execPath}"`;
export default defineConfig({
  testDir:'./tests/e2e',fullyParallel:false,workers:1,timeout:30000,
  use:{baseURL:'http://127.0.0.1:5174',trace:'retain-on-failure',screenshot:'only-on-failure',timezoneId:'Asia/Ho_Chi_Minh'},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome'],baseURL:'http://127.0.0.1:5174'}},{name:'mobile',use:{...devices['iPhone 13'],defaultBrowserType:'chromium',baseURL:'http://127.0.0.1:5175'}}],
  webServer:[
    {command:`${python} -m uvicorn scripts.e2e_map_services:app --host 127.0.0.1 --port 8013 --no-access-log`,url:'http://127.0.0.1:8013/health',reuseExistingServer:false,timeout:30000},
    ...([{name:'desktop',api:8011,frontend:5174},{name:'mobile',api:8012,frontend:5175}].map(profile=>({
      command:`${python} -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${profile.api}`,
      url:`http://127.0.0.1:${profile.api}/api/health`,reuseExistingServer:false,
      env:{PHOTON_URL:'http://127.0.0.1:8013',OSRM_URL:'http://127.0.0.1:8013',GOOGLE_ROUTES_API_KEY:'',GOOGLE_MAPS_BROWSER_KEY:'',DEMO_HISTORY_DAYS:'365',DEMO_AUTO_PREPARE:'true',DEMO_DATA_ENABLED:'true',VIDEO_FEATURE_ENABLED:'false',OVERPASS_URL:'http://127.0.0.1:8013/interpreter',OSM_TILE_URL:'http://127.0.0.1:8013/tiles/{z}/{x}/{y}.svg',MONGODB_DB:`smarteye_e2e_${profile.name}`,SEED_DEMO:'true',ADMIN_EMAIL:'e2e-admin@example.invalid',ADMIN_PASSWORD:'test-only-password-123',APP_BASE_URL:`http://127.0.0.1:${profile.frontend}`},timeout:60000
    }))),
    {command:`${node} scripts/start_e2e_frontend.mjs`,url:'http://127.0.0.1:5174',reuseExistingServer:false,timeout:120000}
  ]
});
