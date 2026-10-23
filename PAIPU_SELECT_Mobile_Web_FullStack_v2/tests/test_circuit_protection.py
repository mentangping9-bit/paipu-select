"""17/20 active 540 holds, five-hour persistence and cache-first queue behavior."""
import threading
import json
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import pytest
from majsoul_client import GameError
from replay_admission import ReplayAdmission, ReplayLimited, ReplayQueue
from replay_policy import ACCOUNT_REST, CIRCUIT_REST, CONGESTION_MESSAGE
from service_account import AccountPool
import server
from test_replay_store import storage
from test_twenty_accounts import enroll
from test_replay_queue import eventually,advance
from test_service_account import URL,FIXTURE
from paipu_vendor.mahjong_url_parser.urls import parse_replay_url


def seed(storage,count=16):
    db,make=storage
    # Use real encrypted SlotVault writes, without production credentials.
    with patch('test_twenty_accounts.vault',side_effect=lambda ignored:make().vault):
        accounts=enroll('unused')
    for account in accounts[:count]:
        account.rate_limit_count=1
        account.rate_limit_until=account.cooldown_until=db.now+ACCOUNT_REST
        account.save(account.session)
    return db,make,accounts


def test_sixteen_do_not_trip_seventeenth_trips_and_survives_restart_and_reauth(storage):
    db,make,accounts=seed(storage)
    assert make().policy()['locked_accounts']==16 and not make().policy()['paused']
    pool=AccountPool(accounts,clock=lambda:db.now)
    admission=ReplayAdmission(durable=make(),global_per_minute=3,min_interval=20,clock=lambda:db.now)
    def fail(*args):raise GameError('fetch_record',540)
    with pytest.raises(GameError) as failed:
        admission.run('new','visitor',lambda:pool.fetch('url',fail))
    assert failed.value.account_slot==17 and failed.value.circuit_open
    assert make().policy()['locked_accounts']==17
    deadline=make().policy()['circuit_until']
    assert deadline==db.now+CIRCUIT_REST
    # A different process and re-enrollment must not reset/extend the deadline.
    accounts[0].enroll(accounts[0].session)
    db.now+=30
    new=ReplayAdmission(durable=make(),global_per_minute=3,min_interval=20,clock=lambda:db.now)
    with pytest.raises(ReplayLimited) as blocked:
        new.run('another','another',lambda:pytest.fail('provider called during global pause'))
    assert blocked.value.code=='SERVER_CONGESTED'
    assert make().policy()['circuit_until']==deadline
    db.now=deadline
    assert not make().policy()['paused'] and make().policy()['locked_accounts']==0
    assert new.run('after','after',lambda:{'log':[[1]]})[1]=='MISS'


def test_expired_540_and_non_540_holds_are_not_counted(storage):
    db,make,accounts=seed(storage,16)
    # Only 15 remain active; a network pause is not a 540 hold.
    accounts[0].rate_limit_until=db.now-1;accounts[0].save(accounts[0].session)
    accounts[16].cooldown_until=db.now+ACCOUNT_REST;accounts[16].save(accounts[16].session)
    assert make().policy()['locked_accounts']==15 and not make().policy()['paused']
    db.now+=ACCOUNT_REST
    assert make().policy()['locked_accounts']==0


def test_circuit_terminates_pending_jobs_and_still_serves_durable_cache(storage):
    db,make,accounts=seed(storage)
    make().put('cached',{'log':[[1]]})
    pool=AccountPool(accounts,clock=lambda:db.now)
    admission=ReplayAdmission(durable=make(),global_per_minute=3,min_interval=20,clock=lambda:db.now)
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=20)
    entered,release=threading.Event(),threading.Event();calls=[]
    def fail(*args):
        calls.append(1);entered.set();assert release.wait(2)
        raise GameError('fetch_record',540)
    _,one,_=queue.submit('new','a',lambda:pool.fetch('url',fail))
    assert entered.wait(1)
    _,two,_=queue.submit('pending','b',lambda:pytest.fail('pending job called provider'))
    release.set()
    eventually(lambda:queue.status(one['job'],'a')[0]==503)
    for ticket,visitor in ((one,'a'),(two,'b')):
        status,error=queue.status(ticket['job'],visitor)
        assert status==503 and error['code']=='SERVER_CONGESTED'
        assert error['error']==CONGESTION_MESSAGE and error['retry_after']==18000
    assert calls==[1] and not queue.pending
    assert queue.submit('cached','c',lambda:pytest.fail('cached replay called provider'))[2]=='DURABLE_HIT'
    with pytest.raises(ReplayLimited) as blocked:
        queue.submit('uncached','d',lambda:pytest.fail('new job admitted during pause'))
    assert blocked.value.code=='SERVER_CONGESTED'


