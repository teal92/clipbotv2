import base64, io
import pytest
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from server.store import Store

def setup(tmp_path):
    from server.account_profile import build_account_router
    store=Store(tmp_path/'account.db');a=store.create_user('a@test.com','long-password-123','A');b=store.create_user('b@test.com','long-password-123','B')
    token,csrf=store.new_session(a)
    app=FastAPI()
    def current(request,write=False):
        session=store.session(request.cookies.get('clipbot_session',''))
        if not session:raise HTTPException(401)
        if write and request.headers.get('x-csrf-token')!=session['csrf']:raise HTTPException(403)
        return session
    app.include_router(build_account_router(store,current,lambda request:None,lambda session:{'user':store.user(session['user_id'])}))
    client=TestClient(app);client.cookies.set('clipbot_session',token)
    return store,a,b,client,{'x-csrf-token':csrf}

def test_profile_is_owned_and_password_never_returned(tmp_path):
    store,a,b,client,headers=setup(tmp_path)
    assert client.patch('/api/account/profile',json={'username':'alice_1'}).status_code==403
    assert client.patch('/api/account/profile',json={'username':'alice_1','user_id':b},headers=headers).status_code==422
    response=client.patch('/api/account/profile',json={'username':'alice_1'},headers=headers)
    assert response.status_code==200
    assert response.json()['user']['username']=='alice_1'
    assert store.user(b)['name']=='B'
    assert 'password' not in response.text
    assert Store(store.path).user(a)['username']=='alice_1'

def test_password_requires_current_revokes_other_sessions_and_workers(tmp_path):
    store,a,b,client,headers=setup(tmp_path);other,_=store.new_session(a);btoken,_=store.new_session(b);worker=store.connect_worker(store.new_pairing(a))
    assert client.post('/api/account/password',json={'currentPassword':'wrong-long-password','newPassword':'Different-password-123!'},headers=headers).status_code==403
    assert store.session(other)
    response=client.post('/api/account/password',json={'currentPassword':'long-password-123','newPassword':'Different-password-123!'},headers=headers)
    assert response.status_code==200
    assert store.authenticate('a@test.com','long-password-123') is None
    assert store.authenticate('a@test.com','Different-password-123!')==a
    assert store.session(other) is None and store.session(btoken)
    assert store.session(client.cookies.get('clipbot_session'))
    assert not store.worker_heartbeat(worker)

def test_avatar_reencoded_and_rejects_nonimages(tmp_path):
    store,a,b,client,headers=setup(tmp_path)
    buf=io.BytesIO();Image.new('RGB',(320,200),'red').save(buf,format='JPEG',comment=b'private metadata')
    response=client.put('/api/account/avatar',json={'image':base64.b64encode(buf.getvalue()).decode()},headers=headers)
    assert response.status_code==200
    value=response.json()['user']['avatar'];assert value.startswith('data:image/png;base64,')
    with Image.open(io.BytesIO(base64.b64decode(value.split(',')[1]))) as im:assert im.size==(256,256)
    assert client.put('/api/account/avatar',json={'image':base64.b64encode(b'<svg/>').decode()},headers=headers).status_code==422
    assert client.put('/api/account/avatar',json={'image':'https://evil.test/avatar'},headers=headers).status_code==422
    assert not store.user(b)['avatar']

def test_username_collision_is_atomic_and_empty_usernames_rejected(tmp_path):
    store,a,b,client,headers=setup(tmp_path)
    store.update_profile(b,'alice')
    assert client.patch('/api/account/profile',json={'username':'ALICE'},headers=headers).status_code==409
    assert store.user(a)['name']=='A'
    assert client.patch('/api/account/profile',json={'username':''},headers=headers).status_code==422
    assert store.user(a)['username']=='A'

def test_untrusted_fields_weak_passwords_and_huge_images_rejected(tmp_path):
    store,a,b,client,headers=setup(tmp_path)
    assert client.post('/api/account/password',json={'currentPassword':'long-password-123','newPassword':'short'},headers=headers).status_code==422
    assert client.patch('/api/account/profile',json={'name':'  ','username':'invalid!'},headers=headers).status_code==422
    assert client.put('/api/account/avatar',json={'image':'A'*175001},headers=headers).status_code==422
    client.cookies.clear()
    assert client.patch('/api/account/profile',json={'username':'valid'},headers=headers).status_code==401

def test_avatar_pixel_bomb_animation_and_remove(tmp_path):
    store,a,b,client,headers=setup(tmp_path)
    for size in [(2100,2100)]:
        buf=io.BytesIO();Image.new('RGB',size,'white').save(buf,format='PNG')
        assert client.put('/api/account/avatar',json={'image':base64.b64encode(buf.getvalue()).decode()},headers=headers).status_code==422
    frames=[Image.new('RGB',(10,10),color) for color in ('red','blue')];buf=io.BytesIO();frames[0].save(buf,format='PNG',save_all=True,append_images=frames[1:])
    assert client.put('/api/account/avatar',json={'image':base64.b64encode(buf.getvalue()).decode()},headers=headers).status_code==422
    assert client.put('/api/account/avatar',json={'image':''},headers=headers).status_code==200
    assert store.user(a)['avatar']==''

def test_auth_limits_survive_restart_and_cannot_parallel_bypass(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store=Store(tmp_path/'rate.db')
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda _:store.auth_rate('ip'),range(25)))
    assert sum(results)==20
    assert not Store(store.path).auth_rate('ip')

def test_profile_route_enforces_cooldown_and_unchanged_does_not_restart_it(tmp_path):
    store,a,b,client,headers=setup(tmp_path)
    first=client.patch('/api/account/profile',json={'username':'first_name'},headers=headers)
    assert first.status_code==200
    changed=first.json()['user']['usernameChangedAt'];available=first.json()['user']['usernameChangeAvailableAt']
    assert available>changed
    same=client.patch('/api/account/profile',json={'username':'FIRST_NAME'},headers=headers)
    assert same.status_code==200 and same.json()['user']['usernameChangedAt']==changed
    assert client.patch('/api/account/profile',json={'username':'second_name'},headers=headers).status_code==409
    assert client.patch('/api/account/profile',json={'username':'second_name','usernameChangeAvailableAt':0},headers=headers).status_code==422
    assert client.patch('/api/account/profile',json={'username':'second_name','name':'Separate display name'},headers=headers).status_code==422
    assert store.user(a)['username']=='first_name'
