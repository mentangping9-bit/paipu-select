import threading
import time
from contextlib import contextmanager

import pytest

from replay_admission import ReplayAdmission, ReplayLimited, ReplayQueue
from service_account import AccountPool, AccountsCooling, ServiceAccount, SlotVault
from server import Session, public_fetch_error
from majsoul_client import GameError


def eventually(predicate):
    deadline=time.monotonic()+2
    while not predicate():
        assert time.monotonic()<deadline
        threading.Event().wait(.002)


def advance(queue, now, value):
    with queue.condition:
        now[0]=value
        queue.condition.notify_all()


def test_ten_per_rolling_minute_fifo_and_status_never_calls_provider():
    now=[0.0];calls=[]
    queue=ReplayQueue(ReplayAdmission(clock=lambda:now[0]),public_fetch_error)
    tickets=[]
    for i in range(11):
        status,data,_=queue.submit(str(i),str(i),lambda i=i:(calls.append((i,now[0])) or {'log':[i]}))
        assert status==202
        tickets.append(data['job'])
    eventually(lambda:len(calls)==1)
    for i in range(1,10):
        advance(queue,now,i*6)
        eventually(lambda:len(calls)==i+1)
    for _ in range(50):
        status,data=queue.status(tickets[10],'10')
        assert status==202 and data['position']==1 and data['wait_seconds']==6
    assert len(calls)==10
    advance(queue,now,59)
    assert len(calls)==10
    advance(queue,now,60)
    eventually(lambda:queue.status(tickets[10],'10')[0]==200)
    assert [c[0] for c in calls]==list(range(11))
    for _,stamp in calls:
        assert sum(stamp-60<t<=stamp for _,t in calls)<=10
    assert queue.submit('10','new',lambda:pytest.fail('cache'))[2]=='HIT'


def test_queue_ownership_coalescing_overflow_and_expiry():
    entered,release=threading.Event(),threading.Event();calls=[];now=[0.0]
    queue=ReplayQueue(ReplayAdmission(clock=lambda:now[0]),public_fetch_error,spacing=0,max_pending=2,ttl=10)
    def fetch():
        calls.append('one');entered.set();assert release.wait(2);return {'log':[1]}
    _,first,_=queue.submit('one','a',fetch)
    assert entered.wait(1)
    _,same,_=queue.submit('one','b',fetch)
    assert queue.status(first['job'],'b')[0]==404
    _,second,_=queue.submit('two','c',lambda:{'log':[2]})
    assert queue.status(second['job'],'c')[1]['position']==1
    with pytest.raises(ReplayLimited,match='요청') as limited:
        queue.submit('three','d',lambda:{})
    assert limited.value.code=='REPLAY_QUEUE_FULL'
    with pytest.raises(ReplayLimited) as limited:
        queue.submit('different','a',lambda:{})
    assert limited.value.code=='REPLAY_ALREADY_QUEUED'
    release.set()
    eventually(lambda:queue.status(second['job'],'c')[0]==200)
    assert queue.status(same['job'],'b')==(200,{'log':[1]}) and calls==['one']
    advance(queue,now,10)
    assert queue.status(first['job'],'a')[0]==404


def test_540_pauses_whole_queue_and_retries_only_with_ready_backup():
    now=[0.0];calls=[]
    queue=ReplayQueue(ReplayAdmission(clock=lambda:now[0]),public_fetch_error,spacing=0)
    def fetch():
        calls.append(now[0])
        if len(calls)==1:
            error=GameError('fetch_record',540);error.can_retry=True;raise error
        return {'log':[1]}
    _,first,_=queue.submit('one','a',fetch)
    eventually(lambda:queue.pause_until==60)
    _,second,_=queue.submit('two','b',lambda:{'log':[2]})
    state=queue.status(first['job'],'a')[1]
    assert state['state']=='queued' and state['cooldown'] and state['wait_seconds']==60
    assert queue.status(second['job'],'b')[1]['position']==2
    advance(queue,now,59)
    assert calls==[0]
    advance(queue,now,60)
    eventually(lambda:queue.status(second['job'],'b')[0]==200)
    assert queue.status(first['job'],'a')[0]==200 and calls==[0,60]


class MemoryVault:
    storage='encrypted_postgres'
    def __init__(self):self.value=None;self.lock=threading.RLock()
    @contextmanager
    def locked(self):
        with self.lock:yield
    def load(self):return self.value
    def save(self,value):self.value=value


def accounts(vault):
    return [ServiceAccount(f'account{i}@example.com','kr',Session,SlotVault(vault,i)) for i in (1,2,3)]


