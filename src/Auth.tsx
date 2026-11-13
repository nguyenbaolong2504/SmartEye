import {can} from './permissions';
import {useState} from 'react';
import {LogOut} from 'lucide-react';
import {api,json} from './api';
import {Feedback,useAction} from './business';
import type {User} from './types';
export {AuthModal} from './AuthDialog';

export function ProfilePage({user, onUser}: {user: User; onUser: (user: User | null) => void}) {
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [phone, setPhone] = useState(user.phone || '');
  const [notifications, setNotifications] = useState(Boolean(user.notifications_enabled));
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const action = useAction();

  function resetProfile() {
    setName(user.name);
    setEmail(user.email);
    setPhone(user.phone || '');
    setNotifications(Boolean(user.notifications_enabled));
    action.setError('');
  }
  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    await action.run(async () => {
      const next = await api<User>('/auth/profile', json({name, email, phone, ...(can(user,'alerts.view')&&{notifications_enabled:notifications}), revision:user.profile_version}, 'PATCH'));
      onUser(next);
    }, 'Đã cập nhật hồ sơ.');
  }
  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    await action.run(async () => {
      if (password !== confirmation) throw new Error('Mật khẩu mới và xác nhận không khớp.');
      await api('/auth/password', json({current_password: current, new_password: password, password_confirmation: confirmation}));
      setCurrent('');
      setPassword('');
      setConfirmation('');
    }, 'Đã đổi mật khẩu và thu hồi các phiên cũ.');
  }
  return <>
    <div className="page-heading">
      <div><div className="eyebrow">TÀI KHOẢN CÁ NHÂN</div><h1>Hồ sơ của bạn<span>.</span></h1><p>{user.email} · {user.role === 'admin' ? 'Quản trị viên' : user.role === 'analyst' ? 'Quản lý' : 'Người dùng'}</p></div>
      <button className="button" disabled={action.busy} onClick={() => action.run(async () => {await api('/auth/logout', {method: 'POST'}); onUser(null);})}><LogOut size={16}/>Đăng xuất</button>
    </div>
    <Feedback error={action.error} success={action.success}/>
    <div className="two-columns">
      <section className="card"><h2>Thông tin cá nhân</h2>
        <form onSubmit={saveProfile}>
          <label className="field">Tên đăng nhập<input value={user.username || user.email} readOnly/></label>
          <label className="field">Họ và tên<input value={name} onChange={e => setName(e.target.value)} minLength={2} maxLength={100} required/></label>
          <label className="field">Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} maxLength={254} required/></label>
          <label className="field">Số điện thoại<input type="tel" value={phone} onChange={e => setPhone(e.target.value)} maxLength={24}/></label>
          {can(user,'alerts.view')&&<label className="check"><input type="checkbox" checked={notifications} onChange={e => setNotifications(e.target.checked)}/>Nhận thông báo khi có cảnh báo được phát hành</label>}
          <div className="workflow-buttons"><button type="button" className="button" onClick={resetProfile}>Hủy</button><button className="button primary" disabled={action.busy}>Lưu hồ sơ</button></div>
        </form>
      </section>
      <section className="card"><h2>Đổi mật khẩu</h2>
        <form onSubmit={changePassword}>
          <label className="field">Mật khẩu hiện tại<input type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} required/></label>
          <label className="field">Mật khẩu mới<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required minLength={10} maxLength={128}/></label>
          <label className="field">Xác nhận mật khẩu mới<input type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} required minLength={10} maxLength={128}/></label>
          <div className="workflow-buttons"><button type="button" className="button" onClick={() => {setCurrent(''); setPassword(''); setConfirmation('');}}>Hủy</button><button className="button primary" disabled={action.busy}>Đổi mật khẩu</button></div>
        </form>
      </section>
    </div>
  </>;
}
