"""Single-use recovery codes, with account cooldowns shared across delivery channels."""
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
import httpx
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from .config import PRODUCTION
from .db import now,stamp
from .models import User,ResetToken
from .security import token_hash

logger=logging.getLogger('smarteye.recovery')
OTP_SECONDS=600
RESET_SECONDS=300
COOLDOWN=60
MAX_ATTEMPTS=5
INVALID='Mã xác nhận không đúng hoặc đã hết hạn. Vui lòng kiểm tra hoặc yêu cầu mã mới.'


def settings():
    secret=len(os.getenv('AUTH_OTP_SECRET',''))>=32
    host=os.getenv('SMTP_HOST','').strip()
    sender=os.getenv('SMTP_FROM','') or os.getenv('SMTP_USER','')
    tls=os.getenv('SMTP_SECURITY','starttls')
    email=bool(secret and host and sender and tls in ('starttls','ssl','none') and
        (tls!='none' or (not PRODUCTION and host in ('localhost','127.0.0.1','mailpit'))))
    sid=os.getenv('TWILIO_ACCOUNT_SID','')
    sms=bool(secret and re.fullmatch(r'AC[0-9a-fA-F]{32}',sid) and os.getenv('TWILIO_AUTH_TOKEN') and
        (os.getenv('TWILIO_MESSAGING_SERVICE_SID') or os.getenv('TWILIO_FROM')))
    return {'email':email,'sms':sms}


def digest(value):
    secret=os.getenv('AUTH_OTP_SECRET','')
    if len(secret)<32:raise HTTPException(503,'Khôi phục mật khẩu tạm chưa sẵn sàng. Vui lòng liên hệ hỗ trợ.')
    return hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()


def phone_aliases(value):
    if value.startswith('0') and len(value)==10:return [value,'+84'+value[1:]]
    if value.startswith('+84') and len(value)==12:return [value,'0'+value[3:]]
    return [value]


def sms_number(value):
    if value.startswith('0') and len(value)==10:return '+84'+value[1:]
    if re.fullmatch(r'\+[1-9][0-9]{8,14}',value):return value
    raise ValueError('SMS requires an international number or a Vietnamese mobile number.')


def send_code(delivery,recipient,code):
    if delivery=='sms':
        sid=os.environ['TWILIO_ACCOUNT_SID']
        body={'To':sms_number(recipient),'Body':f'SmartEye: Ma xac nhan dat lai mat khau la {code}. Ma co hieu luc 10 phut. Khong chia se ma nay.'}
        service=os.getenv('TWILIO_MESSAGING_SERVICE_SID')
        body['MessagingServiceSid' if service else 'From']=service or os.environ['TWILIO_FROM']
        # Fixed TLS endpoint; never follow a redirect carrying provider credentials.
        with httpx.Client(timeout=10,follow_redirects=False) as client:
            response=client.post(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
                data=body,auth=(sid,os.environ['TWILIO_AUTH_TOKEN']))
        if response.status_code!=201:raise RuntimeError('SMS provider rejected delivery.')
        return
    msg=EmailMessage();msg['Subject']='Mã xác nhận khôi phục mật khẩu SmartEye'
    msg['From']=os.getenv('SMTP_FROM') or os.environ['SMTP_USER'];msg['To']=recipient
    msg.set_content(f'Mã xác nhận SmartEye của bạn: {code}\n\nMã có hiệu lực 10 phút, chỉ sử dụng một lần. Không chia sẻ mã này.\nNếu bạn không yêu cầu đổi mật khẩu, hãy bỏ qua thư này.')
    host=os.environ['SMTP_HOST'];security=os.getenv('SMTP_SECURITY','starttls')
    port=int(os.getenv('SMTP_PORT','465' if security=='ssl' else '587'))
    if security=='none' and (PRODUCTION or host not in ('localhost','127.0.0.1','mailpit')):
        raise RuntimeError('Unencrypted mail is restricted to local development.')
    context=ssl.create_default_context()
    connection=smtplib.SMTP_SSL(host,port,timeout=10,context=context) if security=='ssl' else smtplib.SMTP(host,port,timeout=10)
    with connection as smtp:
        if security=='starttls':smtp.starttls(context=context)
        if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
        smtp.send_message(msg)


def deliver(database,key,challenge_hash,delivery,recipient,code):
    query={'_id':key,'challenge_hash':challenge_hash,'verified':False,'expires_at':{'$gt':stamp()}}
    if not database.password_otps.find_one(query):return
    try:send_code(delivery,recipient,code)
    except Exception:
        # Do not log recipient, OTP, provider response bodies or credentials.
        logger.warning('Recovery %s delivery failed',delivery)
        return
    database.password_otps.update_one(query,{'$set':{'sent':True}})


