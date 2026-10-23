"""Durable counter semantics using the real encryption/locking code and a fake DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json

from cryptography.fernet import Fernet
import pytest

import account_usage
import server
from majsoul_client import GameError
from service_account import AccountPool, ServiceAccount, SlotVault
from test_postgres_vault import database, vault
from test_service_account import session


def owners(key):
    return [ServiceAccount(f'account{i}@example.com','kr',server.Session,
                           SlotVault(vault(key),i,'kr')) for i in range(1,10)]


def enrolled():
    key = Fernet.generate_key().decode()
    accounts = owners(key)
    for a in accounts:
        a.enroll(session(a.email))
    return key, accounts


def test_counts_survive_restart_token_refresh_and_failed_account_retry(database):
    key, accounts = enrolled()
    pool = AccountPool(accounts, clock=lambda: 1792710000)
    tried = set()
    with pytest.raises(GameError):
        pool.fetch('replay', lambda *args: (_ for _ in ()).throw(GameError('fetch_record',540)), tried=tried)
    pool.fetch('replay', lambda *args: 'ok', tried=tried)
    # Primary enrollment and a region switch must preserve the shared usage.
    accounts[0].enroll(session(accounts[0].email))
    jp = ServiceAccount(accounts[0].email,'jp',server.Session,SlotVault(vault(key),1,'jp'))
    s = session(jp.email); s.region='jp'; jp.enroll(s)
    accounts[0].enroll(session(accounts[0].email))
    reboot = AccountPool(owners(key), clock=lambda:1792710001)
    status = reboot.operator_status()
    assert status['usage_persistent'] and status['usage_timezone']=='Asia/Seoul'
    assert status['usage_started_at']==1792710000
    assert status['accounts'][0]['usage']['total']=={'attempts':1,'successes':0,'failures':1}
    assert status['accounts'][0]['usage']['last_error_code']==540
    assert status['accounts'][1]['usage']['total']=={'attempts':1,'successes':1,'failures':0}
    assert status['accounts'][2]['usage']['total']=={'attempts':0,'successes':0,'failures':0}
    assert all(a['usage']['unfinished']==0 for a in status['accounts'])
    assert 'private-token' not in json.dumps(status) and 'private-uid' not in json.dumps(status)
    assert not any('usage' in a for a in reboot.flags()['shared_accounts'])
    assert len(database.ciphertext)<16384


def test_kst_day_rollover_including_in_flight_attempt(database):
    key, accounts = enrolled()
    before = datetime(2026,10,23,23,59,59,tzinfo=account_usage.KST).timestamp()
    now=[before]
    pool=AccountPool(accounts,clock=lambda:now[0])
    def crossing_midnight(*args):
        now[0]+=2
        return 'ok'
    pool.fetch('replay',crossing_midnight)
    status=AccountPool(owners(key),clock=lambda:now[0]).operator_status()
    assert status['usage_day']=='2026-10-24'
    assert status['accounts'][0]['usage']['today']=={'attempts':0,'successes':1,'failures':0}
    assert status['accounts'][0]['usage']['total']=={'attempts':1,'successes':1,'failures':0}
    tomorrow=AccountPool(owners(key),clock=lambda:now[0]+86400).operator_status()
    assert tomorrow['accounts'][0]['usage']['today']=={'attempts':0,'successes':0,'failures':0}
    assert tomorrow['accounts'][0]['usage']['total']['attempts']==1


def test_overlapping_deployments_do_not_lose_increments(database):
    key, accounts = enrolled()
    first=AccountPool(accounts)
    second=AccountPool(owners(key))
    def retrieve(i):
        return [first,second][i%2].fetch('replay',lambda *args:'ok')
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(retrieve,range(36)))==['ok']*36
    stats=AccountPool(owners(key)).operator_status()['accounts']
    assert all(a['usage']['total']=={'attempts':4,'successes':4,'failures':0} for a in stats)


def test_interrupted_attempt_is_not_reported_as_success_or_failure(database):
    key, accounts=enrolled()
    root=accounts[0].vault.vault
    with root.locked():
        saved=root.load()
        account_usage.record(saved,1,'attempt',1792710000)
        root.save(saved)
    usage=AccountPool(owners(key)).operator_status()['accounts'][0]['usage']
    assert usage['unfinished']==1
    assert usage['total']=={'attempts':1,'successes':0,'failures':0}


def test_no_authentication_or_status_polling_counted_and_bounded_payload(database):
    key, accounts=enrolled()
    pool=AccountPool(accounts)
    assert pool.operator_status()['usage_started_at'] is None
    for _ in range(3):
        pool.operator_status();pool.flags()
    saved=accounts[0].vault.vault.load()
    for day in range(1000):
        for slot in range(1,10):
            now=1792710000+day*86400
            account_usage.record(saved,slot,'attempt',now)
            account_usage.record(saved,slot,'failure',now,540)
    root=accounts[0].vault.vault
    root.save(saved)
    assert len(database.ciphertext)<16384
    assert len(saved['usage']['accounts'])==9
    assert saved['usage']['accounts']['9']['total']==[1000,0,1000]
    assert 'private-token' not in database.ciphertext