def enroll(account):
    account.enroll(Session(0,0,email=account.email,uid=account.email,token='secret',device_id='device'))


def test_slots_preserve_primary_and_rotated_tokens_and_cooldown_on_restart():
    vault=MemoryVault();owners=accounts(vault)
    for owner in owners:enroll(owner)
    assert all(a.ready_session() for a in accounts(vault))
    owners[0].session.token='rotated';owners[0].save(owners[0].session)
    assert accounts(vault)[0].session.token=='rotated'
    assert all(a.session.token=='secret' for a in accounts(vault)[1:])
    now=[1000.0];pool=AccountPool(owners,clock=lambda:now[0]);seen=[]
    def limited(text,session,account):
        seen.append(account.email);raise GameError('fetch_record',540)
    with pytest.raises(GameError) as error:pool.fetch('replay',limited)
    assert error.value.can_retry and owners[0].cooldown_until==1600
    assert accounts(vault)[0].cooldown_until==1600
    for _ in range(2):
        with pytest.raises(GameError):pool.fetch('replay',limited)
    assert len(set(seen))==3
    with pytest.raises(AccountsCooling) as cooling:pool.fetch('replay',lambda *a:pytest.fail('paused'))
    assert cooling.value.retry_after==601
    assert 'example.com' not in str(pool.flags()) and 'secret' not in str(pool.flags())
    now[0]=1600
    assert pool.fetch('replay',lambda text,s,a:a.email)=='account1@example.com'


def test_persistent_540_is_bounded_and_pending_deadline_never_fetches():
    now=[0.0];calls=[]
    queue=ReplayQueue(ReplayAdmission(clock=lambda:now[0]),public_fetch_error,spacing=0)
    def fail():calls.append(1);raise GameError('fetch_record',540)
    _,job,_=queue.submit('limited','a',fail)
    eventually(lambda:len(calls)==1 and queue.running is None)
    for step in (60,120):
        advance(queue,now,step)
        eventually(lambda:len(calls)==step//60+1 and queue.running is None)
    status,error=queue.status(job['job'],'a')
    assert status==429 and error['server_code']==540 and len(calls)==3
    queue.pause_until=1000
    _,expired,_=queue.submit('expire','b',lambda:pytest.fail('expired request must not fetch'))
    advance(queue,now,1920)
    eventually(lambda:queue.status(expired['job'],'b')[0]==408)


def test_healthy_accounts_rotate_each_fetch_and_reauth_does_not_clear_540():
    vault=MemoryVault();owners=accounts(vault)
    for a in owners:enroll(a)
    now=[1000.0];pool=AccountPool(owners,clock=lambda:now[0]);seen=[]
    def ok(text,s,a):seen.append(a.email);return {'log':[]}
    for _ in range(3):pool.fetch('different replay',ok)
    assert seen==[a.email for a in owners]
    with pytest.raises(GameError):
        pool.fetch('limited',lambda *args:(_ for _ in ()).throw(GameError('fetch_record',540)))
    assert owners[0].rate_limit_count==1
    enroll(owners[0])
    assert owners[0].rate_limit_count==1 and owners[0].cooldown_until==1600
    now[0]=1601
    seen.clear()
    for _ in range(4):pool.fetch('different replay',ok)
    assert seen==[owners[1].email,owners[2].email]*2
    restored=AccountPool(accounts(vault),clock=lambda:now[0])
    assert restored.fetch('another',lambda t,s,a:a.email)==owners[1].email
    assert 'example.com' not in str(restored.flags())
    assert restored.operator_status()['accounts'][0]['email']==owners[0].email


def test_new_account_wakes_queue_without_shortening_shared_540_pause():
    now=[0.0];queue=ReplayQueue(ReplayAdmission(clock=lambda:now[0]),public_fetch_error)
    queue.pause_until=600;queue.provider_pause_until=60
    queue.account_available()
    assert queue.pause_until==60
    now[0]=70;queue.pause_until=600
    queue.account_available()
    assert queue.pause_until==70


def test_failed_game_account_is_skipped_and_secondary_profiles_survive():
    vault=MemoryVault();owners=accounts(vault)
    for a in owners:enroll(a)
    pool=AccountPool(owners)
    with pytest.raises(GameError) as error:
        pool.fetch('replay',lambda *args:(_ for _ in ()).throw(GameError('account_unbound',0)))
    assert error.value.can_retry
    assert owners[0].unavailable_reason=='account_unbound'
    assert accounts(vault)[0].unavailable_reason=='account_unbound'
    assert pool.fetch('replay',lambda t,s,a:a.email)==owners[1].email
