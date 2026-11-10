import {useState} from 'react';
import {LockKeyhole, LogOut} from 'lucide-react';
import {api, json} from './api';
import {Modal, Spinner} from './components';
import {Feedback, useAction} from './business';
import {type User, type Config} from './types';

type Mode = 'login' | 'register' | 'forgot' | 'reset';

export function AuthModal({onClose, onUser, config, resetToken}: {
  onClose: () => void; onUser: (user: User | null) => void; config: Config; resetToken?: string;
}) {
  const [mode, setMode] = useState<Mode>(resetToken ? 'reset' : 'login');
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState('');
  const action = useAction();

  function changeMode(next: Mode) {
    setMode(next);
    setPassword('');
    setConfirmation('');
    setMessage('');
    action.setError('');
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await action.run(async () => {
      setMessage('');
      if (mode === 'login') {
        const user = await api<User>('/auth/login', json({email, password}));
        onUser(user);
        onClose();
      } else if (mode === 'register') {
        if (password !== confirmation) throw new Error('Mật khẩu và xác nhận không khớp.');
        await api('/auth/register', json({name, username, email, phone, password, password_confirmation: confirmation}));
        changeMode('login');
        setMessage('Tạo tài khoản thành công. Vui lòng đăng nhập.');
      } else if (mode === 'forgot') {
        const result = await api<{message: string}>('/auth/forgot-password', json({email}));
        setMessage(result.message);
      } else {
        const result = await api<{message: string}>('/auth/reset-password', json({token: resetToken, password}));
        changeMode('login');
        setMessage(result.message);
        history.replaceState(null, '', location.pathname + location.hash);
      }
    });
  }

  const titles = {login: 'Chào mừng trở lại', register: 'Tạo tài khoản SmartEye', forgot: 'Khôi phục mật khẩu', reset: 'Chọn mật khẩu mới'};
  const labels = {login: 'Đăng nhập', register: 'Tạo tài khoản', forgot: 'Gửi hướng dẫn', reset: 'Đặt lại mật khẩu'};
  return <Modal title={titles[mode]} onClose={onClose}>
    <Feedback error={action.error} success={message}/>
    <form onSubmit={submit}>
      {mode === 'register' && <>
        <label className="field">Họ và tên<input value={name} onChange={e => setName(e.target.value)} required minLength={2} maxLength={100} autoComplete="name"/></label>
        <label className="field">Tên đăng nhập<input aria-label="Tên đăng nhập" aria-describedby="signup-username-hint" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={40} autoComplete="username"/><small id="signup-username-hint">Dùng chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang.</small></label>
      </>}
      {mode !== 'reset' && <label className="field">{mode === 'login' ? 'Email hoặc tên đăng nhập' : 'Email'}<input type={mode === 'login' ? 'text' : 'email'} autoComplete={mode === 'login' ? 'username' : 'email'} value={email} onChange={e => setEmail(e.target.value)} required maxLength={254}/></label>}
      {mode === 'register' && <label className="field">Số điện thoại (không bắt buộc)<input type="tel" value={phone} onChange={e => setPhone(e.target.value)} maxLength={24} autoComplete="tel"/></label>}
      {mode !== 'forgot' && <label className="field">Mật khẩu<input aria-label="Mật khẩu" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} required minLength={mode === 'login' ? 1 : 10} maxLength={128}/>{mode !== 'login' && <small>Ít nhất 10 ký tự.</small>}</label>}
      {mode === 'register' && <label className="field">Xác nhận mật khẩu<input type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} required minLength={10} maxLength={128}/></label>}
      <button className="button primary full" disabled={action.busy}>{action.busy ? <Spinner/> : <LockKeyhole size={16}/>} {labels[mode]}</button>
    </form>
    <div className="auth-links">
      {mode === 'login' ? <>
        <button className="text-button" onClick={() => changeMode('register')}>Tạo tài khoản mới</button>
        <button className="text-button" disabled={!config.password_reset_available} onClick={() => changeMode('forgot')} title={!config.password_reset_available ? 'Máy chủ chưa cấu hình email' : undefined}>Quên mật khẩu?</button>
      </> : <button className="text-button" onClick={() => changeMode('login')}>Quay lại đăng nhập</button>}
    </div>
  </Modal>;
}

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
      const next = await api<User>('/auth/profile', json({name, email, phone, notifications_enabled: notifications, revision: user.profile_version}, 'PATCH'));
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
          <label className="check"><input type="checkbox" checked={notifications} onChange={e => setNotifications(e.target.checked)}/>Nhận thông báo khi có cảnh báo được phát hành</label>
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
