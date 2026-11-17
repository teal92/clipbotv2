import pytest
from concurrent.futures import ThreadPoolExecutor
from server.store import Store
from server.report_delivery import ReportDelivery, ReportRejected

def report(title='A clear issue'):
    return dict(kind='feedback',area='Logs',title=title,details='Enough detail for the team to investigate.',steps='',expected='',frequency='unsure',impact='minor',environment='')

def test_missing_transport_saved_honestly_and_deduplicated(tmp_path):
    service=ReportDelivery(Store(tmp_path/'test.db'), config={})
    first=service.submit('user','ip',report())
    assert first['status']=='Received'
    assert service.submit('user','ip',report())['reference']==first['reference']
    assert service.deliver_one() is False

def test_validation_and_durable_ip_limits(tmp_path):
    store=Store(tmp_path/'test.db');service=ReportDelivery(store,config={})
    with pytest.raises(ReportRejected):service.submit('user','ip',report('Header\x00injection'))
    for i in range(10):service.submit(str(i),'shared-ip',report(f'Issue number {i}'))
    with pytest.raises(ReportRejected):ReportDelivery(store,config={}).submit('another','shared-ip',report('Another issue'))

def test_delivery_never_retries_unknown_outcome(tmp_path):
    sent=[]
    def transport(message):
        sent.append(message)
        raise TimeoutError('private diagnostic')
    service=ReportDelivery(Store(tmp_path/'test.db'),config={'enabled':True,'recipient':'support@example.com','sender':'robot@example.com'},transport=transport)
    receipt=service.submit('user','ip',report())
    assert receipt['status']=='Queued'
    assert service.deliver_one()
    assert not service.deliver_one()
    assert len(sent)==1
    assert service.receipts('user')[0]['status']=='Delivery unknown'
    assert not sent[0].is_multipart()
    assert sent[0]['To']=='support@example.com'

def test_mail_is_text_only_and_rejection_not_delivered(tmp_path):
    messages=[]
    service=ReportDelivery(Store(tmp_path/'test.db'),config={'enabled':True,'recipient':'support@example.com','sender':'robot@example.com'},transport=lambda msg:messages.append(msg))
    service.submit('user','ip',report('<script>issue</script>'))
    assert service.deliver_one()
    assert service.receipts('user')[0]['status']=='Accepted by mail server'
    assert messages[0].get_content_type()=='text/plain'
    assert messages[0]['Reply-To'] is None

@pytest.mark.parametrize('change',[{'attachments':['file.exe']},{'details':'x'*4001},{'title':'Header\nBcc: other@example.com','kind':'unknown'},{'title':'Bad\u202e title'}])
def test_client_cannot_add_files_or_bypass_validation(tmp_path,change):
    service=ReportDelivery(Store(tmp_path/'test.db'),config={})
    with pytest.raises(ReportRejected):service.submit('user','ip',{**report(),**change})

def test_user_limit_atomic_across_parallel_requests(tmp_path):
    service=ReportDelivery(Store(tmp_path/'test.db'),config={})
    def submit(i):
        try:return service.submit('user',f'ip-{i}',report(f'Parallel issue {i}'))
        except ReportRejected as error:return error.status
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(submit,range(12)))
    assert sum(isinstance(item,dict) for item in results)==5
    assert sum(item==429 for item in results)==7

def test_global_queue_is_bounded_and_claim_survives_restart(tmp_path):
    store=Store(tmp_path/'test.db')
    cfg={'enabled':True,'recipient':'support@example.com','sender':'robot@example.com'}
    service=ReportDelivery(store,config=cfg,transport=lambda msg:None)
    for i in range(100):service.submit(str(i),str(i),report(f'Queued issue {i}'))
    with pytest.raises(ReportRejected):service.submit('other','other',report('Overflow issue'))
    with store.connection() as db:
        db.execute("UPDATE report_delivery SET status='Delivery unknown',attempted=1")
    restarted=ReportDelivery(store,config=cfg,transport=lambda msg:pytest.fail('Must not resend'))
    assert not restarted.deliver_one()

