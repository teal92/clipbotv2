from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
import ssl
import pytest
from server.store import Store
from server.report_delivery import ReportDelivery
from server.account_recovery import AccountRecovery
from server.customer_access import CustomerAccess

CONFIG={'enabled':True,'sender':'robot@example.test','recipient':'owner@example.test','host':'smtp.example.test','port':465,'username':'synthetic','password':'synthetic-only'}
class SMTP:
 def __init__(self,*args,**kwargs):
  assert kwargs['context'].verify_mode==ssl.CERT_REQUIRED and kwargs['context'].check_hostname
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def login(self,*args):pass
 def send_message(self,message):return {}

def test_smtp_attempt_budget_is_shared_across_reports_recovery_and_verification(tmp_path,monkeypatch):
 monkeypatch.setattr('server.report_delivery.smtplib.SMTP_SSL',SMTP);monkeypatch.setenv('CLIPBOT_MAIL_DAILY_LIMIT','3')
 store=Store(tmp_path/'mail.db');services=[ReportDelivery(store,CONFIG),AccountRecovery(store,'https://example.test',CONFIG),CustomerAccess(store,'https://example.test',CONFIG)]
 message=EmailMessage();message.set_content('Synthetic test')
 for service in services:ReportDelivery._smtp(service,message)
 with pytest.raises(Exception,match='Email attempt limit'):ReportDelivery._smtp(ReportDelivery(store,CONFIG),message)

def test_parallel_smtp_attempts_cannot_exceed_the_shared_limit(tmp_path,monkeypatch):
 monkeypatch.setattr('server.report_delivery.smtplib.SMTP_SSL',SMTP);monkeypatch.setenv('CLIPBOT_MAIL_DAILY_LIMIT','5')
 store=Store(tmp_path/'mail.db');message=EmailMessage();message.set_content('Synthetic test')
 def send(_):
  try:ReportDelivery._smtp(ReportDelivery(store,CONFIG),message);return True
  except RuntimeError:return False
 with ThreadPoolExecutor(max_workers=8) as pool:admitted=list(pool.map(send,range(20)))
 assert sum(admitted)==5

@pytest.mark.parametrize('value',['999','-1','garbage'])
def test_unsafe_mail_budget_configuration_fails_before_network(tmp_path,monkeypatch,value):
 monkeypatch.setenv('CLIPBOT_MAIL_DAILY_LIMIT',value)
 def forbidden(*args,**kwargs):pytest.fail('Unsafe limit opened SMTP')
 monkeypatch.setattr('server.report_delivery.smtplib.SMTP_SSL',forbidden)
 with pytest.raises(RuntimeError):ReportDelivery._smtp(ReportDelivery(Store(tmp_path/'mail.db'),CONFIG),EmailMessage())
