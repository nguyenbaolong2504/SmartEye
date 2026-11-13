from datetime import timedelta
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
import httpx
from backend.app import password_recovery as recovery
from backend.app.db import SessionLocal,now,stamp,get_database
from backend.app.models import User,ResetToken,LoginSession
from backend.app.passwords import hash_password,verify_password
from backend.app.security import token_hash

REAL_SEND_CODE=recovery.send_code


@pytest.fixture
def account(client,monkeypatch):
    monkeypatch.setenv('AUTH_OTP_SECRET','test-only-key-for-password-recovery-2026')
    for key,value in {'SMTP_HOST':'smtp.example.invalid','SMTP_PORT':'587','SMTP_USER':'sender@example.invalid',
        'SMTP_FROM':'sender@example.invalid','SMTP_PASSWORD':'fake-only','SMTP_SECURITY':'starttls',
        'TWILIO_ACCOUNT_SID':'AC'+'a'*32,'TWILIO_AUTH_TOKEN':'test-only-token','TWILIO_FROM':'+15005550006',
        'TWILIO_MESSAGING_SERVICE_SID':''}.items():monkeypatch.setenv(key,value)
    sent=[]
    monkeypatch.setattr(recovery,'send_code',lambda delivery,recipient,code:sent.append((delivery,recipient,code)))
    with SessionLocal() as db:
        user=User(name='Recovery test',username='recovery',email='recovery@example.invalid',phone='0911111111',password=hash_password('original-test-password'))
        db.add(user);db.commit()
    return SimpleNamespace(client=client,user=user,sent=sent)


def request(account,delivery='email',identifier=None):
    return account.client.post('/api/auth/forgot-password',json={'identifier':identifier or (account.user.email if delivery=='email' else account.user.phone),'delivery':delivery})


def verify(account,challenge,code=None):
    return account.client.post('/api/auth/verify-reset-otp',json={'challenge':challenge,'code':code or account.sent[-1][2]})


def allow_resend():
    get_database().password_otps.update_many({}, {'$set':{'requested_at':(now()-timedelta(seconds=61)).isoformat()}})


def test_email_otp_is_private_single_use_and_does_not_change_password_before_verification(account):
    response=request(account);assert response.status_code==200
    body=response.json();assert body['expires_in']==600 and body['resend_after']==60
    assert account.sent[0][:2]==('email',account.user.email)
    assert 'code' not in body and account.sent[0][2] not in response.text
    document=get_database().password_otps.find_one()
    assert document['sent'] and document['otp_hash']!=account.sent[0][2]
    assert document['expires_on']>now()+timedelta(minutes=50)
    assert 'challenge' not in document and body['challenge'] not in str(document)
    with SessionLocal() as db:assert verify_password('original-test-password',db.get(User,account.user.id).password)
    grant=verify(account,body['challenge']);assert grant.status_code==200
    assert verify(account,body['challenge']).status_code==400
    assert account.client.post('/api/auth/reset-password',json={'token':grant.json()['token'],'password':'new-test-password-2026','password_confirmation':'new-test-password-2026'}).status_code==200
    with SessionLocal() as db:
        assert verify_password('new-test-password-2026',db.get(User,account.user.id).password)
        assert db.count(ResetToken)==0
    assert account.client.post('/api/auth/reset-password',json={'token':grant.json()['token'],'password':'another-test-password'}).status_code==400


def test_sms_matches_registered_vietnamese_number_and_reset_revokes_sessions(account):
    assert account.client.post('/api/auth/login',json={'email':account.user.email,'password':'original-test-password'}).status_code==200
    old_cookie=account.client.cookies.get('smarteye_session')
    body=request(account,'sms','+84911111111').json()
    assert account.sent[-1][:2]==('sms','0911111111')
    grant=verify(account,body['challenge']).json()
    assert account.client.post('/api/auth/reset-password',json={'token':grant['token'],'password':'new-test-password-2026'}).status_code==200
    account.client.cookies.clear();account.client.cookies.set('smarteye_session',old_cookie)
    assert account.client.get('/api/auth/me').json() is None
    assert account.client.post('/api/auth/login',json={'email':account.user.email,'password':'original-test-password'}).status_code==401
    assert account.client.post('/api/auth/login',json={'email':account.user.email,'password':'new-test-password-2026'}).status_code==200


def test_unknown_contact_never_sends_and_has_the_same_public_response(account):
    valid=request(account).json()
    unknown=request(account,identifier='absent@example.invalid').json()
    assert {k:v for k,v in valid.items() if k!='challenge'}=={k:v for k,v in unknown.items() if k!='challenge'}
    assert len(account.sent)==1
    assert verify(account,unknown['challenge'],'123456').status_code==400
    assert get_database().reset_tokens.count_documents({})==0


def test_otp_expires_and_five_wrong_attempts_lock_challenge(account):
    body=request(account).json();real=account.sent[-1][2];wrong='000000' if real!='000000' else '999999'
    for _ in range(5):assert verify(account,body['challenge'],wrong).status_code==400
    assert verify(account,body['challenge'],real).status_code==400
    allow_resend();body=request(account).json()
    get_database().password_otps.update_many({}, {'$set':{'expires_at':(now()-timedelta(seconds=1)).isoformat()}})
    assert verify(account,body['challenge']).status_code==400


def test_resend_cooldown_is_shared_between_email_and_sms_and_replaces_old_challenge(account):
    first=request(account).json()
    assert request(account,'sms').status_code==429
    assert len(account.sent)==1
    allow_resend();second=request(account,'sms').json()
    assert second['challenge']!=first['challenge'] and len(account.sent)==2
    assert verify(account,first['challenge']).status_code==400
    assert verify(account,second['challenge']).status_code==200