def test_global_email_attempt_limit_is_durable(tmp_path,monkeypatch):
    moment=[2000000.0];monkeypatch.setattr('server.report_delivery.time.time',lambda:moment[0])
    store=Store(tmp_path/'test.db');cfg={'enabled':True,'recipient':'support@example.com','sender':'robot@example.com'}
    service=ReportDelivery(store,config=cfg,transport=lambda msg:None)
    for i in range(51):service.submit(str(i),str(i),report(f'Daily issue {i}'))
    for i in range(50):
        assert service.deliver_one()
        assert not service.deliver_one()
        moment[0]+=61
    assert not ReportDelivery(store,config=cfg,transport=lambda msg:pytest.fail('Daily cap exceeded')).deliver_one()

def test_refused_recipient_is_not_claimed_as_accepted(tmp_path):
    service=ReportDelivery(Store(tmp_path/'test.db'),config={'enabled':True,'recipient':'support@example.com','sender':'robot@example.com'},transport=lambda msg:{'support@example.com':(550,b'No')})
    service.submit('user','ip',report());assert service.deliver_one()
    assert service.receipts('user')[0]['status']=='Mail server rejected'

def test_configuration_requires_verified_tls_and_no_header_injection(monkeypatch):
    from server.report_delivery import mail_config
    for key in ['CLIPBOT_REPORT_EMAIL','CLIPBOT_REPORT_FROM','CLIPBOT_REPORT_SMTP_HOST','CLIPBOT_REPORT_SMTP_USERNAME','CLIPBOT_REPORT_SMTP_PASSWORD','CLIPBOT_REPORT_SMTP_PORT']:monkeypatch.delenv(key,raising=False)
    assert not mail_config()['enabled']
    for key,value in {'FROM':'robot@example.com','SMTP_HOST':'smtp.example.com','SMTP_USERNAME':'robot','SMTP_PASSWORD':'test-only','SMTP_PORT':'465'}.items():monkeypatch.setenv('CLIPBOT_REPORT_'+key,value)
    assert mail_config()['enabled']
    assert mail_config()['recipient']=='support@your-domain.example'
    monkeypatch.setenv('CLIPBOT_REPORT_FROM','robot@example.com\nBcc: other@example.com')
    assert not mail_config()['enabled']


def test_report_endpoint_uses_verified_client_attribution(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from server.app import create_app
 store=Store(tmp_path/'report-ip.db');uid=store.create_user('reports@example.test','SafePassword!2026','reports');token,csrf=store.new_session(uid)
 monkeypatch.setattr('server.app.client_ip',lambda request:'8.8.8.8')
 app=create_app(store,origin='http://testserver')
 with TestClient(app) as client:
  client.cookies.set('clipbot_session',token)
  response=client.post('/api/reports',headers={'Origin':'http://testserver','X-CSRF-Token':csrf},json=report())
 assert response.status_code==201
 import hashlib
 with store.connection() as db:assert db.execute('SELECT ip_hash FROM report_delivery').fetchone()[0]==hashlib.sha256(b'8.8.8.8').hexdigest()


def test_executable_looking_report_text_remains_plain_in_fixed_recipient_email(tmp_path):
    messages=[]
    cfg={'enabled':True,'recipient':'support@example.com','sender':'robot@example.com'}
    service=ReportDelivery(Store(tmp_path/'untrusted.db'),config=cfg,transport=messages.append)
    payload="<script>fetch('https://untrusted.example')</script> $(whoami) __import__('os').system('echo nope')"
    service.submit('user','ip',{**report(), 'details':payload})
    assert service.deliver_one() and len(messages)==1
    message=messages[0]
    assert message.get_content_type()=='text/plain'
    assert not message.is_multipart() and list(message.iter_attachments())==[]
    assert message['To']=='support@example.com' and message['Bcc'] is None
    assert payload in message.get_content()


def test_report_api_rejects_multipart_upload_and_hidden_attachment_fields(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import create_app
    monkeypatch.setenv('CLIPBOT_REPORT_SMTP_PASSWORD','')
    store=Store(tmp_path/'uploads.db');uid=store.create_user('upload@example.test','SafePassword!2026','upload')
    session,csrf=store.new_session(uid);app=create_app(store,origin='http://testserver')
    headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',session)
        response=client.post('/api/reports',headers=headers,files={'file':('payload.py',b'print("not executed")','application/octet-stream')})
        assert response.status_code in (413,422)
        for field in ('attachments','file','recipient','sender','html','command'):
            response=client.post('/api/reports',headers=headers,json={**report(),field:'untrusted'})
            assert response.status_code==422
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM report_delivery').fetchone()[0]==0
