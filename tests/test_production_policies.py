from fastapi.testclient import TestClient
from server.legal import build_legal_router,POLICY_VERSION
from fastapi import FastAPI

def test_production_policy_pages_and_downloads():
 app=FastAPI();app.include_router(build_legal_router())
 with TestClient(app) as c:
  for slug,title in [('terms','Terms of Service'),('privacy','Privacy Policy'),('acceptable-use','Acceptable Use Policy')]:
   page=c.get('/'+slug);assert page.status_code==200 and title in page.text
   assert 'private pre-launch software' not in page.text and 'provisional' not in page.text
   assert 'Download' in page.text and POLICY_VERSION in page.text
   for ext,contenttype in [('txt','text/plain'),('html','text/html')]:
    result=c.get('/'+slug+'.'+ext);assert result.status_code==200 and title in result.text
    assert result.headers['content-type'].startswith(contenttype)
    assert 'attachment;' in result.headers['content-disposition']
    if ext=='html':assert '<style>' in result.text and 'data-print-policy' not in result.text
  terms=c.get('/terms').text
  assert 'User responsibility' in terms and 'Indemnification' in terms and 'Limitation of liability' in terms
  assert 'to the extent permitted by applicable law' in terms
  assert 'Reporting copyright or abuse' not in c.get('/acceptable-use').text
  assert 'Send privacy questions or copyright notices to' not in c.get('/privacy').text
  assert 'poster' in terms and 'mandatory' in terms
  assert c.get('/terms.exe').status_code==404

def test_served_signup_form_matches_current_policy_and_cancellation_disclosure(tmp_path):
 from server.app import create_app
 from server.store import Store
 with TestClient(create_app(Store(tmp_path/'policy.db'),origin='http://testserver')) as client:
  form=client.get('/js/views/auth.js');assert form.status_code==200
  assert 'value="'+POLICY_VERSION+'"' in form.text
  assert 'cancellation takes effect immediately' in client.get('/terms').text
  assert 'Cancellation does not automatically issue a refund' in client.get('/terms').text
