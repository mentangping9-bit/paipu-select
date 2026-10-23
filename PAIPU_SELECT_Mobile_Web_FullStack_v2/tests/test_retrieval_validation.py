from types import SimpleNamespace
from cryptography.fernet import Fernet
import pytest
import server
from majsoul_client import GameError
from replay_admission import ReplayAdmission
from retrieval_validation import validate
from service_account import AccountPool, AccountsCooling
from test_postgres_vault import database
from test_twenty_accounts import enroll,owners

URLS=['https://game.mahjongsoul.com/?paipu=261020-f5be3e18-149e-4a08-9060-9d304e07f891_a460096575',
      'https://mahjongsoul.game.yo-star.com/?paipu=261019-ed6ff58a-5721-4a85-bb86-b7199f7fa668_a917631742']
STATS=SimpleNamespace(stats=lambda:{'opened':0,'reused':0,'closed':0,'active':0})

def test_probe_uses_one_eligible_slot_twice_and_never_repeats_after_restart(database):
    key=Fernet.generate_key().decode();accounts=enroll(key)
    accounts[0].cooldown_until=1792720000;accounts[0].save(accounts[0].session)
    pool=AccountPool(accounts,clock=lambda:1792710000);calls=[]
    def fetch(url,s,a):calls.append(a.email);return {'log':[[1]]}
    validate(pool,ReplayAdmission(),server.extract_share_url,fetch,STATS,revision='test-one-shot',urls=URLS)
    assert calls==[accounts[1].email]*2
    assert accounts[0].cooldown_until==1792720000
    restored=AccountPool(owners(key),clock=lambda:1792710000)
    validate(restored,ReplayAdmission(),server.extract_share_url,fetch,STATS,revision='test-one-shot',urls=URLS)
    assert len(calls)==2
    with pytest.raises(AccountsCooling):
        restored.fetch(URLS[0],fetch,preferred_slot=1)
    assert len(calls)==2

def test_probe_stops_on_first_540_without_trying_another_slot(database):
    key=Fernet.generate_key().decode();accounts=enroll(key);calls=[]
    def fetch(url,s,a):calls.append(a.email);raise GameError('fetch_record',540)
    validate(AccountPool(accounts,clock=lambda:1792710000),ReplayAdmission(),server.extract_share_url,
             fetch,STATS,revision='test-540-once',urls=URLS)
    assert calls==[accounts[0].email] and accounts[0].cooldown_until>1792710000
