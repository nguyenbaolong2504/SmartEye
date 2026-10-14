export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const response = await fetch(`/api${path}`, {...options, credentials:'same-origin', headers: {...(!isForm && options.body ? {'Content-Type':'application/json'} : {}), ...options.headers}});
  if (!response.ok) {
    const error = await response.json().catch(() => ({detail:'Không kết nối được máy chủ.'}));
    throw new Error(Array.isArray(error.detail) ? error.detail.map((e: {msg: string; loc: string[]}) => `${e.loc.slice(1).join('.')}: ${e.msg.replace('Value error, ','')}`).join('; ') : error.detail || 'Đã có lỗi xảy ra.');
  }
  return response.json();
}
export const json = (data: unknown, method = 'POST'): RequestInit => ({method, body:JSON.stringify(data)});