def test_account_cannot_request_more_than_five_codes_per_hour(account):
    for _ in range(5):
        assert request(account).status_code==200
        allow_resend()
    assert request(account).status_code==429
    assert len(account.sent)==5


@pytest.mark.parametrize('change',[{'active':False},{'email':'changed@example.invalid'},{'phone':'0922222222'},{'auth_version':1}])
def test_lock_contact_or_password_change_invalidates_code(account,change):
    body=request(account).json()
    with SessionLocal() as db:db.update(User,account.user.id,change)
    assert verify(account,body['challenge']).status_code==400


def test_new_request_or_contact_change_invalidates_previously_verified_grant(account):
    first=request(account).json();grant=verify(account,first['challenge']).json()['token']
    allow_resend();second=request(account).json()
    assert account.client.post('/api/auth/reset-password',json={'token':grant,'password':'new-test-password-2026'}).status_code==400
    grant=verify(account,second['challenge']).json()['token']
    with SessionLocal() as db:db.update(User,account.user.id,{'email':'changed@example.invalid'})
    assert account.client.post('/api/auth/reset-password',json={'token':grant,'password':'new-test-password-2026'}).status_code==400


def test_delivery_failure_never_authorizes_reset_and_does_not_log_secrets(account,monkeypatch,caplog):
    def fail(*args):raise RuntimeError('secret provider response must not be logged')
    monkeypatch.setattr(recovery,'send_code',fail)
    body=request(account).json()
    assert not get_database().password_otps.find_one()['sent']
    assert verify(account,body['challenge'],'123456').status_code==400
    assert 'secret provider response' not in caplog.text and account.user.email not in caplog.text


def test_missing_delivery_configuration_and_invalid_inputs_are_explicit(account,monkeypatch):
    monkeypatch.setenv('SMTP_HOST','');monkeypatch.setenv('TWILIO_AUTH_TOKEN','')
    assert request(account).status_code==503 and request(account,'sms').status_code==503
    assert account.client.get('/api/config').json()['password_reset_channels']=={'email':False,'sms':False}
    assert request(account,identifier='not-email').status_code==422
    assert request(account,'sms','invalid-phone').status_code==422
    assert account.client.post('/api/auth/verify-reset-otp',json={'challenge':'x'*43,'code':'12'}).status_code==422
    assert account.client.post('/api/auth/reset-password',json={'token':'x'*43,'password':'long-password-2026','password_confirmation':'different-password'}).status_code==422


def test_concurrent_verification_issues_only_one_grant(account):
    from backend.app.schemas import VerifyResetOTP
    from fastapi import HTTPException
    body=request(account).json();data=VerifyResetOTP(challenge=body['challenge'],code=account.sent[-1][2])
    def run():
        with SessionLocal() as db:
            try:return recovery.verify_code(data,db)
            except HTTPException:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert sum(value is not None for value in results)==1
    assert get_database().reset_tokens.count_documents({})==1


def test_twilio_transport_uses_fixed_tls_endpoint_auth_and_normalized_number(account,monkeypatch):
    seen=[]
    class Transport:
        def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def post(self,url,**kwargs):seen.append((url,kwargs));return httpx.Response(201)
    monkeypatch.setattr(httpx,'Client',Transport)
    REAL_SEND_CODE('sms','0911111111','123456')
    assert seen[0][0].startswith('https://api.twilio.com/2010-04-01/Accounts/AC')
    assert seen[0][1]['data']['To']=='+84911111111' and '123456' in seen[0][1]['data']['Body']
    assert seen[0][1]['auth'][1]=='test-only-token'


def test_plain_smtp_is_never_allowed_in_production(account,monkeypatch):
    monkeypatch.setattr(recovery,'PRODUCTION',True)
    monkeypatch.setenv('SMTP_HOST','localhost');monkeypatch.setenv('SMTP_SECURITY','none')
    assert not recovery.settings()['email']


@pytest.mark.parametrize('security,port',[('starttls','587'),('ssl','465')])
def test_email_transport_verifies_tls_and_sends_code_only_to_registered_recipient(account,monkeypatch,security,port):
    monkeypatch.setenv('SMTP_SECURITY',security);monkeypatch.setenv('SMTP_PORT',port)
    seen=[]
    class SMTP:
        def __init__(self,host,number,**options):
            assert host=='smtp.example.invalid' and number==int(port)
            if security=='ssl':assert options['context'].check_hostname
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def starttls(self,context):assert context.check_hostname;seen.append('tls')
        def login(self,username,password):assert username=='sender@example.invalid' and password=='fake-only'
        def send_message(self,message):seen.append(message)
    monkeypatch.setattr(recovery.smtplib,'SMTP',SMTP);monkeypatch.setattr(recovery.smtplib,'SMTP_SSL',SMTP)
    REAL_SEND_CODE('email','recovery@example.invalid','123456')
    message=seen[-1];assert message['To']=='recovery@example.invalid' and '123456' in message.get_content()
    assert ('tls' in seen)==(security=='starttls')


def test_simultaneous_requests_cannot_bypass_cooldown(account):
    from backend.app.schemas import ResetRequest
    from fastapi import BackgroundTasks,HTTPException
    body=ResetRequest(identifier=account.user.email,delivery='email')
    def run():
        with SessionLocal() as db:
            try:return recovery.request_code(body,db,BackgroundTasks())
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert sum(isinstance(value,dict) for value in results)==1 and 429 in results


def test_ambiguous_phone_alias_does_not_pick_another_account(account):
    with SessionLocal() as db:
        db.add(User(name='Another phone record',email='another@example.invalid',username='another',phone='+84911111111',password=hash_password('original-test-password')));db.commit()
    value=request(account,'sms').json()
    assert account.sent==[] and verify(account,value['challenge'],'123456').status_code==400
