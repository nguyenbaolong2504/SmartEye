const publicAuthPaths = new Set(['/auth/login', '/auth/register', '/auth/me', '/auth/forgot-password', '/auth/verify-reset-otp', '/auth/reset-password']);

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const response = await fetch(`/api${path}`, {...options, credentials:'same-origin', headers: {...(!isForm && options.body ? {'Content-Type':'application/json'} : {}), ...options.headers}});
  if (!response.ok) {
    const error = await response.json().catch(() => ({detail:'Không kết nối được máy chủ.'}));
    if (response.status === 401 && !publicAuthPaths.has(path)) window.dispatchEvent(new CustomEvent('smarteye-session-expired'));
    const detail=error.detail;
    const message=Array.isArray(detail)?detail.map((e:{msg:string;loc:string[]})=>`${e.loc.slice(1).join('.')}: ${e.msg.replace('Value error, ','')}`).join('; '):typeof detail==='object'&&detail?detail.message:detail;
    throw new Error(message||'Đã có lỗi xảy ra.');
  }
  return response.json();
}
export const json = (data: unknown, method = 'POST'): RequestInit => ({method, body:JSON.stringify(data)});