def test_production_spacing_and_rolling_cap_survive_new_instances(storage):
    db,make=storage
    make().claim()
    db.now+=19
    with pytest.raises(ReplayLimited) as blocked:make().claim()
    assert blocked.value.retry_after==1
    db.now+=1;make().claim()
    db.now+=20;make().claim()
    db.now+=19
    with pytest.raises(ReplayLimited):make().claim()
    db.now+=1;make().claim()
    assert len(make().vault.load()['usage']['admission']['marks'])==3


def test_http_paused_notice_and_cached_conversion_with_no_provider_calls(storage):
    db,make,accounts=seed(storage,17)
    make().put(('international',parse_replay_url(URL).replay_id),FIXTURE)
    pool=AccountPool(accounts,clock=lambda:db.now)
    admission=ReplayAdmission(durable=make(),global_per_minute=3,min_interval=20,clock=lambda:db.now)
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=20)
    api=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=api.serve_forever,daemon=True);thread.start()
    def post(url):
        request=urllib.request.Request(f'http://127.0.0.1:{api.server_port}/api/convert',
            data=json.dumps({'url':url}).encode(),headers={'Content-Type':'application/json'})
        try:response=urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:response=error
        return response.status,json.load(response)
    try:
        with patch.object(server,'service_pool',pool),patch.object(server,'service_account',accounts[0]),\
             patch.object(server,'replay_admission',admission),patch.object(server,'replay_queue',queue),\
             patch.object(server,'REPLAY_QUEUE_ENABLED',True),patch.object(server,'fetch_from_mahjongsoul') as provider:
            different=URL.replace('ed6ff58a','ed6ff58b')
            status,error=post(different)
            assert status==503 and error['code']=='SERVER_CONGESTED' and error['error']==CONGESTION_MESSAGE
            assert error['retry_after']==18000 and error['retry_at']>0
            status,result=post(URL)
            assert status==200 and len(result['log'])==10
            assert not queue.jobs
            provider.assert_not_called()
    finally:api.shutdown();api.server_close();thread.join(timeout=2)


def test_legacy_540_hold_uses_failure_time_and_reauth_preserves_it(storage):
    db,make,accounts=seed(storage,0)
    saved=make().vault.load()
    saved.update(rate_limit_count=3,cooldown_until=db.now+600,last_success_at=db.now-7200)
    saved.pop('rate_limit_until',None)
    saved.setdefault('usage',{'version':1,'started_at':db.now,'accounts':{}})['accounts']['1']={
        'total':[1,0,1],'last_failure_at':db.now-3600,'last_error_code':540}
    make().vault.save(saved)
    restored=AccountPool(accounts,clock=lambda:db.now)
    restored._restore_rotation(make().vault.load())
    expected=db.now-3600+ACCOUNT_REST
    assert restored.accounts[0].rate_limit_until==expected
    restored.accounts[0].enroll(restored.accounts[0].session)
    assert make().vault.load()['rate_limit_until']==expected
    assert make().policy()['locked_accounts']==1


def test_production_queue_starts_three_per_minute_in_fifo_order():
    now=[0.0];calls=[]
    admission=ReplayAdmission(clock=lambda:now[0],global_per_minute=3,min_interval=20)
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=20,max_pending=30,max_wait=600)
    tickets=[]
    for i in range(4):
        _,ticket,_=queue.submit(str(i),str(i),lambda i=i:(calls.append((i,now[0])) or {'log':[[i]]}))
        tickets.append(ticket)
    eventually(lambda:len(calls)==1)
    for stamp,count in ((20,2),(40,3)):
        advance(queue,now,stamp);eventually(lambda:len(calls)==count)
    advance(queue,now,59)
    assert len(calls)==3
    advance(queue,now,60)
    eventually(lambda:queue.status(tickets[3]['job'],'3')[0]==200)
    assert calls==[(0,0),(1,20),(2,40),(3,60)]


def test_new_queue_submission_does_not_wait_for_authentication_lock(storage):
    db,make=storage
    admission=ReplayAdmission(durable=make(),global_per_minute=3,min_interval=20,clock=lambda:db.now)
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=20)
    entered,release=threading.Event(),threading.Event()
    def slow():
        with make().vault.locked():
            entered.set();assert release.wait(2)
        return {'log':[[1]]}
    _,first,_=queue.submit('slow','a',slow)
    assert entered.wait(1)
    status,second,_=queue.submit('second','b',lambda:{'log':[[2]]})
    assert status==202 and second['position']==1
    release.set()
    eventually(lambda:queue.status(first['job'],'a')[0]==200)
    db.now+=20
    with queue.condition:queue.condition.notify_all()
    eventually(lambda:queue.status(second['job'],'b')[0]==200)
