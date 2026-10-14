import { defineConfig, devices } from '@playwright/test';
const python=process.platform==='win32'?'".venv\\Scripts\\python.exe"':'python';
export default defineConfig({
  testDir:'./tests/e2e',fullyParallel:false,workers:1,timeout:30000,
  use:{baseURL:'http://127.0.0.1:5174',trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}}],
  webServer:[
    {command:`${python} -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8011`,url:'http://127.0.0.1:8011/api/health',reuseExistingServer:false,env:{DATABASE_URL:'sqlite:///./backend/data/e2e.db',SEED_DEMO:'true',ADMIN_EMAIL:'e2e-admin@example.invalid',ADMIN_PASSWORD:'test-only-password-123',APP_BASE_URL:'http://127.0.0.1:5174'},timeout:60000},
    {command:'npm run dev -- --port 5174 --strictPort',url:'http://127.0.0.1:5174',reuseExistingServer:false,env:{API_TARGET:'http://127.0.0.1:8011'},timeout:60000}
  ]
});
