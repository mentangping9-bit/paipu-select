"""Security boundaries tested locally, without contacting Yostar or sending mail."""
import http.client
from http.server import ThreadingHTTPServer
import json
import socket
import threading
import time
from unittest.mock import patch

import pytest

import regional_auth
import server
from service_account import ServiceAccount, AccountPool

KEY = 'test-only-operator-key-with-32-or-more-characters'
URL = 'https://game.mahjongsoul.com/?paipu=261020-f5be3e18-149e-4a08-9060-9d304e07f891_a460096575'


@pytest.fixture
def endpoint():
    server.sessions.clear()
    server.auth_attempts.clear()
    api = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    worker = threading.Thread(target=api.serve_forever, daemon=True)
    worker.start()
    try:
        yield api.server_port
    finally:
        api.shutdown()
        worker.join()
        api.server_close()


def request(port, path, data=None, headers=None, method=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    hdr = {'Content-Type':'application/json', **(headers or {})}
    body = json.dumps(data).encode() if data is not None else None
    connection.request(method or ('POST' if data is not None else 'GET'), path, body, hdr)
    response = connection.getresponse()
    status, response_headers, content = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return status, response_headers, content


def test_operator_management_is_protected_without_disabling_public_replay(endpoint):
    owner = ServiceAccount('owner@example.com', 'kr', server.Session)
    owner.enroll(server.Session(0, 0, email='owner@example.com', uid='secret-user',
                               token='secret-token', device_id='secret-device'))
    with patch.object(server, 'service_account', owner), patch.object(server, 'OPERATOR_KEY', KEY), patch.object(
            regional_auth, 'regional_client') as provider, patch.object(server, 'fetch_from_mahjongsoul', return_value={'log':[]}) as fetch:
        for path, data in [('/api/auth/send-code', {'service_account':True}),
                           ('/api/auth/send-code', {'email':'owner@example.com'}),
                           ('/api/auth/verify', {'code':'123456'}), ('/api/auth/logout', {}), ('/api/auth/accounts', {})]:
            for candidate in ['', 'wrong-key']:
                status, _, raw = request(endpoint, path, data, {'X-Paipu-Operator-Key':candidate})
                assert status == 403
                assert json.loads(raw)['code'] == 'OPERATOR_AUTH_REQUIRED'
                assert KEY.encode() not in raw and b'secret-token' not in raw
        with patch.object(server, 'service_pool', AccountPool([owner])):
            status, _, raw = request(endpoint, '/api/auth/accounts', {}, {'X-Paipu-Operator-Key':KEY})
            assert status == 200 and json.loads(raw)['accounts'][0]['email'] == owner.email
            assert b'secret-token' not in raw and b'secret-device' not in raw and b'secret-user' not in raw
            assert owner.email.encode() not in request(endpoint, '/api/auth/status')[2]
        provider.assert_not_called()
        status, _, _ = request(endpoint, '/api/convert', {'url':URL})
        assert status == 200
        fetch.assert_called_once()
        assert request(endpoint, '/api/auth/logout', {}, {'X-Paipu-Operator-Key':KEY})[0] == 401
        with patch.object(server, 'OPERATOR_KEY', ''):
            assert request(endpoint, '/api/auth/send-code', {'service_account':True})[0] == 403
        assert owner.ready_session().token == 'secret-token'


def test_public_responses_do_not_expose_credentials_and_include_browser_policies(endpoint):
    for path in ['/', '/app.js', '/api/auth/status', '/.env', '/../../server.py', '/public/']:
        status, headers, raw = request(endpoint, path)
        assert headers['X-Frame-Options'] == 'DENY'
        assert headers['Referrer-Policy'] == 'no-referrer'
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        assert "script-src 'self'" in headers['Content-Security-Policy']
        assert "'unsafe-inline'" not in headers['Content-Security-Policy']
        assert 'Python' not in headers['Server']
        if path in ['/.env', '/../../server.py', '/public/']:
            assert status == 404
    for path in ['/server.py', '/%2e%2e/server.py', '/.env']:
        assert request(endpoint, path, method='HEAD')[0] == 404
    with patch.dict('os.environ', {'PUBLIC_HTTPS':'1'}):
        assert request(endpoint, '/')[1]['Strict-Transport-Security'] == 'max-age=15552000'


def test_cross_site_body_type_and_oversize_are_rejected_before_fetch(endpoint):
    with patch.object(server, 'fetch_from_mahjongsoul') as fetch:
        for headers in [{'Origin':'https://evil.example'}, {'Origin':'null'},
                        {'Sec-Fetch-Site':'cross-site'}, {'Content-Type':'text/plain'},
                        {'Content-Type':'application/json-evil'}]:
            assert request(endpoint, '/api/convert', {'url':URL}, headers)[0] == 400
        assert request(endpoint, '/api/convert', {'url':'x'*17000})[0] == 400
        fetch.assert_not_called()


def test_ambiguous_http_framing_is_rejected(endpoint):
    for headers in [b'Content-Length: 2\r\nContent-Length: 2',
                    b'Content-Length: 2\r\nTransfer-Encoding: chunked']:
        with socket.create_connection(('127.0.0.1', endpoint), timeout=3) as connection:
            connection.sendall(b'POST /api/convert HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n'+headers+b'\r\nConnection: close\r\n\r\n{}')
            assert b'400' in connection.recv(4096).split(b'\r\n',1)[0]


def test_rate_limit_memory_is_bounded():
    server.auth_attempts.clear()
    try:
        for _ in range(3):
            server._throttle('same-client', 3, 60)
        with pytest.raises(server.RateLimited):
            server._throttle('same-client', 3, 60)
        now=time.monotonic()
        server.auth_attempts.update({f'client-{i}':[now] for i in range(4096)})
        with pytest.raises(server.RateLimited):
            server._throttle('another-client')
        assert len(server.auth_attempts) <= 4097
    finally:
        server.auth_attempts.clear()


def test_overloaded_server_rejects_extra_connection_and_recovers():
    api=server.BoundedHTTPServer(('127.0.0.1',0),server.Handler,max_connections=2)
    worker=threading.Thread(target=api.serve_forever,daemon=True)
    worker.start()
    clients=[]
    try:
        for _ in range(2):
            connection=socket.create_connection(('127.0.0.1',api.server_port),timeout=3)
            connection.sendall(b'GET / HTTP/1.1\r\n')  # Deliberately unfinished local request.
            clients.append(connection)
        assert request(api.server_port,'/')[0] == 503
        for connection in clients:
            connection.close()
        clients.clear()
        for _ in range(20):
            status=request(api.server_port,'/')[0]
            if status==200:
                break
            threading.Event().wait(0.01)
        assert status == 200
    finally:
        for connection in clients:
            connection.close()
        api.shutdown()
        worker.join()
        api.server_close()

FRONTEND = 'https://paipu-select-web.onrender.com'


def test_static_frontend_cors_does_not_open_operator_apis(endpoint):
    for origin in [FRONTEND, 'https://evil.example', FRONTEND+'.evil.example']:
        status, headers, _ = request(endpoint, '/api/convert', headers={
            'Origin':origin,'Access-Control-Request-Method':'POST',
            'Access-Control-Request-Headers':'content-type,x-paipu-visitor'},method='OPTIONS')
        assert status == (204 if origin==FRONTEND else 403)
        assert headers.get('Access-Control-Allow-Origin') == (FRONTEND if origin==FRONTEND else None)
    status, headers, _ = request(endpoint, '/api/auth/accounts', headers={
        'Origin':FRONTEND,'Access-Control-Request-Method':'POST'},method='OPTIONS')
    assert status==403 and 'Access-Control-Allow-Origin' not in headers
    status, _, _ = request(endpoint, '/api/auth/accounts', {}, {
        'Origin':FRONTEND,'Sec-Fetch-Site':'cross-site','X-Paipu-Operator-Key':KEY})
    assert status==400


def test_static_frontend_queue_ownership_without_cookies(endpoint):
    owner = ServiceAccount('owner@example.com','jp',server.Session)
    owner.enroll(server.Session(0,0,email=owner.email,region='jp',uid='secret-id',
                               token='secret-token',device_id='secret-device'))
    common={'Origin':FRONTEND,'Sec-Fetch-Site':'cross-site'}
    with patch.object(server,'service_account',owner), patch.object(server,'service_pool',AccountPool([owner])), patch.object(
            server,'fetch_from_mahjongsoul',return_value={'log':[]}) as fetch:
        status, headers, raw = request(endpoint,'/api/convert',{'url':URL},common)
        assert status==202
        token=headers['X-Paipu-Visitor']
        assert len(token)==57 and 'secret' not in token
        assert headers['Access-Control-Allow-Origin']==FRONTEND
        assert 'Access-Control-Allow-Credentials' not in headers
        job=json.loads(raw)['job']
        path='/api/convert/status?job='+job
        assert request(endpoint,path,headers=common)[0]==404
        for _ in range(30):
            status, _, raw=request(endpoint,path,headers={**common,'X-Paipu-Visitor':token})
            if status!=202:break
            time.sleep(.01)
        assert status==200 and json.loads(raw)=={'log':[]}
        assert request(endpoint,path,headers={**common,'X-Paipu-Visitor':token[:-1]+'x'})[0]==404
        fetch.assert_called_once()
