"""Real encrypted pool integration with a simulated game, no production probes."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
import load_scheduler as policy
from majsoul_client import GameError
from postgres_vault import VaultCorrupt,MAX_CIPHERTEXT_BYTES
from replay_admission import ReplayAdmission,ReplayLimited
from service_account import AccountPool
from test_replay_store import storage
from test_twenty_accounts import enroll
from test_service_account import URL,FIXTURE


def setup_pool(storage):
    db,make=storage
    with patch('test_twenty_accounts.vault',side_effect=lambda ignored:make().vault):accounts=enroll('unused')
    return db,make,accounts,lambda:AccountPool(accounts,clock=lambda:db.now,load_control=True)


def test_fair_rotation_restart_and_shrink_never_overloads_remaining_accounts(storage):
    db,make,accounts,new=setup_pool(storage);seen=[]
    for _ in range(40):
        new().fetch(URL,lambda u,s,a:seen.append(accounts.index(a)+1))
        db.now+=60
    assert seen==list(range(1,21))*2
    saved=make().vault.load();assert len(saved['usage']['load_scheduler']['accounts'])==20
    for row in saved['usage']['load_scheduler']['accounts'].values():assert row['history'][1]-row['history'][0]==1200
    # Five remaining accounts slow the whole service to 4 minutes per start.
    for a in accounts[5:]:a.cooldown_until=db.now+18000;a.save(a.session)
    pool=new();assert pool.operator_status()['scheduler']['interval_seconds']==240
    with pytest.raises(ReplayLimited) as waiting:pool.fetch(URL,lambda *_:pytest.fail('overloaded remaining accounts'))
    assert waiting.value.code=='ACCOUNT_LOAD_LIMITED'
    assert make().vault.load()['usage']['load_scheduler']==saved['usage']['load_scheduler']
    db.now+=180
    pool.fetch(URL,lambda *args:FIXTURE)


def test_short_long_limits_credit_recovery_and_preferred_slot_cannot_bypass(storage):
    db,make,accounts,new=setup_pool(storage)
    pool=new();pool.fetch(URL,lambda *args:FIXTURE,preferred_slot=1)
    state=make().vault.load();account=state['usage']['load_scheduler']['accounts']['1']
    account.update(history=[db.now-500,db.now-100],last=db.now-100,credits=3.,asof=db.now)
    make().vault.save(state)
    with pytest.raises(ReplayLimited):new().fetch(URL,lambda *_:pytest.fail('short cap bypass'),preferred_slot=1)
    state=make().vault.load();account=state['usage']['load_scheduler']['accounts']['1']
    account.update(history=[db.now-20000+i*500 for i in range(18)],last=db.now-11500,credits=3.)
    make().vault.save(state)
    with pytest.raises(ReplayLimited) as error:new().fetch(URL,lambda *_:pytest.fail('long cap bypass'),diagnostic_slot=1)
    assert error.value.retry_after>=1600
    # Read-only status does not replenish persistent credits or erase history.
    original=make().vault.load();new().operator_status();assert make().vault.load()==original


def test_540_holds_persist_penalty_and_comeback_is_single_credit(storage):
    db,make,accounts,new=setup_pool(storage)
    def fail(*args):raise GameError('fetch_record',540)
    with pytest.raises(GameError):new().fetch(URL,fail,preferred_slot=1)
    saved=make().vault.load();row=saved['usage']['load_scheduler']['accounts']['1']
    assert row['level']==1 and row['probation'] and row['credits']==0
    assert saved['rate_limit_until']==db.now+18000
    # Re-enrollment is not a credit/penalty reset.
    accounts[0].enroll(accounts[0].session)
    assert make().vault.load()['usage']['load_scheduler']==saved['usage']['load_scheduler']
    db.now+=18000
    new().fetch(URL,lambda *args:FIXTURE,preferred_slot=1)
    after=make().vault.load()['usage']['load_scheduler']['accounts']['1']
    assert after['level']==1 and not after['probation'] and after['credits']==0
    db.now+=400
    with pytest.raises(ReplayLimited) as waiting:new().fetch(URL,lambda *_:pytest.fail('post-rest burst'),preferred_slot=1)
    assert waiting.value.retry_after>=2000


def test_distinct_errors_slow_global_and_idle_time_alone_never_recovers(storage):
    db,make,accounts,new=setup_pool(storage)
    def fail(*args):raise GameError('fetch_record',540)
    with pytest.raises(GameError):new().fetch(URL,fail,preferred_slot=1)
    db.now+=100
    with pytest.raises(GameError):new().fetch(URL,fail,preferred_slot=2)
    value=make().vault.load()['usage']['load_scheduler'];assert value['level']==1
    assert new().operator_status()['scheduler']['interval_seconds']>120
    db.now+=7*3600
    assert new().operator_status()['scheduler']['global_slowdown_level']==1
    new().fetch(URL,lambda *args:FIXTURE,preferred_slot=3)
    assert make().vault.load()['usage']['load_scheduler']['level']==1


def test_concurrent_processes_claim_once_and_cache_does_not_spend_budget(storage):
    db,make,accounts,new=setup_pool(storage);calls=[]
    def run(_):
        try:return new().fetch(URL,lambda *args:calls.append(1) or FIXTURE)
        except ReplayLimited as error:return error.code
    with ThreadPoolExecutor(max_workers=4) as workers:results=list(workers.map(run,range(4)))
    assert len(calls)==1 and results.count('ACCOUNT_LOAD_LIMITED')==3
    admission=ReplayAdmission(durable=make(),clock=lambda:db.now)
    make().put('stored',FIXTURE);before=make().vault.load()
    assert admission.run('stored','visitor',lambda:pytest.fail('cache fetched upstream'))==(FIXTURE,'DURABLE_HIT')
    assert make().vault.load()==before


def test_success_and_failure_logs_are_bounded_under_full_twenty_account_load(storage):
    db,make,accounts,new=setup_pool(storage)
    for _ in range(400):
        new().fetch(URL,lambda *args:FIXTURE);db.now+=60
    saved=make().vault.load()
    assert len(db.ciphertext)<MAX_CIPHERTEXT_BYTES
    assert all(len(row['history'])<=18 for row in saved['usage']['load_scheduler']['accounts'].values())
    assert sum(a['total'][0] for a in saved['usage']['accounts'].values())==400
    assert new().operator_status()['scheduler']['interval_seconds']==60


def test_malformed_policy_fails_closed_and_backward_clock_cannot_refill():
    saved={};row=policy.account_state(saved,1,10000);row.update(credits=0,last=10000)
    assert policy.projected(row,9000)['credits']==0
    for mutation in [lambda v:v.update(level=True),lambda v:v.update(errors=[[1]]),lambda v:v['accounts']['1'].update(history=[0]*19)]:
        corrupted=copy.deepcopy(saved);mutation(corrupted['usage']['load_scheduler'])
        with pytest.raises(VaultCorrupt):policy.state(corrupted)


def test_slow_recovery_requires_time_and_real_success_counts():
    saved={};policy.account_state(saved,1,10000)
    policy.outcome(saved,1,10000,limited=True)
    value=policy.state(saved);value.update(level=1,successes=0)
    for n in range(59):policy.outcome(saved,1,10000+policy.RECOVERY_WINDOW,success=True)
    assert value['level']==1
    policy.outcome(saved,1,10000+policy.RECOVERY_WINDOW,success=True)
    assert value['level']==0
    assert value['accounts']['1']['level']==0


def test_selection_prefers_long_window_headroom_over_oldest_last_use():
    from types import SimpleNamespace
    owners=[SimpleNamespace(rate_limit_count=0,cooldown_until=0,unavailable_reason='',status=lambda:{'shared_ready':True}) for _ in range(2)]
    saved={};now=100000
    a=policy.account_state(saved,1,now);b=policy.account_state(saved,2,now)
    a.update(credits=3.,last=now-1000,history=[now-20000+i*500 for i in range(17)])
    b.update(credits=3.,last=now-500)
    chosen,wait,_,_=policy.plan(saved,owners,list(enumerate(owners)),now)
    assert chosen[0]==1 and wait==0


def test_queue_waits_for_budget_without_retrying_provider_or_charging_again(storage):
    from replay_admission import ReplayQueue
    from test_replay_queue import eventually
    import server
    db,make,accounts,new=setup_pool(storage)
    admission=ReplayAdmission(durable=make(),clock=lambda:db.now,global_per_minute=3,min_interval=20)
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=20)
    calls=[];start=db.now
    _,first,_=queue.submit('one','first',new().queued_fetch(URL,lambda *args:calls.append(db.now) or FIXTURE))
    eventually(lambda:queue.status(first['job'],'first')[0]==200)
    _,second,_=queue.submit('two','second',new().queued_fetch(URL,lambda *args:calls.append(db.now) or FIXTURE))
    with queue.condition:db.now=start+20;queue.condition.notify_all()
    eventually(lambda:queue.pause_until>=start+60 and queue.running is None)
    assert len(calls)==1
    assert sum(a['total'][0] for a in make().vault.load()['usage']['accounts'].values())==1
    for _ in range(20):assert queue.status(second['job'],'second')[0]==202
    with queue.condition:db.now=start+60;queue.condition.notify_all()
    eventually(lambda:queue.status(second['job'],'second')[0]==200)
    assert calls==[start,start+60]


def test_rest_expiry_does_not_prefer_penalized_account_over_healthy():
    from types import SimpleNamespace
    owners=[SimpleNamespace(rate_limit_count=0,cooldown_until=0,unavailable_reason='',status=lambda:{'shared_ready':True}) for _ in range(2)]
    saved={};now=100000
    a=policy.account_state(saved,1,now);b=policy.account_state(saved,2,now)
    a.update(level=1,probation=True,credits=1.,last=now-18000)
    b.update(credits=1.,last=now-1200,history=[now-1200])
    chosen,_,_,_=policy.plan(saved,owners,list(enumerate(owners)),now)
    assert chosen[0]==1
    owners[1].cooldown_until=now+3600
    chosen,_,_,_=policy.plan(saved,owners,[(0,owners[0])],now)
    assert chosen[0]==0
