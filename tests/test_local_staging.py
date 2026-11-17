from pathlib import Path
import pytest

def test_staging_drops_all_inherited_credentials_and_production_access(tmp_path):
    from ops.local_staging import staging_environment
    env=staging_environment(tmp_path,{'PATH':'safe-runtime','STRIPE_SECRET_KEY':'sk_live_private','STRIPE_LIVE_SECRET_KEY':'rk_live_private','ANTHROPIC_API_KEY':'private','CLIPBOT_ADMIN_USER_ID':'real-user','CLIPBOT_REPORT_SMTP_PASSWORD':'private','CLIPBOT_PUBLIC_SIGNUP':'1','CLIPBOT_CUSTOMER_ANALYSIS_ENABLED':'1'})
    assert env['PATH']=='safe-runtime'
    assert not any('private' in value or value=='real-user' for value in env.values())
    assert env['CLIPBOT_DB_PATH']==str(tmp_path.resolve()/'.staging'/'clipbot.db')
    assert env['CLIPBOT_BILLING_MODE']=='test' and env['CLIPBOT_LIVE_BILLING_ACCEPTED']=='false'
    assert env['CLIPBOT_CUSTOMER_ANALYSIS_ENABLED']=='0' and env['CLIPBOT_PUBLIC_SIGNUP']=='0'
    assert env['CLIPBOT_ORIGIN']=='http://127.0.0.1:8766'

def test_staging_has_no_external_bind_or_arbitrary_database_override(tmp_path):
    from ops.local_staging import staging_environment
    env=staging_environment(tmp_path,{'CLIPBOT_DB_PATH':'production.db','CLIPBOT_ORIGIN':'https://clipbot.your-domain.example','CLIPBOT_EDGE_SECRET':'private'})
    assert env['CLIPBOT_DB_PATH']!= 'production.db'
    assert not any('EDGE' in key for key in env)
