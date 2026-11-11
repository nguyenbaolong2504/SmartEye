import {expect,type APIRequestContext} from '@playwright/test';

export async function createManager(request:APIRequestContext,scope:number[]|null=null) {
  const username=`manager-${Date.now()}-${Math.random().toString(36).slice(2,7)}`;
  const account={name:'Quản lý kiểm thử',email:`${username}@example.invalid`,username,
    password:'test-manager-password-2026',password_confirmation:'test-manager-password-2026',
    role:'analyst',managed_segment_ids:scope};
  expect((await request.post('/api/auth/login',{data:{email:'e2e-admin@example.invalid',password:'test-only-password-123'}})).status()).toBe(200);
  expect((await request.post('/api/admin/accounts',{data:account})).status()).toBe(201);
  expect((await request.post('/api/auth/logout')).status()).toBe(200);
  return account;
}
