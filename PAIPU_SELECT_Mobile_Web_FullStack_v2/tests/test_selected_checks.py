"""At-most-once checks honor holds, pacing and account budgets."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
import server
from replay_checks import run,AlreadyChecked
from replay_admission import ReplayAdmission
from service_account import AccountPool
from majsoul_client import GameError
from test_replay_store import storage
from test_twenty_accounts import enroll
from test_service_account import URL,FIXTURE


def setup(storage):
    db,make=storage
    with patch('test_twenty_accounts.vault',side_effect=lambda ignored:make().vault):accounts=enroll('unused')
    return db,make,accounts,lambda:AccountPool(accounts,clock=lambda:db.now,load_control=True)


def test_five_selected_accounts_once_across_restart_errors_and_pacing(storage,capsys):
    db,make,accounts,pool=setup(storage);calls=[]
    def fetch(url,s,a):
        slot=accounts.index(a)+1;calls.append((slot,db.now))
        if slot in (1,3):raise GameError('fetch_record',540)
        return FIXTURE
    def sleep(seconds):db.now+=seconds
    def check():
        run(pool(),ReplayAdmission(durable=make(),clock=lambda:db.now,global_per_minute=3,min_interval=20),server.extract_share_url,fetch,
            revision='requested-five',url=URL,slots='1,2,3,8,9',sleep=sleep)
    check();check()
    assert [s for s,t in calls]==[1,2,3,8,9]
    assert all(b[1]-a[1]>=60 for a,b in zip(calls,calls[1:]))
    rows=make().vault.load()['usage']['replay_check_runs']['requested-five']['slots']
    assert set(rows)=={'1','2','3','8','9'}
    assert rows['1']['code']==540 and rows['3']['code']==540
    assert all(rows[str(i)]['state']=='success' for i in (2,8,9))
    assert rows['2']['rounds']==10
    output=capsys.readouterr().out
    assert 'test-token' not in output and 'example.com' not in output and URL not in output


def test_holds_and_global_stop_never_bypassed(storage):
    db,make,accounts,pool=setup(storage)
    accounts[0].cooldown_until=accounts[0].rate_limit_until=db.now+18000;accounts[0].rate_limit_count=1;accounts[0].save(accounts[0].session)
    saved=make().vault.load();saved.setdefault('usage',{'version':1,'accounts':{}})['admission']={'marks':[],'pause_until':0,'circuit_until':db.now+18000}
    make().vault.save(saved)
    run(pool(),ReplayAdmission(durable=make(),clock=lambda:db.now),server.extract_share_url,
        lambda *_:pytest.fail('hold bypass'),revision='protected',url=URL,slots='1,2',sleep=lambda _:pytest.fail('global stop should not poll'))
    assert 'replay_check_runs' not in make().vault.load()['usage']


def test_private_check_revision_is_atomic_with_budget_claim(storage):
    db,make,accounts,pool=setup(storage);calls=[]
    def attempt(_):
        try:pool().fetch(URL,lambda *a:calls.append(1) or FIXTURE,diagnostic_slot=1,check_revision='same')
        except Exception as error:return type(error).__name__
    with ThreadPoolExecutor(max_workers=2) as workers:list(workers.map(attempt,range(2)))
    assert calls==[1]
    db.now+=2400
    with pytest.raises(AlreadyChecked):pool().fetch(URL,lambda *_:pytest.fail('duplicate check'),diagnostic_slot=1,check_revision='same')
    assert make().vault.load()['usage']['accounts']['1']['total'][0]==1


@pytest.mark.parametrize('slots',['1,1','0','21','1,2,3,4,5,6','1, 2'])
def test_invalid_selection_never_calls_provider(storage,slots):
    db,make,accounts,pool=setup(storage)
    run(pool(),ReplayAdmission(),server.extract_share_url,lambda *_:pytest.fail('invalid selection'),revision='bad',url=URL,slots=slots)
    assert 'replay_check_runs' not in make().vault.load().get('usage',{})
