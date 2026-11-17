import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import pytest
from server.store import Store

def moment(y,m,d):return datetime(y,m,d,12,30,tzinfo=timezone.utc).timestamp()

def test_first_claim_becomes_display_name_and_unchanged_preserves_timestamp(tmp_path,monkeypatch):
    store=Store(tmp_path/'names.db');uid=store.create_user('one@example.com','long-password-123','Legacy Name')
    assert store.user(uid)['username']=='Legacy Name'
    monkeypatch.setattr('server.store.time.time',lambda:moment(2026,8,31))
    store.update_profile(uid,'first_name');user=store.user(uid)
    assert user['name']==user['username']=='first_name'
    assert user['usernameChangedAt']==moment(2026,8,31)
    assert user['usernameChangeAvailableAt']==moment(2027,2,28)
    monkeypatch.setattr('server.store.time.time',lambda:moment(2026,9,1))
    store.update_profile(uid,'FIRST_NAME')
    assert store.user(uid)['usernameChangedAt']==moment(2026,8,31)

def test_six_calendar_months_reject_before_exact_boundary_allow_on_it(tmp_path,monkeypatch):
    from server.store import UsernameChangeUnavailable
    store=Store(tmp_path/'months.db');uid=store.create_user('one@example.com','long-password-123','Legacy')
    monkeypatch.setattr('server.store.time.time',lambda:moment(2026,8,31));store.update_profile(uid,'first_name')
    monkeypatch.setattr('server.store.time.time',lambda:moment(2027,2,28)-1)
    with pytest.raises(UsernameChangeUnavailable):store.update_profile(uid,'second_name')
    monkeypatch.setattr('server.store.time.time',lambda:moment(2027,2,28));store.update_profile(uid,'second_name')
    assert store.user(uid)['username']=='second_name'
    assert store.user(uid)['usernameChangeAvailableAt']==moment(2027,8,28)

def test_legacy_reservations_and_profile_uniqueness_are_case_insensitive(tmp_path):
    import sqlite3
    store=Store(tmp_path/'unique.db');a=store.create_user('a@example.com','long-password-123','Reserved');b=store.create_user('b@example.com','long-password-123','Other')
    with pytest.raises(sqlite3.IntegrityError):store.update_profile(b,'RESERVED')
    store.update_profile(a,'reserved')
    with pytest.raises(sqlite3.IntegrityError):store.update_profile(b,'Reserved')
    assert store.user(b)['name']=='Other'

def test_racing_claims_have_one_winner_and_no_partial_names(tmp_path):
    import sqlite3
    store=Store(tmp_path/'race.db');users=[store.create_user(str(i)+'@example.com','long-password-123','Legacy '+str(i)) for i in range(2)]
    def claim(uid):
        try:store.update_profile(uid,'same_name');return True
        except sqlite3.IntegrityError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,users))
    assert sum(results)==1
    assert sum(store.user(uid)['name']=='same_name' for uid in users)==1

def test_existing_profile_migrates_without_invented_change_date(tmp_path):
    import sqlite3
    path=tmp_path/'old.db'
    db=sqlite3.connect(path);db.execute("CREATE TABLE user_profiles(user_id TEXT PRIMARY KEY,username TEXT COLLATE NOCASE UNIQUE,avatar TEXT NOT NULL DEFAULT '')");db.commit();db.close()
    store=Store(path);uid=store.create_user('a@example.com','long-password-123','Legacy');store.update_avatar(uid,'')
    assert store.user(uid)['usernameChangedAt'] is None
    store.update_profile(uid,'new_name');assert store.user(uid)['usernameChangedAt'] is not None

def test_calendar_calculation_clamps_leap_month_and_keeps_utc_time():
    from server.store import username_change_available_at
    assert username_change_available_at(moment(2027,8,31))==moment(2028,2,29)
    assert username_change_available_at(moment(2028,2,29))==moment(2028,8,29)
    assert username_change_available_at(moment(2026,1,31))==moment(2026,7,31)
