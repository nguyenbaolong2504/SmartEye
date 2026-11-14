const publicAuthPaths = new Set(['/auth/login', '/auth/register', '/auth/me', '/auth/forgot-password', '/auth/verify-reset-otp', '/auth/reset-password']);

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const response = await fetch(`/api${path}`, {...options, credentials:'same-origin', headers: {...(!isForm && options.body ? {'Content-Type':'application/json'} : {}), ...options.headers}});
  if (!response.ok) {
    const error = await response.json().catch(() => ({detail:'Không kết nối được máy chủ.'}));
    if (response.status === 401 && !publicAuthPaths.has(path)) window.dispatchEvent(new CustomEvent('smarteye-session-expired'));
    const detail=error.detail;
    const authFields:Record<string,string>={username:'Tên đăng nhập',email:'Email',name:'Họ và tên',phone:'Số điện thoại',password:'Mật khẩu',password_confirmation:'Xác nhận mật khẩu'};
    const message=Array.isArray(detail)?detail.map((e:{msg:string;loc:string[];type?:string})=>{
      const field=e.loc.slice(1).join('.'),label=path.startsWith('/auth/')?authFields[field]:undefined;
      if(label&&field==='username'&&e.type==='string_pattern_mismatch')return 'Tên đăng nhập chỉ dùng chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang. Nhập email vào ô Email.';
      const text=e.msg.replace('Value error, ','');
      return label&&text.startsWith(label)?text:`${label||field}: ${text}`;
    }).join('; '):typeof detail==='object'&&detail?detail.message:detail;
    throw new Error(message||'Đã có lỗi xảy ra.');
  }
  return response.json();
}
export const json = (data: unknown, method = 'POST'): RequestInit => ({method, body:JSON.stringify(data)});
