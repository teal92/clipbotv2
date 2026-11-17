import sqlite3
import pytest
from server.store import Store
from server.operator import backup_database,restore_database,list_reports

def test_backup_restore_and_private_report_review(tmp_path):
    original=tmp_path/'original.db'
    store=Store(original)
    uid=store.create_user('owner@example.com','a-good-long-password','Owner')
    reference=store.save_report(uid,{'kind':'bug','title':'A real submitted issue','details':'Detailed information from a customer'})
    archive=tmp_path/'backup.db'
    backup_database(original,archive)
    with pytest.raises(FileExistsError):backup_database(original,archive)
    restored=tmp_path/'restored.db'
    restore_database(archive,restored)
    assert Store(restored).user(uid)['email']=='owner@example.com'
    assert list_reports(restored)[0]['reference']==reference
    with pytest.raises(FileExistsError):restore_database(archive,original)
    with pytest.raises(ValueError):list_reports(restored,limit=1000)

def test_invalid_backup_never_creates_destination(tmp_path):
    corrupt=tmp_path/'corrupt.db';corrupt.write_text('invalid database')
    target=tmp_path/'restore.db'
    with pytest.raises((ValueError,sqlite3.DatabaseError)):restore_database(corrupt,target)
    assert not target.exists()


def test_backup_cannot_enter_public_frontend(tmp_path):
    from server.operator import ROOT
    source=tmp_path/'private.db';Store(source)
    with pytest.raises(ValueError):backup_database(source,ROOT/'frontend'/'account-backup.db')
    assert not (ROOT/'frontend'/'account-backup.db').exists()


def test_private_test_account_requires_sandbox_and_never_grants_coverage(tmp_path,monkeypatch):
    from server.operator import create_test_account
    path=tmp_path/'existing.db';store=Store(path)
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_privateexample')
    monkeypatch.setenv('CLIPBOT_LOCAL_SIGNUP','0')
    monkeypatch.setenv('CLIPBOT_DEV_BYPASS','0')
    uid=create_test_account(path,'test@example.com','Tester','long-private-password','long-private-password')
    assert store.authenticate('test@example.com','long-private-password')==uid
    assert store.coverage(uid) is None
    with pytest.raises(ValueError):create_test_account(path,'test@example.com','Tester','long-private-password','long-private-password')
    with pytest.raises(ValueError):create_test_account(path,'another@example.com','Tester','short','short')
    with pytest.raises(ValueError):create_test_account(path,'another@example.com','Tester','long-private-password','mismatch')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_privateexample')
    with pytest.raises(ValueError):create_test_account(path,'another@example.com','Tester','long-private-password','long-private-password')

def test_private_account_does_not_create_wrong_database(tmp_path,monkeypatch):
    from server.operator import create_test_account
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_privateexample')
    path=tmp_path/'missing.db'
    with pytest.raises(FileNotFoundError):create_test_account(path,'test@example.com','Tester','long-private-password','long-private-password')
    assert not path.exists()
