from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import threading
import time
from unittest.mock import patch

import pytest

from replay_admission import ReplayAdmission, ReplayLimited, ReplayQueue
import server
from service_account import ServiceAccount, AccountPool


def test_normal_use_cache_isolation_and_window_recovery():
    now=[0.0]
    admission=ReplayAdmission(clock=lambda:now[0])
    calls=[]
    def fetch():
        calls.append(1)
        return {'log':[[1]], 'name':['A','B','C','D']}
    data, status=admission.run(('kr','id'), 'browser-a', fetch)
    assert status=='MISS'
    data['name'][0]='modified'
    assert admission.run(('kr','id'), 'browser-b', fetch)[0]['name'][0]=='A'
    for _ in range(11):
        assert admission.run(('kr','id'), 'browser-a', fetch)[1]=='HIT'
    with pytest.raises(ReplayLimited) as caught:
        admission.run(('kr','id'), 'browser-a', fetch)
    assert caught.value.code=='VISITOR_RATE_LIMITED' and caught.value.retry_after==60
    # Another visitor on the same server/proxy is not penalized.
    assert admission.run(('kr','id'), 'browser-b', fetch)[1]=='HIT'
    assert len(calls)==1
    now[0]=60
    assert admission.run(('kr','id'), 'browser-a', fetch)[1]=='HIT'


def test_hourly_and_global_limits_charge_only_actual_upstream_work():
    now=[0.0]
    admission=ReplayAdmission(clock=lambda:now[0],per_minute=1000,per_hour=3,global_per_minute=2)
    fetch=lambda:{'log':[]}
    assert admission.run('a','one',fetch)[1]=='MISS'
    assert admission.run('b','two',fetch)[1]=='MISS'
    for visitor in ['three','four']:
        assert admission.run('a',visitor,fetch)[1]=='HIT'
    with pytest.raises(ReplayLimited) as caught:
        admission.run('c','five',fetch)
    assert caught.value.code=='SERVICE_RATE_LIMITED'
    assert admission.run('a','one',fetch)[1]=='HIT'
    assert admission.run('a','one',fetch)[1]=='HIT'
    with pytest.raises(ReplayLimited) as caught:
        admission.run('a','one',fetch)
    assert caught.value.code=='VISITOR_RATE_LIMITED' and caught.value.retry_after==3600
    now[0]=60
    assert admission.run('c','six',fetch)[1]=='MISS'


def test_duplicate_requests_share_one_upstream_call():
    admission=ReplayAdmission()
    entered, release=threading.Event(),threading.Event()
    calls=[]
    def fetch():
        calls.append(1);entered.set()
        assert release.wait(2)
        return {'log':[[1]]}
    with ThreadPoolExecutor(max_workers=3) as executor:
        leader=executor.submit(admission.run,'same','one',fetch)
        assert entered.wait(1)
        followers=[executor.submit(admission.run,'same',v,fetch) for v in ['two','three']]
        deadline=time.monotonic()+1
        while admission.joiners<2 and time.monotonic()<deadline:
            threading.Event().wait(0.005)
        assert admission.joiners==2
        release.set()
        assert leader.result()[1]=='MISS'
        assert [future.result()[1] for future in followers]==['SHARED','SHARED']
    assert len(calls)==1 and admission.joiners==0 and not admission.flights


def test_short_queue_is_serial_and_overflow_does_not_hit_upstream():
    admission=ReplayAdmission(max_pending=2)
    entered,release=threading.Event(),threading.Event()
    calls=[]
    def first():
        calls.append('first');entered.set()
        assert release.wait(2)
        return {'log':[]}
    def second():
        calls.append('second');return {'log':[]}
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_request=executor.submit(admission.run,'first','one',first)
        assert entered.wait(1)
        with pytest.raises(ReplayLimited) as caught:
            admission.run('other','one',second)
        assert caught.value.code=='REPLAY_BUSY'
        waiting=executor.submit(admission.run,'second','two',second)
        deadline=time.monotonic()+1
        while len(admission.flights)<2 and time.monotonic()<deadline:
            threading.Event().wait(0.005)
        with pytest.raises(ReplayLimited) as caught:
            admission.run('third','three',second)
        assert caught.value.status==503 and calls==['first']
        release.set()
        assert first_request.result()[1]=='MISS'
        assert waiting.result()[1]=='MISS'
    assert calls==['first','second'] and not admission.active_visitors


