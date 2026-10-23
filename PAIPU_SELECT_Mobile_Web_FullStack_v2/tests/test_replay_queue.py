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


def test_540_pauses_whole_queue_without_cascading_to_ready_backup():
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
    status,error=queue.status(first['job'],'a')
    assert status==429 and error['server_code']==540
    assert queue.status(second['job'],'b')[1]['position']==1
    advance(queue,now,59)
    assert calls==[0]
    advance(queue,now,60)
    eventually(lambda:queue.status(second['job'],'b')[0]==200)
    assert queue.status(first['job'],'a')[0]==429 and calls==[0]


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
    assert error.value.can_retry and owners[0].cooldown_until==19000
    assert accounts(vault)[0].cooldown_until==19000
    for _ in range(2):
        with pytest.raises(GameError):pool.fetch('replay',limited)
    assert len(set(seen))==3
    with pytest.raises(AccountsCooling) as cooling:pool.fetch('replay',lambda *a:pytest.fail('paused'))
    assert cooling.value.retry_after==18001
    assert 'example.com' not in str(pool.flags()) and 'secret' not in str(pool.flags())
    now[0]=19000
    assert pool.fetch('replay',lambda text,s,a:a.email)=='account1@example.com'


def test_persistent_540_is_bounded_and_pending_deadline_never_fetches():
    now=[0.0];calls=[]
    queue=ReplayQueue(ReplayAdmission(clock=lambda:now[0]),public_fetch_error,spacing=0)
    def fail():calls.append(1);raise GameError('fetch_record',540)
    _,job,_=queue.submit('limited','a',fail)
    eventually(lambda:len(calls)==1 and queue.running is None)
    for step in (60,120):
        advance(queue,now,step)
        assert len(calls)==1 and queue.running is None
    status,error=queue.status(job['job'],'a')
    assert status==429 and error['server_code']==540 and len(calls)==1
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
    assert owners[0].rate_limit_count==1 and owners[0].cooldown_until==19000
    now[0]=19001
    seen.clear()
    for _ in range(4):pool.fetch('different replay',ok)
    assert seen==[owners[1].email,owners[2].email,owners[0].email,owners[1].email]
    assert owners[0].rate_limit_count==0
    restored=AccountPool(accounts(vault),clock=lambda:now[0])
    assert restored.fetch('another',lambda t,s,a:a.email)==owners[2].email
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


def test_region_change_requires_new_auth_and_preserves_old_region_and_other_slots():
    vault=MemoryVault();owners=accounts(vault)
    for a in owners:enroll(a)
    owners[1].rate_limit_count=1;owners[1].cooldown_until=1600
    owners[1].save(owners[1].session)
    jp=ServiceAccount(owners[1].email,'jp',Session,SlotVault(vault,2,'jp'))
    assert jp.ready_session() is None and not jp.storage_error
    jp.enroll(Session(0,0,email=jp.email,region='jp',uid='jp-user',token='jp-secret',device_id='jp-device'))
    assert ServiceAccount(jp.email,'jp',Session,SlotVault(vault,2,'jp')).session.token=='jp-secret'
    kr=ServiceAccount(jp.email,'kr',Session,SlotVault(vault,2,'kr'))
    assert kr.session.token=='secret' and kr.cooldown_until==1600 and kr.rate_limit_count==1
    assert ServiceAccount(owners[0].email,'kr',Session,SlotVault(vault,1,'kr')).session.token=='secret'
    assert ServiceAccount(owners[2].email,'kr',Session,SlotVault(vault,3,'kr')).session.token=='secret'
    kr.session.token='kr-rotated';kr.save(kr.session)
    assert ServiceAccount(jp.email,'jp',Session,SlotVault(vault,2,'jp')).session.token=='jp-secret'


def test_nine_slots_preserve_existing_sessions_on_refresh_and_restore():
    vault=MemoryVault()
    owners=[ServiceAccount(f'account{i}@example.com','jp',Session,SlotVault(vault,i,'jp')) for i in range(1,10)]
    for account in owners:
        account.enroll(Session(0,0,email=account.email,region='jp',uid=account.email,
                              token='existing-token',device_id='device'))
    owners[8].session.token='rotated-nine'
    owners[8].save(owners[8].session)
    restored=[ServiceAccount(a.email,'jp',Session,SlotVault(vault,i,'jp')) for i,a in enumerate(owners,1)]
    assert [a.session.token for a in restored]==['existing-token']*8+['rotated-nine']
    pool=AccountPool(restored)
    assert pool.registration_account(9) is restored[8]
    with pytest.raises(ValueError):pool.registration_account(10)
    assert len(pool.flags()['shared_accounts'])==9


