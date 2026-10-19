"""Server/session integration with stubbed providers, not live login tests."""
import json
from pathlib import Path
import threading
import time
from unittest.mock import AsyncMock, patch
from http.server import ThreadingHTTPServer
import http.cookiejar
import urllib.error
import urllib.request

from paipu_vendor.mahjong_url_parser.sources.yostar import YostarSession
import majsoul_client
import regional_auth
import server

FIXTURE=json.loads(Path(__file__).with_name('fixture.json').read_text())
URL='https://mahjongsoul.game.yo-star.com/?paipu=261019-ed6ff58a-5721-4a85-bb86-b7199f7fa668_a917631742'


def test_token_rotation_is_saved_even_when_game_rejects_it():
    s=server.Session(0,0,uid='u',token='old',device_id='d')
    client=type('Client',(),{'refresh':AsyncMock(return_value=YostarSession('u','rotated','d'))})()
    with patch.object(regional_auth,'regional_client',return_value=client), patch.object(
            majsoul_client,'fetch_record',side_effect=majsoul_client.GameError('oauth_auth',110)):
        try:server.fetch_from_mahjongsoul(URL,s)
        except majsoul_client.GameError:pass
    assert s.token=='rotated' and s.game_verified is False
    assert not s.operation.locked()


def test_http_auth_cookie_and_replay_flow():
    server.sessions.clear();server.auth_attempts.clear()
    api=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    worker=threading.Thread(target=api.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{api.server_port}'
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    client=type('Client',(),{'device_id':'d','send_email_code':AsyncMock(),
                            'exchange_email_code':AsyncMock(return_value=YostarSession('u','secret-device-session','d'))})()
    def post(path,body):
        return opener.open(urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}))
    try:
        with patch.object(regional_auth,'regional_client',return_value=client),patch.object(majsoul_client,'fetch_record',new=AsyncMock(return_value=FIXTURE)):
            assert json.load(opener.open(base+'/api/auth/status'))['authenticated'] is False
            response=post('/api/auth/send-code',{'email':'test@example.com','region':'kr'})
            assert 'HttpOnly' in response.headers['Set-Cookie']
            response.read()
            verified=post('/api/auth/verify',{'code':'123456'}).read().decode()
            assert 'secret-device-session' not in verified
            assert json.load(opener.open(base+'/api/auth/status'))['game_authenticated'] is False
            assert len(json.load(post('/api/convert',{'url':'작혼 패보:'+URL}))['log'])==10
            assert json.load(opener.open(base+'/api/auth/status'))['game_authenticated'] is True
            assert json.load(post('/api/auth/logout',{}))['ok']
            assert json.load(opener.open(base+'/api/auth/status'))['authenticated'] is False
    finally:
        api.shutdown();worker.join();api.server_close()
