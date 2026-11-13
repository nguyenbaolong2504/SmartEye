import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,Check,Eye,EyeOff,KeyRound,LockKeyhole,Mail,MapPin,Phone,ShieldCheck,UserRound} from 'lucide-react';
import {api,json} from './api';
import {Modal,Spinner} from './components';
import {Feedback,useAction} from './business';
import type {User,Config} from './types';
import './auth.css';

type Mode='login'|'register'|'forgot'|'otp'|'reset';
type Delivery='email'|'sms';
type Challenge={challenge:string;expires_in:number;resend_after:number;delivery:Delivery;message:string};
const titles={login:'Chào mừng trở lại',register:'Tạo tài khoản SmartEye',forgot:'Khôi phục mật khẩu',otp:'Nhập mã xác nhận',reset:'Chọn mật khẩu mới'};
const labels={login:'Đăng nhập',register:'Tạo tài khoản',forgot:'Gửi mã OTP',otp:'Xác nhận mã',reset:'Đặt lại mật khẩu'};

export function AuthModal({onClose,onUser,config,resetToken}:{onClose:()=>void;onUser:(user:User|null)=>void;config:Config;resetToken?:string}){
  const [mode,setMode]=useState<Mode>(resetToken?'reset':'login');
  const [name,setName]=useState(''),[username,setUsername]=useState(''),[email,setEmail]=useState(''),[phone,setPhone]=useState('');
  const [password,setPassword]=useState(''),[confirmation,setConfirmation]=useState(''),[showPassword,setShowPassword]=useState(false);
  const [identifier,setIdentifier]=useState(''),[delivery,setDelivery]=useState<Delivery>('email'),[code,setCode]=useState('');
  const [challenge,setChallenge]=useState<Challenge|null>(null),[verifiedToken,setVerifiedToken]=useState(resetToken||'');
  const [expires,setExpires]=useState(0),[resendAt,setResendAt]=useState(0),[clock,setClock]=useState(Date.now());
  const [message,setMessage]=useState('');
  const action=useAction();
  const request=useRef<AbortController|null>(null);
  useEffect(()=>{
    const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
    // Keep a legacy recovery link out of subsequent URLs and referrer headers.
    if(resetToken){const url=new URL(location.href);url.searchParams.delete('reset');history.replaceState(null,'',url.pathname+url.search+url.hash);}
    return()=>{request.current?.abort();document.body.style.overflow=overflow;};
  },[]);
  useEffect(()=>{
    if(mode!=='otp')return;
    const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);
  },[mode]);
  function close(){request.current?.abort();onClose();}
  function changeMode(next:Mode){
    if(action.busy)return;
    request.current?.abort();setMode(next);setPassword('');setConfirmation('');setShowPassword(false);setMessage('');action.setError('');setCode('');setVerifiedToken('');
    if(next==='forgot'){
      const method=config.password_reset_channels?.email===false&&config.password_reset_channels?.sms?'sms':'email';
      setDelivery(method);setIdentifier(method==='email'&&email.includes('@')?email:'');setChallenge(null);
    }
  }
  async function call<T>(path:string,body:unknown){
    request.current?.abort();const controller=new AbortController();request.current=controller;
    const value=await api<T>(path,{...json(body),signal:controller.signal});
    if(controller.signal.aborted)throw new Error('Đã hủy yêu cầu.');
    return value;
  }
  async function sendOTP(){
    const value=await call<Challenge>('/auth/forgot-password',{identifier,delivery});
    setChallenge(value);setCode('');setVerifiedToken('');setClock(Date.now());
    setExpires(Date.now()+value.expires_in*1000);setResendAt(Date.now()+value.resend_after*1000);setMode('otp');setMessage('');
  }
  async function submit(event:React.FormEvent){
    event.preventDefault();
    await action.run(async()=>{
      setMessage('');
      if(mode==='login'){
        const user=await call<User>('/auth/login',{email,password});onUser(user);close();
      }else if(mode==='register'){
        if(password!==confirmation)throw new Error('Mật khẩu và xác nhận không khớp.');
        await call('/auth/register',{name,username,email,phone,password,password_confirmation:confirmation});
        setMode('login');setPassword('');setConfirmation('');setShowPassword(false);setMessage('Tạo tài khoản thành công. Bạn có thể đăng nhập ngay.');
      }else if(mode==='forgot')await sendOTP();
      else if(mode==='otp'){
        const value=await call<{token:string}>('/auth/verify-reset-otp',{challenge:challenge?.challenge,code});
        if(typeof value.token!=='string'||value.token.length<32)throw new Error('Chưa xác nhận được mã. Vui lòng thử lại.');
        setVerifiedToken(value.token);setCode('');setPassword('');setConfirmation('');setShowPassword(false);setMode('reset');
      }else{
        if(password!==confirmation)throw new Error('Mật khẩu và xác nhận không khớp.');
        const value=await call<{message:string}>('/auth/reset-password',{token:verifiedToken,password,password_confirmation:confirmation});
        setVerifiedToken('');setChallenge(null);setMode('login');setPassword('');setConfirmation('');setShowPassword(false);setMessage(value.message);
      }
    });
  }
  const seconds=Math.max(0,Math.ceil((expires-clock)/1000));
  const cooldown=Math.max(0,Math.ceil((resendAt-clock)/1000));
  const descriptions={login:'Đăng nhập để tiếp tục hành trình cùng SmartEye.',register:'Một vài thông tin để bắt đầu hành trình của bạn.',
    forgot:'Chọn cách nhận mã và nhập thông tin bạn đã dùng khi đăng ký.',
    otp:`Nhập mã 6 chữ số gửi qua ${delivery==='email'?'email':'SMS'} đến ${identifier}. Mã chỉ được gửi nếu thông tin khớp với tài khoản.`,
    reset:'Mật khẩu mới giúp bạn lấy lại quyền truy cập tài khoản.'};
  const recovery=['forgot','otp','reset'].includes(mode);
  const available=config.password_reset_channels?.[delivery]??config.password_reset_available;
  return <Modal title={titles[mode]} className={`auth-dialog${mode==='register'?' auth-registration':''}`} onClose={close}>
    <aside className="auth-story" aria-hidden="true"><div className="auth-story-brand"><span><MapPin size={24}/></span>SmartEye</div><div className="auth-orb auth-orb-one"/><div className="auth-orb auth-orb-two"/><div className="auth-orb auth-orb-three"/><div className="auth-story-copy"><span className="auth-story-badge"><NavigationIcon/>HIỂU ĐƯỜNG · CHỌN LỐI</span><h3>Mỗi hành trình,<br/>chủ động hơn.</h3><p>Lưu những tuyến đường quen thuộc và chọn thời điểm phù hợp cho chuyến đi.</p></div><span className="auth-story-bottom"><ShieldCheck size={15}/>Kết nối để bắt đầu hành trình</span></aside>
    <div className="auth-content"><p className="auth-description">{descriptions[mode]}</p>
      {recovery&&<ol className="auth-steps" aria-label="Các bước khôi phục">{['Thông tin','Mã OTP','Mật khẩu mới'].map((text,index)=>{const step=mode==='forgot'?0:mode==='otp'?1:2;return <li key={text} className={index<=step?'active':''} aria-current={index===step?'step':undefined}><span>{index<step?<Check size={12}/>:index+1}</span>{text}</li>;})}</ol>}
      <Feedback error={action.error} success={message}/>
      <form onSubmit={submit} className="auth-form">
        {mode==='register'&&<div className="auth-form-pair"><label className="field">Họ và tên<div className="auth-input"><UserRound size={16}/><input aria-label="Họ và tên" value={name} onChange={e=>setName(e.target.value)} required minLength={2} maxLength={100} autoComplete="name" placeholder="Tên của bạn"/></div></label><label className="field">Tên đăng nhập<div className="auth-input"><UserRound size={16}/><input aria-label="Tên đăng nhập" value={username} onChange={e=>setUsername(e.target.value)} required minLength={3} maxLength={40} pattern="[A-Za-z0-9_.-]+" autoComplete="username" placeholder="ten_dang_nhap"/></div></label><p className="auth-field-note">Tên đăng nhập dùng chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang.</p></div>}
        {['login','register'].includes(mode)&&<label className="field">{mode==='login'?'Email hoặc tên đăng nhập':'Email'}<div className="auth-input"><Mail size={16}/><input aria-label={mode==='login'?'Email hoặc tên đăng nhập':'Email'} type={mode==='login'?'text':'email'} autoComplete={mode==='login'?'username':'email'} value={email} onChange={e=>setEmail(e.target.value)} required maxLength={254} placeholder={mode==='login'?'Nhập email hoặc tên đăng nhập':'ban@example.com'}/></div></label>}
        {mode==='register'&&<label className="field">Số điện thoại (không bắt buộc)<div className="auth-input"><Phone size={16}/><input aria-label="Số điện thoại (không bắt buộc)" type="tel" value={phone} onChange={e=>setPhone(e.target.value)} maxLength={24} autoComplete="tel" placeholder="09xx xxx xxx"/></div><small>Thêm số điện thoại để có thể khôi phục tài khoản qua SMS.</small></label>}
        {mode==='forgot'&&<><div className="auth-delivery" role="group" aria-label="Cách nhận mã OTP">{(['email','sms'] as const).map(value=><button key={value} type="button" aria-pressed={delivery===value} disabled={action.busy} onClick={()=>{setDelivery(value);setIdentifier('');action.setError('');}}>{value==='email'?<Mail size={17}/>:<Phone size={17}/>}Qua {value==='email'?'email':'SMS'}</button>)}</div>
          <label className="field">{delivery==='email'?'Email đã đăng ký':'Số điện thoại đã đăng ký'}<div className="auth-input">{delivery==='email'?<Mail size={16}/>:<Phone size={16}/>}<input aria-label={delivery==='email'?'Email đã đăng ký':'Số điện thoại đã đăng ký'} type={delivery==='email'?'email':'tel'} value={identifier} onChange={e=>setIdentifier(e.target.value)} autoComplete={delivery==='email'?'email':'tel'} required maxLength={254} placeholder={delivery==='email'?'ban@example.com':'09xx xxx xxx'}/></div></label>
          {!available&&<p className="auth-channel-note">Cách nhận mã này hiện chưa sẵn sàng. Bạn có thể chọn cách khác hoặc liên hệ hỗ trợ.</p>}
        </>}
        {mode==='otp'&&<div className="auth-code-field"><label className="field">Mã OTP<div className="auth-input"><KeyRound size={18}/><input aria-label="Mã OTP" className="auth-code" value={code} onChange={e=>setCode(e.target.value.replace(/[^0-9]/g,'').slice(0,6))} required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code" placeholder="000000"/></div></label><p>{seconds?<>Mã có hiệu lực trong <b>{Math.floor(seconds/60)}:{String(seconds%60).padStart(2,'0')}</b></>:'Mã đã hết hạn. Vui lòng yêu cầu mã mới.'}</p></div>}
        {['login','register','reset'].includes(mode)&&<div className="auth-password"><div className="auth-password-label"><label htmlFor="auth-password">{mode==='reset'?'Mật khẩu mới':'Mật khẩu'}</label>{mode==='login'&&<button type="button" className="text-button" disabled={action.busy} onClick={()=>changeMode('forgot')}>Quên mật khẩu?</button>}</div><div className="auth-input"><LockKeyhole size={16}/><input id="auth-password" aria-label={mode==='reset'?'Mật khẩu mới':'Mật khẩu'} type={showPassword?'text':'password'} autoComplete={mode==='login'?'current-password':'new-password'} value={password} onChange={e=>setPassword(e.target.value)} required minLength={mode==='login'?1:10} maxLength={128} placeholder={mode==='login'?'Nhập mật khẩu':'Ít nhất 10 ký tự'}/><button type="button" className="auth-eye" aria-label={showPassword?'Ẩn mật khẩu':'Hiện mật khẩu'} aria-pressed={showPassword} onClick={()=>setShowPassword(value=>!value)}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div>{mode!=='login'&&<p className="auth-field-note">Ít nhất 10 ký tự.</p>}</div>}
        {['register','reset'].includes(mode)&&<label className="field">{mode==='reset'?'Xác nhận mật khẩu mới':'Xác nhận mật khẩu'}<div className="auth-input"><ShieldCheck size={16}/><input aria-label={mode==='reset'?'Xác nhận mật khẩu mới':'Xác nhận mật khẩu'} type={showPassword?'text':'password'} autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)} required minLength={10} maxLength={128} placeholder="Nhập lại mật khẩu"/></div></label>}
        <button className="button primary full auth-submit" disabled={action.busy||(mode==='otp'&&!seconds)}>{action.busy?<Spinner/>:<>{labels[mode]}<ArrowRight size={17}/></>}</button>
      </form>
      {mode==='otp'&&<div className="auth-resend"><span>Chưa nhận được mã?</span><button type="button" className="text-button" disabled={action.busy||cooldown>0} onClick={()=>void action.run(sendOTP)}>{cooldown?`Gửi lại sau ${cooldown}s`:'Gửi lại mã'}</button><button type="button" className="text-button" disabled={action.busy} onClick={()=>changeMode('forgot')}>Đổi thông tin nhận mã</button></div>}
      <div className="auth-bottom">{mode==='login'?<><span>Chưa có tài khoản?</span><button type="button" className="text-button" disabled={action.busy} onClick={()=>changeMode('register')}>Tạo tài khoản mới</button></>:<button type="button" className="text-button" disabled={action.busy} onClick={()=>changeMode('login')}><ArrowLeft size={14}/>Quay lại đăng nhập</button>}</div>
      <div className="auth-safe-note"><ShieldCheck size={13}/>{recovery?'Chỉ đặt lại mật khẩu sau khi xác nhận đúng mã OTP.':'Hành trình của bạn, trong tầm tay bạn.'}</div>
    </div>
  </Modal>;
}

function NavigationIcon(){return <MapPin size={12}/>;}
