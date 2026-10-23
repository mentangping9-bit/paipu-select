"""Encrypted cache/admission across independent server instances; simulated SQL."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from cryptography.fernet import Fernet
import pytest

from majsoul_client import GameError
from postgres_vault import VaultUnavailable
from replay_admission import ReplayAdmission, ReplayLimited
from replay_store import ReplayStore
from test_postgres_vault import SimulatedDatabase, vault


class CacheDatabase(SimulatedDatabase):
    def __init__(self):
        super().__init__()
        self.now=1792700000.0
        self.cache={}

    def connect(self, **settings):
        connection=super().connect(**settings)
        execute=connection.execute
        db=self
        class Rows:
            def __init__(self, rows):self.rows=rows
            def fetchone(self):return self.rows[0] if self.rows else None
            def fetchall(self):return self.rows
        def extended(sql, params=None):
            if 'clock_timestamp' in sql and sql.startswith('SELECT extract'):
                assert connection.locked
                return Rows([(db.now,)])
            if 'paipu_private.replay_cache' not in sql:
                return execute(sql,params)
            if sql.startswith('SELECT ciphertext'):
                entry=db.cache.get(params[0])
                return Rows([(entry[0],)] if entry and entry[1]>db.now else [])
            assert connection.locked
            if sql.startswith('SELECT cache_key'):
                return Rows([(k,len(v[0])) for k,v in sorted(db.cache.items(),key=lambda x:x[1][2]) if k!=params[0]])
            if sql.startswith('INSERT'):
                db.cache[params[0]]=(params[1],db.now+30*86400,db.now)
            elif 'ANY' in sql:
                for k in params[0]:db.cache.pop(k,None)
            elif sql.startswith('DELETE'):
                for k in list(db.cache):
                    if db.cache[k][1]<=db.now:db.cache.pop(k)
            else:raise AssertionError(sql)
            return Rows([])
        connection.execute=extended
        return connection


@pytest.fixture
def storage():
    db=CacheDatabase();key=Fernet.generate_key().decode()
    with patch('psycopg.connect',side_effect=db.connect):
        yield db,lambda:ReplayStore(vault(key))
    assert not db.lock.locked() and all(c.closed for c in db.connections)


def test_restart_cache_is_encrypted_expires_and_skips_upstream_claim(storage):
    db,make=storage;calls=[];key=('international','a-record')
    payload={'log':[[1]],'name':['private-name','B','C','D']}
    def fetch():calls.append(1);return payload
    first=ReplayAdmission(durable=make())
    assert first.run(key,'one',fetch)[1]=='MISS'
    encrypted=next(iter(db.cache.values()))[0]
    assert 'private-name' not in encrypted and 'a-record' not in json.dumps(db.cache)
    saved=make().vault.load()
    assert len(saved['usage']['admission']['marks'])==1
    second=ReplayAdmission(durable=make())
    assert second.run(key,'two',fetch)==(payload,'DURABLE_HIT')
    assert len(calls)==1 and make().vault.load()==saved
    wrong=ReplayStore(vault())
    assert wrong.get(key) is None
    db.now+=30*86400+1
    assert make().get(key) is None
    assert ReplayAdmission(durable=make()).run(key,'three',fetch)[1]=='MISS'
    assert len(calls)==2


def test_global_limit_survives_restart_and_serializes_two_instances(storage):
    db,make=storage
    def attempt(i):
        try:make().claim();return 'accepted'
        except ReplayLimited as error:return error.code
    with ThreadPoolExecutor(max_workers=4) as workers:
        results=list(workers.map(attempt,range(14)))
    assert results.count('accepted')==10
    assert results.count('SERVICE_RATE_LIMITED')==4
    assert len(make().vault.load()['usage']['admission']['marks'])==10
    db.now+=60
    make().claim()
    assert len(make().vault.load()['usage']['admission']['marks'])==1


def test_540_pauses_all_instances_but_cached_replay_still_works(storage):
    db,make=storage;make().put('cached',{'log':[[1]]})
    def limited():raise GameError('fetch_record',540)
    with pytest.raises(GameError):ReplayAdmission(durable=make()).run('new','one',limited)
    with pytest.raises(ReplayLimited) as caught:
        ReplayAdmission(durable=make()).run('other','two',lambda:pytest.fail('provider called during hold'))
    assert caught.value.code=='UPSTREAM_REPLAY_LIMITED'
    assert ReplayAdmission(durable=make()).run('cached','three',limited)[1]=='DURABLE_HIT'
    db.now+=60;make().claim()


def test_cache_bounds_and_database_failure_do_not_fall_back_to_upstream(storage):
    db,make=storage
    with patch('replay_store.MAX_CACHE_ENTRIES',2):
        for i in range(3):
            db.now+=1;make().put(str(i),{'log':[[i]]})
    assert len(db.cache)==2 and make().get('0') is None
    db.fail=True
    with pytest.raises(VaultUnavailable):
        ReplayAdmission(durable=make()).run('uncached','one',lambda:pytest.fail('unsafe fallback'))


def test_durable_hit_works_with_full_upstream_slots_and_held_auth_lock(storage):
    db,make=storage;make().put('cached',{'log':[[1]]})
    admission=ReplayAdmission(durable=make(),max_pending=1,queue_timeout=0)
    # Model a slow authenticated request occupying all admission capacity AND
    # the shared auth advisory lock, as observed after a production restart.
    admission.flights['slow']=object();admission.active_visitors['another']='slow'
    admission.worker.acquire()
    with make().vault.locked():
        assert admission.run('cached','normal',lambda:pytest.fail('cache hit called provider'))[1]=='DURABLE_HIT'
    admission.worker.release()
