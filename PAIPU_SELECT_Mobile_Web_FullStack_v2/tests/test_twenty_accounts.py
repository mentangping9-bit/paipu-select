"""20-slot persistence and bounded operator diagnostic; providers are stubbed."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request
from unittest.mock import patch

from cryptography.fernet import Fernet
import pytest

import server
from majsoul_client import GameError
from postgres_vault import MAX_CIPHERTEXT_BYTES, VaultUnavailable
from replay_admission import ReplayAdmission, ReplayQueue
from replay_diagnostic import diagnose_replay
from service_account import AccountPool, ServiceAccount, SlotVault, AccountsCooling
from test_postgres_vault import database, vault
from test_service_account import session, URL, FIXTURE


def owners(key):
    return [ServiceAccount(f'account{i}@example.com','jp',server.Session,
                           SlotVault(vault(key),i,'jp')) for i in range(1,21)]


def enroll(key):
    accounts=owners(key)
    for a in accounts:
        s=session(a.email);s.region='jp';s.token='test-token-'+('x'*512)
        a.enroll(s)
    return accounts


def test_twenty_slots_rotate_across_restart_and_preserve_primary_refresh(database):
    key=Fernet.generate_key().decode()
    accounts=enroll(key)
    for i in range(20):
        pool=AccountPool(owners(key),clock=lambda:1792710000+i)
        pool.fetch(URL,lambda url,s,a:a.email)
        assert pool.last_success_slot==i+1
    # Include a large realistic token and operator statistics, beyond the old
    # 16 KiB bound. Reload the actual Fernet ciphertext, not an in-memory alias.
    assert 16384<len(database.ciphertext)<MAX_CIPHERTEXT_BYTES
    assert accounts[0].enroll(session(accounts[0].email)) is False  # JP binding rejects KR.
    s=session(accounts[0].email);s.region='jp';accounts[0].enroll(s)
    status=AccountPool(owners(key),clock=lambda:1792710021).operator_status()
    assert status['next_slot']==1 and status['last_success_slot']==20
    assert len(status['accounts'])==20
    assert all(a['usage']['total']=={'attempts':1,'successes':1,'failures':0} for a in status['accounts'])
    assert owners(key)[19].session.token.startswith('test-token-')
    assert 'test-token-' not in json.dumps(status)
    assert ReplayQueue(ReplayAdmission(),server.public_fetch_error,max_account_attempts=20).max_account_attempts==20
    store=vault(key)
    with pytest.raises(VaultUnavailable):
        store.save({'version':1,'oversized':'x'*MAX_CIPHERTEXT_BYTES})
    assert len(AccountPool(owners(key)).flags()['shared_accounts'])==20


def test_one_shot_diagnostic_never_repeats_on_restart_and_keeps_other_holds(database,capsys):
    key=Fernet.generate_key().decode();accounts=enroll(key)
    for a in accounts:
        a.cooldown_until=1792715000;a.rate_limit_count=3;a.save(a.session)
    # Private diagnostics also respect holds; use exactly one eligible slot.
    accounts[0].cooldown_until=0;accounts[0].rate_limit_count=0;accounts[0].save(accounts[0].session)
    calls=[]
    def fail(url,s,a):
        calls.append(a.email)
        raise GameError('fetch_record',540)
    def run(_):
        diagnose_replay(AccountPool(owners(key),clock=lambda:1792710000),ReplayAdmission(),
            server.extract_share_url,fail,revision='incident-once',url=URL)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(run,range(2)))
    run(0)
    assert len(calls)==1
    reboot=AccountPool(owners(key),clock=lambda:1792710000)
    assert reboot.accounts[0].rate_limit_count==1
    assert all(a.rate_limit_count==3 and a.cooldown_until==1792715000 for a in reboot.accounts[1:])
    with pytest.raises(AccountsCooling):
        reboot.fetch(URL,fail)
    output=capsys.readouterr().out
    assert 'fetch_record 540' in output
    assert 'test-token' not in output and 'example.com' not in output
    assert URL not in output
    assert sum(a['usage']['total']['attempts'] for a in reboot.operator_status()['accounts'])==1


def test_direct_http_returns_result_or_cooldown_without_jobs_and_keeps_limits(database):
    key=Fernet.generate_key().decode();accounts=enroll(key)
    pool=AccountPool(accounts)
    admission=ReplayAdmission(queue_timeout=0)
    queue=ReplayQueue(admission,server.public_fetch_error)
    api=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    worker=threading.Thread(target=api.serve_forever,daemon=True);worker.start()
    def post(value):
        req=urllib.request.Request(f'http://127.0.0.1:{api.server_port}/api/convert',
            data=json.dumps(value).encode(),headers={'Content-Type':'application/json'})
        try:
            response=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            response=e
        return response.status,json.load(response)
    try:
        with patch.object(server,'service_pool',pool),patch.object(server,'service_account',accounts[0]),patch.object(server,'replay_admission',admission),patch.object(server,'replay_queue',queue),patch.object(server,'REPLAY_QUEUE_ENABLED',False),patch.object(server,'fetch_from_mahjongsoul',return_value=FIXTURE) as fetch:
            status,result=post({'url':URL})
            assert status==200 and len(result['log'])==10 and 'job' not in result
            assert fetch.call_count==1 and not queue.jobs and queue.thread is None
            assert post({'url':URL})[0]==200 and fetch.call_count==1
            admission.cache.clear();admission.cached_bytes=0
            for a in accounts:
                a.cooldown_until=pool.clock()+3600;a.save(a.session)
            # A public caller cannot enable the private diagnostic bypass.
            status,result=post({'url':URL,'diagnostic_slot':1})
            assert status==429 and result['code']=='UPSTREAM_REPLAY_LIMITED'
            assert 'job' not in result and fetch.call_count==1
            admission.upstream_marks.extend([admission.clock()]*10)
            assert post({'url':URL})[1]['code']=='SERVICE_RATE_LIMITED'
            admission.upstream_marks.clear();admission.worker.acquire()
            try:
                assert post({'url':URL})[1]['code']=='REPLAY_BUSY'
            finally:
                admission.worker.release()
    finally:
        api.shutdown();worker.join();api.server_close()
