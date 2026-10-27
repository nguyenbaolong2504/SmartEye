import { defineConfig, devices } from '@playwright/test';
const python=process.platform==='win32'?'".venv\\Scripts\\python.exe"':'python';
const externalApi=process.env.SMARTEYE_E2E_API_URL;
const node=`"${process.execPath}"`;
export default defineConfig({
  testDir:'./tests/e2e',fullyParallel:false,workers:1,timeout:30000,
  use:{baseURL:'http://127.0.0.1:5174',trace:'retain-on-failure',screenshot:'only-on-failure',timezoneId:'Asia/Ho_Chi_Minh'},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}}],
  webServer:[
    ...(!externalApi?[{command:`${python} -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8011`,url:'http://127.0.0.1:8011/api/health',reuseExistingServer:false,env:{MONGODB_DB:'smarteye_e2e',SEED_DEMO:'true',ADMIN_EMAIL:'e2e-admin@example.invalid',ADMIN_PASSWORD:'test-only-password-123',APP_BASE_URL:'http://127.0.0.1:5174'},timeout:60000}]:[]),
    {command:`${node} node_modules/vite/bin/vite.js build && ${node} node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5174 --strictPort`,url:'http://127.0.0.1:5174',reuseExistingServer:false,env:{API_TARGET:externalApi||'http://127.0.0.1:8011'},timeout:120000}
  ]
});