def request_code(body,db,tasks):
    if not settings()[body.delivery]:
        method='email' if body.delivery=='email' else 'SMS'
        raise HTTPException(503,f'Gửi mã qua {method} tạm chưa sẵn sàng. Vui lòng thử cách khác hoặc liên hệ hỗ trợ.')
    if body.delivery=='email':row=db.find_one(User,{'email':body.identifier,'active':True})
    else:
        matches=db.find(User,{'phone':{'$in':phone_aliases(body.identifier)},'active':True},limit=2)
        row=matches[0] if len(matches)==1 else None
    # An opaque challenge and the same message are returned for unknown accounts.
    key=digest(f'account:{row.id}' if row else f'unknown:{body.delivery}:{body.identifier}')
    challenge=secrets.token_urlsafe(32);code=f'{secrets.randbelow(1000000):06d}'
    issued=now();expires=issued+timedelta(seconds=OTP_SECONDS)
    previous=db.database.password_otps.find_one({'_id':key})
    recent=[value for value in (previous or {}).get('request_times',[]) if value>(issued-timedelta(hours=1)).isoformat()]
    if len(recent)>=5:
        raise HTTPException(429,'Bạn đã yêu cầu nhiều mã. Vui lòng thử lại sau một giờ.',headers={'Retry-After':'3600'})
    if previous and previous['requested_at']>(issued-timedelta(seconds=COOLDOWN)).isoformat():
        raise HTTPException(429,'Vui lòng chờ một phút trước khi yêu cầu mã mới.',headers={'Retry-After':str(COOLDOWN)})
    document={'challenge_hash':token_hash(challenge),'otp_hash':digest(f'{challenge}:{code}'),
        'user_id':row.id if row else None,'email':row.email if row else None,'phone':row.phone if row else None,
        'auth_version':row.auth_version if row else None,'delivery':body.delivery,'attempts':0,'verified':False,'sent':False,
        'requested_at':issued.isoformat(),'expires_at':expires.isoformat(),'expires_on':issued+timedelta(hours=1),
        'request_times':recent+[issued.isoformat()]}
    try:
        db.database.password_otps.find_one_and_update({'_id':key,'requested_at':previous['requested_at'] if previous else {'$exists':False}},
            {'$set':document},upsert=True)
    except DuplicateKeyError:
        raise HTTPException(429,'Vui lòng chờ một phút trước khi yêu cầu mã mới.',headers={'Retry-After':str(COOLDOWN)}) from None
    if row:
        db.delete_many(ResetToken,{'user_id':row.id})
        recipient=row.email if body.delivery=='email' else row.phone
        tasks.add_task(deliver,db.database,key,document['challenge_hash'],body.delivery,recipient,code)
    return {'challenge':challenge,'expires_in':OTP_SECONDS,'resend_after':COOLDOWN,'delivery':body.delivery,
        'message':'Nếu thông tin khớp với tài khoản đang hoạt động, mã OTP sẽ được gửi tới địa chỉ đã đăng ký.'}


def verify_code(body,db):
    challenge_hash=token_hash(body.challenge)
    document=db.database.password_otps.find_one_and_update({'challenge_hash':challenge_hash,'verified':False,
        'expires_at':{'$gt':stamp()},'attempts':{'$lt':MAX_ATTEMPTS}},
        {'$inc':{'attempts':1}},return_document=ReturnDocument.AFTER)
    if not document:raise HTTPException(400,INVALID)
    correct=hmac.compare_digest(document['otp_hash'],digest(f'{body.challenge}:{body.code}'))
    row=db.get(User,document['user_id']) if document['user_id'] is not None else None
    if not correct or not document['sent'] or not row or not row.active or row.auth_version!=document['auth_version'] or row.email!=document['email'] or row.phone!=document['phone']:
        raise HTTPException(400,INVALID)
    expires=now()+timedelta(seconds=RESET_SECONDS)
    claimed=db.database.password_otps.update_one({'_id':document['_id'],'challenge_hash':challenge_hash,
        'verified':False,'expires_at':{'$gt':stamp()}},
        {'$set':{'verified':True,'expires_at':expires.isoformat()}})
    if claimed.modified_count!=1:raise HTTPException(400,INVALID)
    token=secrets.token_urlsafe(32)
    db.add(ResetToken(token_hash=token_hash(token),user_id=row.id,auth_version=row.auth_version,expires_at=expires.isoformat(),
        recovery_key=document['_id'],recovery_challenge_hash=challenge_hash,contact_email=row.email,contact_phone=row.phone))
    db.commit()
    return {'token':token,'expires_in':RESET_SECONDS,'message':'Đã xác nhận. Bạn có thể đặt mật khẩu mới.'}