def test_queue_timeout_and_failures_release_slots_without_caching_errors():
    admission=ReplayAdmission(queue_timeout=0.02)
    entered,release=threading.Event(),threading.Event()
    def fetch():
        entered.set();assert release.wait(2);return {'log':[]}
    with ThreadPoolExecutor(max_workers=1) as executor:
        first=executor.submit(admission.run,'a','one',fetch)
        assert entered.wait(1)
        with pytest.raises(ReplayLimited) as caught:
            admission.run('b','two',lambda:{'log':[]})
        assert caught.value.code=='REPLAY_BUSY' and len(admission.upstream_marks)==1
        release.set();first.result()
    def error():raise RuntimeError('example provider failure')
    with pytest.raises(RuntimeError):admission.run('b','two',error)
    assert not admission.flights and not admission.worker.locked()
    assert admission.run('b','two',lambda:{'log':[]})[1]=='MISS'


def test_cache_and_visitor_state_have_fixed_bounds_and_expire():
    now=[0.0]
    admission=ReplayAdmission(clock=lambda:now[0],cache_entries=2,cache_bytes=100,cache_ttl=10,
                              global_per_minute=100,per_minute=100)
    for key in ['a','b','c']:
        admission.run(key,key,lambda:{'log':[]})
    assert len(admission.cache)==2 and admission.cached_bytes<=100
    assert admission.run('b','b',lambda:{'log':[]})[1]=='HIT'
    now[0]=10
    assert admission.run('b','b',lambda:{'log':[]})[1]=='MISS'
    with admission.lock:
        for i in range(4200):admission._visitor(str(i),now[0])
    assert len(admission.visitors)==4096


def test_http_cookie_is_not_auth_and_throttles_have_retry_after():
    admission=ReplayAdmission(per_minute=2)
    owner=ServiceAccount('owner@example.com','kr',server.Session)
    owner.enroll(server.Session(0,0,email='owner@example.com',uid='u',token='private-token',device_id='d'))
    api=server.BoundedHTTPServer(('127.0.0.1',0),server.Handler)
    worker=threading.Thread(target=api.serve_forever,daemon=True);worker.start()
    url='https://game.mahjongsoul.com/?paipu=261020-f5be3e18-149e-4a08-9060-9d304e07f891_a460096575'
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=0)
    def request(cookie='',job=None):
        connection=http.client.HTTPConnection('127.0.0.1',api.server_port,timeout=2)
        if job:
            connection.request('GET','/api/convert/status?job='+job,headers={'Cookie':cookie})
        else:
            connection.request('POST','/api/convert',json.dumps({'url':url}),{'Content-Type':'application/json','Cookie':cookie})
        response=connection.getresponse();raw=response.read()
        result=(response.status,dict(response.getheaders()),json.loads(raw));connection.close();return result
    try:
        with patch.object(server,'service_account',owner),patch.object(server,'replay_admission',admission),patch.object(server,'service_pool',AccountPool([owner])),patch.object(server,'replay_queue',queue),patch.object(
                server,'fetch_from_mahjongsoul',return_value={'log':[]}) as fetch,patch.dict('os.environ',{'PUBLIC_HTTPS':'1'}):
            status,headers,body=request()
            assert status==202 and headers['X-Paipu-Cache']=='QUEUED'
            cookie=headers['Set-Cookie'].split(';')[0]
            assert cookie.startswith('ps_visitor=') and 'private-token' not in cookie
            assert 'HttpOnly' in headers['Set-Cookie'] and 'Secure' in headers['Set-Cookie']
            ticket=body['job']
            deadline=time.monotonic()+2
            while request(cookie,ticket)[0]==202 and time.monotonic()<deadline:
                threading.Event().wait(0.005)
            assert request(cookie,ticket)[0]==200
            assert request('',ticket)[0]==404
            assert request(cookie)[1]['X-Paipu-Cache']=='HIT'
            status,headers,body=request(cookie)
            assert status==429 and body['code']=='VISITOR_RATE_LIMITED'
            assert int(headers['Retry-After'])==body['retry_after']
            assert request()[0]==200  # Another browser on the same connection address.
            fetch.assert_called_once()
    finally:
        api.shutdown();worker.join();api.server_close()