def nine_accounts():
    vault = MemoryVault()
    owners = [ServiceAccount(f'account{i}@example.com', 'jp', Session,
                             SlotVault(vault, i, 'jp')) for i in range(1, 10)]
    for a in owners:
        a.enroll(Session(0, 0, email=a.email, region='jp', uid=a.email,
                         token='retained-token', device_id='device'))
    return vault, owners


def restored_nine(vault):
    return [ServiceAccount(f'account{i}@example.com', 'jp', Session,
                           SlotVault(vault, i, 'jp')) for i in range(1, 10)]


def test_rotation_and_history_survive_a_restart_before_every_request():
    vault, owners = nine_accounts()
    seen = []
    for i in range(18):
        pool = AccountPool(restored_nine(vault), clock=lambda: 1000+i)
        status = pool.operator_status()
        assert status['next_slot'] == i%9+1
        assert status['last_used_slot'] == ((i-1)%9+1 if i else None)
        assert status['last_success_slot'] == status['last_used_slot']
        pool.fetch('replay', lambda t,s,a: seen.append(a.email))
    assert seen == [a.email for a in owners]*2
    # Updating primary tokens must preserve the shared cursor and history.
    owners[0].restore()
    owners[0].session.token = 'rotated-primary'
    owners[0].save(owners[0].session)
    assert AccountPool(restored_nine(vault)).operator_status()['next_slot'] == 1
    assert all(a.session.token == 'retained-token' for a in restored_nine(vault)[1:])


def test_legacy_success_history_advances_to_unused_eighth_and_ninth():
    vault, owners = nine_accounts()
    for i,a in enumerate(owners[:7]):
        a.last_success_at = 1000+i
        a.save(a.session)
    # Historical 540 counts do not mean a currently active restriction.
    owners[0].rate_limit_count = 2
    owners[0].cooldown_until = 1100
    owners[0].save(owners[0].session)
    for expected in [8,9,1]:
        pool = AccountPool(restored_nine(vault), clock=lambda: 2000)
        assert pool.operator_status()['next_slot'] == expected
        assert pool.fetch('replay',lambda t,s,a:a.email) == owners[expected-1].email


def test_another_process_cannot_reset_cursor_or_ignore_new_cooldowns():
    vault, owners = nine_accounts()
    first = AccountPool(owners, clock=lambda: 1000)
    stale = AccountPool(restored_nine(vault), clock=lambda: 1000)
    with pytest.raises(GameError):
        first.fetch('replay',lambda *args: (_ for _ in ()).throw(GameError('fetch_record',540)))
    # Even a process created before the failure reads the committed hold/cursor.
    assert stale.fetch('replay',lambda t,s,a:a.email) == owners[1].email
    assert stale.accounts[0].cooldown_until == 19000
    assert first.fetch('replay',lambda t,s,a:a.email) == owners[2].email
    reboot = AccountPool(restored_nine(vault), clock=lambda: 1000)
    assert reboot.operator_status()['next_slot'] == 4
    assert reboot.operator_status()['last_success_slot'] == 3


def test_claim_survives_failure_before_result_and_corrupt_cursor_fails_closed():
    from postgres_vault import VaultCorrupt
    vault, owners = nine_accounts()
    pool = AccountPool(owners)
    with pytest.raises(RuntimeError, match='stopped'):
        pool.fetch('replay',lambda *a: (_ for _ in ()).throw(RuntimeError('stopped')))
    reboot = AccountPool(restored_nine(vault))
    assert reboot.operator_status()['last_used_slot'] == 1
    assert reboot.operator_status()['last_success_slot'] is None
    assert reboot.operator_status()['next_slot'] == 2
    vault.value['rotation']['next_slot'] = 'private-invalid-value'
    with pytest.raises(VaultCorrupt):
        reboot.fetch('replay',lambda *a:pytest.fail('must not fetch'))


def test_nine_accounts_rotate_and_auth_failures_reach_ninth_without_exposing_error():
    _, owners = nine_accounts()
    now = [1000.0]
    pool = AccountPool(owners, clock=lambda: now[0])
    seen = []
    for _ in range(18):
        pool.fetch('replay', lambda t, s, a: seen.append(a.email) or {'log': []})
    assert seen == [a.email for a in owners]*2
    seen.clear()
    def fetch(t, s, a):
        seen.append(a.email)
        if a is not owners[-1]:
            raise GameError('oauth_auth', 110)
        return {'log': [9]}
    queue = ReplayQueue(ReplayAdmission(clock=lambda: now[0]), public_fetch_error,
                        spacing=6, max_account_attempts=9)
    _, ticket, _ = queue.submit('one', 'visitor', pool.queued_fetch('replay', fetch))
    eventually(lambda: len(seen) == 1 and queue.running is None)
    state = queue.status(ticket['job'], 'visitor')[1]
    assert state['retrying'] and state['waiting_count'] == 1 and state['processing_count'] == 0
    assert state['position'] == 1 and 'example.com' not in str(state)
    for attempt in range(2, 10):
        advance(queue, now, 1000+(attempt-1)*6)
        eventually(lambda: len(seen) == attempt and queue.running is None)
    assert queue.status(ticket['job'], 'visitor') == (200, {'log': [9]})
    assert seen == [a.email for a in owners]
    assert all(a.unavailable_reason == 'oauth_auth' for a in owners[:-1])
    assert pool.fetch('next', lambda t, s, a: a.email) == owners[-1].email


