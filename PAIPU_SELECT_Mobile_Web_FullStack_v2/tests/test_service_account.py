"""Shared account behavior; providers are stubbed, never a live-login claim."""
import http.cookiejar
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.request
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
import pytest

import majsoul_client
import regional_auth
import server
from service_account import ServiceAccount, SessionVault, AccountPool
from replay_admission import ReplayAdmission, ReplayQueue
from paipu_vendor.mahjong_url_parser.sources.yostar import YostarSession

FIXTURE = json.loads(Path(__file__).with_name('fixture.json').read_text())
URL = 'https://mahjongsoul.game.yo-star.com/?paipu=261019-ed6ff58a-5721-4a85-bb86-b7199f7fa668_a917631742'


def make_manager(tmp_path, key=None):
    vault = SessionVault(str(tmp_path/'private'/'account.session.enc'),
                         key or Fernet.generate_key().decode(), tmp_path/'public')
    return ServiceAccount('service@example.com', 'kr', server.Session, vault)


def session(email='service@example.com'):
    return server.Session(time.monotonic(), time.monotonic(), email=email, region='kr',
                          uid='private-uid', token='private-token', device_id='private-device')


def test_encrypted_restart_and_email_binding(tmp_path):
    key = Fernet.generate_key().decode()
    manager = make_manager(tmp_path, key)
    assert not manager.enroll(session('unrelated@example.com'))
    original = session()
    assert manager.enroll(original)
    assert manager.ready_session() is not original
    data = manager.vault.path.read_bytes()
    assert b'private-token' not in data and b'service@example.com' not in data
    assert manager.vault.path.stat().st_mode & 0o777 == 0o600
    rebooted = make_manager(tmp_path, key)
    assert rebooted.ready_session().token == 'private-token'
    assert rebooted.ready_session().fresh_token_at == 0
    assert not rebooted.ready_session().game_verified
    manager.invalidate(manager.ready_session())
    assert make_manager(tmp_path, key).ready_session() is None


def test_bad_key_and_public_storage_are_rejected(tmp_path):
    make_manager(tmp_path).enroll(session())
    with pytest.raises(RuntimeError, match='복원하지 못했습니다'):
        make_manager(tmp_path)
    with pytest.raises(ValueError, match='공개 폴더 외부'):
        SessionVault(str(tmp_path/'public'/'secret'), Fernet.generate_key().decode(), tmp_path/'public')


def test_rotated_shared_token_is_durable_even_on_downstream_failure(tmp_path):
    manager = make_manager(tmp_path)
    manager.enroll(session())
    client = type('Client', (), {'refresh': AsyncMock(return_value=YostarSession('private-uid','rotated-secret','private-device'))})()
    with patch.object(server, 'service_account', manager), patch.object(regional_auth, 'regional_client', return_value=client), patch.object(
            majsoul_client, 'fetch_record', side_effect=majsoul_client.GameError('oauth_auth',110)):
        with pytest.raises(majsoul_client.GameError):
            server.fetch_from_mahjongsoul(URL, manager.ready_session())
    assert manager.vault.load()['token'] == 'rotated-secret'
    assert not manager.operation.locked()


def test_anonymous_retrieval_and_operator_logout_are_independent(tmp_path):
    manager = make_manager(tmp_path)
    server.sessions.clear()
    server.auth_attempts.clear()
    api = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
    worker = threading.Thread(target=api.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{api.server_port}'
    operator = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    visitor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    client = type('Client', (), {'device_id':'private-device','send_email_code':AsyncMock(),
                                'exchange_email_code':AsyncMock(return_value=YostarSession('private-uid','private-token','private-device')),
                                'refresh':AsyncMock(return_value=YostarSession('private-uid','rotated-token','private-device'))})()
    def post(opener, path, value):
        headers = {'Content-Type':'application/json'}
        if opener is operator:
            headers['X-Paipu-Operator-Key'] = 'test-operator-key-with-at-least-32-characters'
        return opener.open(urllib.request.Request(base+path, data=json.dumps(value).encode(),
                                                  headers=headers))
    def converted():
        response=post(visitor,'/api/convert',{'url':URL})
        data=json.load(response)
        deadline=time.monotonic()+3
        while 'job' in data and time.monotonic()<deadline:
            threading.Event().wait(0.005)
            data=json.load(visitor.open(base+'/api/convert/status?job='+data['job']))
        return data
    admission=ReplayAdmission()
    queue=ReplayQueue(admission,server.public_fetch_error,spacing=0)
    try:
        with patch.object(server,'service_pool',AccountPool([manager])), patch.object(server,'replay_queue',queue), patch.object(server,'OPERATOR_KEY','test-operator-key-with-at-least-32-characters'), patch.object(server,'service_account',manager), patch.object(regional_auth,'regional_client',return_value=client), patch.object(
                majsoul_client,'fetch_record',new=AsyncMock(return_value=FIXTURE)):
            page = visitor.open(base+'/?setup=1')
            assert page.headers['Cache-Control'] == 'no-store'
            assert f'app.js?v={server.BUILD}' in page.read().decode()
            assert not json.load(visitor.open(base+'/api/auth/status'))['shared_ready']
            post(operator,'/api/auth/send-code',{'service_account':True,
                                               'email':'unrelated@example.com','region':'en'}).read()
            client.send_email_code.assert_awaited_once_with('service@example.com')
            result = json.load(post(operator,'/api/auth/verify',{'code':'123456'}))
            assert result['shared_enrolled']
            status = json.load(visitor.open(base+'/api/auth/status'))
            assert status['shared_ready'] and not status['authenticated']
            assert not status['email']
            assert not any(secret in json.dumps(status) for secret in ['private-token','private-uid','private-device','service@example.com'])
            assert len(converted()['log']) == 10
            post(operator,'/api/auth/logout',{}).read()
            server.sessions.clear()  # Browser sessions may expire independently.
            assert json.load(visitor.open(base+'/api/auth/status'))['shared_game_authenticated']
            assert len(converted()['log']) == 10
            # Simulate a new process loading only the encrypted file.
            restored = ServiceAccount('service@example.com','kr',server.Session,manager.vault)
            # A process restart also loses the nonpersistent replay cache.
            with patch.object(server,'service_account',restored), patch.object(server,'service_pool',AccountPool([restored])), patch.object(server,'replay_queue',ReplayQueue(ReplayAdmission(),server.public_fetch_error,spacing=0)):
                assert len(converted()['log']) == 10
            assert manager.vault.load()['token'] == 'rotated-token'
    finally:
        api.shutdown()
        worker.join()
        api.server_close()
