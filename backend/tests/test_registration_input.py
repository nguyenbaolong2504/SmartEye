import pytest


def payload(username):
    return {'name':'Người kiểm thử','username':username,'email':'username-check@example.invalid',
            'password':'test-registration-only-2026','password_confirmation':'test-registration-only-2026'}


@pytest.mark.parametrize('username,message',[
    ('student@example.invalid','Tên đăng nhập không dùng địa chỉ email'),
    ('tên có dấu','Tên đăng nhập chỉ dùng chữ không dấu'),
    ('ab','Tên đăng nhập cần từ 3 đến 40 ký tự'),
])
def test_signup_rejects_invalid_username_with_vietnamese_message(client,username,message):
    response=client.post('/api/auth/register',json=payload(username))
    assert response.status_code==422
    assert message in response.json()['detail'][0]['msg']
    assert 'String should match pattern' not in response.text


def test_signup_normalizes_copied_username_before_format_validation(client):
    response=client.post('/api/auth/register',json=payload('  User.Name_2026-Test  '))
    assert response.status_code==201,response.text
    assert response.json()['username']=='user.name_2026-test'
    login=client.post('/api/auth/login',json={'email':'USER.NAME_2026-TEST','password':'test-registration-only-2026'})
    assert login.status_code==200