def test_sdk_rejections_and_timeouts_preserve_tokens_and_skip_each_slot_once():
    from paipu_vendor.mahjong_url_parser.sources.yostar import YostarApiError
    vault, owners = nine_accounts()
    now = [1000.0]
    pool = AccountPool(owners, clock=lambda: now[0])
    seen = []
    def fetch(t, s, a):
        seen.append(a.email)
        if a is owners[0]:
            raise YostarApiError(123456, 'provider detail must not be public')
        if a is owners[1]:
            raise TimeoutError()
        return {'log': [3]}
    attempt = pool.queued_fetch('replay', fetch)
    with pytest.raises(YostarApiError) as sdk:
        attempt()
    assert sdk.value.can_retry and sdk.value.retry_kind == 'account'
    assert owners[0].cooldown_until == 1300
    with pytest.raises(TimeoutError) as timeout:
        attempt()
    assert timeout.value.can_retry and owners[1].cooldown_until == 1060
    now[0] = 2000  # Earlier slots are healthy again, but already tried for this job.
    assert attempt() == {'log': [3]}
    assert seen == [a.email for a in owners[:3]]
    assert all(a.session.token == 'retained-token' for a in owners)
    restored = ServiceAccount(owners[0].email, 'jp', Session, SlotVault(vault, 1, 'jp'))
    assert restored.cooldown_until == 1300 and restored.session.token == 'retained-token'


def test_all_nine_sdk_failures_are_bounded_and_protocol_or_bad_replay_does_not_rotate():
    from paipu_vendor.mahjong_url_parser.sources.yostar import YostarApiError
    _, owners = nine_accounts()
    now = [1000.0]
    pool = AccountPool(owners, clock=lambda: now[0])
    queue = ReplayQueue(ReplayAdmission(clock=lambda: now[0]), public_fetch_error, spacing=6)
    seen = []
    def failed(t, s, a):
        seen.append(a.email)
        raise YostarApiError(999, 'hidden')
    _, ticket, _ = queue.submit('one', 'visitor', pool.queued_fetch('replay', failed))
    eventually(lambda: len(seen) == 1 and queue.running is None)
    for attempt in range(2, 10):
        advance(queue, now, 1000+(attempt-1)*6)
        eventually(lambda: len(seen) == attempt and queue.running is None)
    status, error = queue.status(ticket['job'], 'visitor')
    assert status == 502 and error['code'] == 'SDK_REFRESH_REJECTED'
    assert len(seen) == len(set(seen)) == 9
    assert 'hidden' not in str(error) and 'retained-token' not in str(error)
    now[0] = 2000
    for stage, code in [('oauth_login', 151), ('fetch_record', 404), ('conversion', 0)]:
        with pytest.raises(GameError) as caught:
            pool.fetch('bad', lambda *a: (_ for _ in ()).throw(GameError(stage, code)))
        assert not getattr(caught.value, 'can_retry', False)
    assert not any(a.unavailable_reason for a in owners)


def test_visible_queue_counts_and_position_track_actual_waiters():
    entered, release = threading.Event(), threading.Event()
    queue = ReplayQueue(ReplayAdmission(), public_fetch_error, spacing=0)
    def fetch():
        entered.set()
        assert release.wait(2)
        return {'log': [1]}
    try:
        _, first, _ = queue.submit('one', 'a', fetch)
        assert entered.wait(1)
        _, second, _ = queue.submit('two', 'b', lambda: {'log': [2]})
        _, third, _ = queue.submit('three', 'c', lambda: {'log': [3]})
        own = queue.status(first['job'], 'a')[1]
        assert own['state'] == 'processing' and own['processing_count'] == 1
        for ticket, visitor, position in [(second, 'b', 1), (third, 'c', 2)]:
            state = queue.status(ticket['job'], visitor)[1]
            assert state['position'] == position and state['waiting_count'] == 2
            assert state['processing_count'] == 1 and not state['retrying']
            assert queue.status(ticket['job'], 'unrelated')[0] == 404
    finally:
        release.set()
    eventually(lambda: queue.status(third['job'], 'c')[0] == 200)
