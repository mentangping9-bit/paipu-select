"""PAIPU SELECT mobile web server.

Actual Mahjong Soul KR/JP/US retrieval is implemented through the MIT-licensed
LekangZou/Mahjong-Replay-Converter Python library. Authenticated replay fetching
requires Yostar email verification, never a password or external service token.

Run: python server.py
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
HOSTS = {"game.mahjongsoul.com", "mahjongsoul.game.yo-star.com", "mahjongsoul.com", "www.mahjongsoul.com", "game.maj-soul.com", "game.maj-soul.net"}
PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,160}$")
SHARE_URL = re.compile(r"https://[^\s\xa0<>\"'`]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ")]}>,.!?;:。．，、！？）」』】"
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
COOKIE_NAME = "ps_session"
TTL = 2 * 60 * 60
MAX_JSON = 12 * 1024 * 1024
SESSION_LIMIT = 1500

@dataclass
class Session:
    created: float
    last_active: float
    email: str = ""
    device_id: str = ""
    uid: str = ""
    token: str = ""
    region: str = "kr"
    code_sent: float = 0

sessions: dict[str, Session] = {}
auth_attempts: dict[str, list[float]] = {}
lock = threading.RLock()


def extract_share_url(text: str) -> str:
    """Accept raw URLs and localized share messages; reject unknown hosts.

    Never fetch user-provided URLs here. This is an exact-host, fixed-parameter
    normalization for the Mahjong Soul replay id only.
    """
    if not isinstance(text, str) or len(text) > 8192:
        raise ValueError("작혼 공유 문구가 너무 길거나 올바르지 않습니다.")
    for match in SHARE_URL.finditer(text.replace("&amp;", "&")):
        candidate = match.group().rstrip(TRAILING_PUNCTUATION)
        try:
            parsed = urlsplit(candidate)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or host not in HOSTS or parsed.port or parsed.username or parsed.password:
                continue
            ids = parse_qs(parsed.query, keep_blank_values=True).get("paipu", [])
            if len(ids) != 1 or not PATTERN.fullmatch(ids[0]):
                continue
            return urlunsplit(("https", host, parsed.path or "/", urlencode({"paipu": ids[0]}), ""))
        except ValueError:
            continue
    raise ValueError("복사한 문구에서 공식 작혼 패보 URL을 찾지 못했습니다. 공유 내용을 그대로 붙여넣어 주세요.")


def parse_url(text: str) -> tuple[str, str]:
    url = extract_share_url(text)
    parsed = urlsplit(url)
    return parse_qs(parsed.query)["paipu"][0], parsed.hostname.lower()


def check_tenhou(v):
    if not isinstance(v, dict) or not isinstance(v.get("log"), list) or not v["log"]:
        raise ValueError("천봉 JSON의 log 데이터가 없습니다.")
    if len(v["log"]) > 120 or len(json.dumps(v, ensure_ascii=False)) > MAX_JSON:
        raise ValueError("패보가 너무 큽니다.")
    for r in v["log"]:
        if not isinstance(r, list) or len(r) < 17 or not isinstance(r[0], list) or not isinstance(r[16], list):
            raise ValueError("국별 기록이 올바르지 않습니다.")
    return v


def _converter():
    """Lazy import so the UI + JSON-file flow can be tested offline."""
    from mahjong_url_parser.models import MahjongSoulCredentials, ServerRegion, ReplayNotFoundError
    from mahjong_url_parser.sources.majsoul import (
        send_yostar_email_code, authenticate_yostar, fetch_majsoul
    )
    from mahjong_url_parser.urls import parse_replay_url
    from regional_auth import patch_connection_handshake
    from mahjong_url_parser.sources import majsoul as upstream
    patch_connection_handshake(upstream)
    return (MahjongSoulCredentials, ServerRegion, ReplayNotFoundError,
            send_yostar_email_code, authenticate_yostar, fetch_majsoul, parse_replay_url)


def package_ready() -> bool:
    try:
        _converter()
        return True
    except ImportError:
        return False


def _cleanup():
    now = time.monotonic()
    for sid, s in list(sessions.items()):
        if now - s.last_active > TTL:
            sessions.pop(sid, None)
    if len(sessions) > SESSION_LIMIT:
        for sid in sorted(sessions, key=lambda k: sessions[k].last_active)[:len(sessions) - SESSION_LIMIT]:
            sessions.pop(sid, None)
    for key, marks in list(auth_attempts.items()):
        marks[:] = [x for x in marks if now - x < 3600]
        if not marks:
            auth_attempts.pop(key, None)


def _throttle(key: str, limit: int = 4, duration: int = 900):
    now = time.monotonic()
    with lock:
        marks = auth_attempts.setdefault(key, [])
        marks[:] = [x for x in marks if now - x < duration]
        if len(marks) >= limit:
            raise ValueError("인증 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        marks.append(now)


async def _bootstrap_for_account(upstream, region: str):
    """Use the regional web version AND route id; KR is not EN language.

    Route ids are returned by /api/clientgate/routes. A previously hardcoded
    'en-2' was not necessarily valid for the Korean account's route.
    """
    import aiohttp
    from urllib.parse import quote
    import random
    from regional_auth import select_gateway_routes
    target = upstream.ServerRegion.JP if region == "jp" else upstream.ServerRegion.EN
    # EN and JP versions from upstream, KR version from the /kr/ client.
    if region == "kr":
        base = "https://mahjongsoul.game.yo-star.com/kr/"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
                html = await upstream._text(s, base)
                version = upstream._unity_version_from_html(html)
        except (aiohttp.ClientError, TimeoutError, upstream.RemoteReplayError):
            # The Korean client sometimes redirects to the shared EN build.
            shared_version, _ = await upstream._bootstrap(target)
            version = shared_version.removeprefix("web-").removeprefix("WebGL_2022-")
    else:
        version_with_prefix, _ = await upstream._bootstrap(target)
        version = version_with_prefix.removeprefix("web-").removeprefix("WebGL_2022-")
    # For Unity WebGL protocol, request version string must use WebGL_2022.
    version_string = "WebGL_2022-" + version
    authorities = ("jpgs.mahjongsoul.com", "jpgsbk.mahjongsoul.com") if region == "jp" \
        else ("engs.mahjongsoul.com", "engsbk.mahjongsoul.com")
    errors = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        for authority in authorities:
            url = (f"https://{authority}/api/clientgate/routes?platform=Web"
                   f"&version={quote(version)}&lang={region}&randv={random.randint(1, 999999999)}")
            try:
                payload = await upstream._json(s, url)
                routes = payload.get("data", {}).get("routes", [])
                valid = select_gateway_routes(routes, authority)
                if valid:
                    return version_string, valid
            except (aiohttp.ClientError, TimeoutError, KeyError, ValueError,
                    upstream.RemoteReplayError) as exc:
                errors.append(type(exc).__name__)
    raise upstream.RemoteReplayError(
        "작혼 서버에서 해당 지역의 유효한 접속 경로 ID를 가져오지 못했습니다.")


async def _fetch_by_region(reference, credentials, login_region: str):
    """Obtain account-region token, route/version, then fetch replay."""
    from mahjong_url_parser.models import (
        RemoteReplayError, ReplayNotFoundError, ServerRegion
    )
    from mahjong_url_parser.sources import majsoul as upstream
    from regional_auth import regional_client, route_context

    target = ServerRegion.JP if login_region == "jp" else ServerRegion.EN
    client = regional_client(login_region, credentials.yostar_device_id)
    session = await client.refresh(credentials.yostar_uid, credentials.yostar_token)
    version, routes = await _bootstrap_for_account(upstream, login_region)
    errors = []
    for endpoint, route_id in routes:
        ctx = route_context.set(route_id)
        try:
            return await upstream._fetch_from_gateway(
                endpoint, reference, credentials, version,
                target_region=target, yostar_session=session,
            )
        except (RemoteReplayError, ReplayNotFoundError):
            raise  # Wrong credentials: retrying a gateway does not fix it.
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            route_context.reset(ctx)
    raise RemoteReplayError('게임 게이트웨이에 연결하지 못했습니다: ' +
                            (errors[-1] if errors else 'NoGateway'))


def fetch_from_mahjongsoul(text: str, session: Session) -> dict:
    (Credentials, Region, _, _, _, _, parse) = _converter()
    reference = parse(extract_share_url(text))
    credentials = Credentials(region=Region.JP, email=session.email,
                              yostar_uid=session.uid, yostar_token=session.token,
                              yostar_device_id=session.device_id)
    result = asyncio.run(asyncio.wait_for(
        _fetch_by_region(reference, credentials, session.region), timeout=100))
    if result.yostar_session:
        with lock:
            session.uid = result.yostar_session.uid
            session.token = result.yostar_session.token
            session.device_id = result.yostar_session.device_id
    return check_tenhou(result.payload)


def public_fetch_error(error: Exception) -> tuple[int, dict]:
    detail = str(error)
    if type(error).__name__ == 'ReplayNotFoundError':
        return 404, {'code':'REPLAY_NOT_FOUND',
                     'error':'이 서버에서 패보를 찾지 못했습니다. 공유 링크와 서버 지역을 확인해 주세요.'}
    if '尚未绑定' in detail or '未绑定雀魂账号' in detail:
        return 403, {'code':'GAME_ACCOUNT_UNBOUND',
                     'error':'해당 인증 지역의 Yostar 계정에 작혼 게임 계정이 연결되지 않았다는 응답입니다. 한국/일본/영문 로그인 지역을 확인해 주세요.'}
    if 'OAuth2' in detail or '雀魂登录失败' in detail or '登录未返回' in detail:
        import re as _re
        match = _re.search(r'(?:代码|code)\s*(\d+)', detail)
        code = match.group(1) if match else 'unknown'
        # 151 commonly means client protocol/version mismatch, not bad credentials.
        if code == '151':
            return 502, {'code':'GAME_PROTOCOL_MISMATCH', 'stage':'oauth',
                         'error':'게임 서버가 로그인 프로토콜 또는 버전을 거부했습니다 (151). 이메일 재인증보다 서버 코드 업데이트가 필요합니다.'}
        return 502, {'code':'GAME_OAUTH_FAILED', 'stage':'oauth',
                     'error':f'작혼 게임 서버 OAuth 단계에서 코드 {code}을 반환했습니다. 인증 지역·토큰 또는 프로토콜이 일치하지 않을 수 있습니다.'}
    if '게임 게이트웨이' in detail or '连接' in detail or '초기화' in detail:
        return 503, {'code':'GAME_GATEWAY_ERROR', 'stage':'connect',
                     'error':'작혼 게임 서버 연결 또는 연결 초기화 실패입니다. 네트워크/프로토콜 상태를 확인해야 합니다.'}
    if '转换' in detail or '校验' in detail:
        return 502, {'code':'CONVERSION_FAILED', 'stage':'convert',
                     'error':'서버가 패보를 받았지만 JSON 변환에 실패했습니다.'}
    if type(error).__name__ in ('AuthenticationRequired', 'VerificationCodeRequired'):
        return 401, {'code':'SDK_SESSION_EXPIRED', 'needs_auth':True,
                     'error':'인증 세션이 만료됐습니다. Yostar 인증을 다시 진행해 주세요.'}
    return 502, {'code':'REPLAY_FETCH_FAILED',
                 'error':f'패보 조회에 실패했습니다 (유형 {type(error).__name__}). 서버 로그의 오류 분류를 확인해 주세요.'}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, format, *args):
        # Don't put OTP, e-mail or replay URL in logs.
        if self.path.startswith('/api/'):
            print('api', self.command, urlsplit(self.path).path)
        else:
            super().log_message(format, *args)

    def json_reply(self, status: int, value: dict, *, sid: str | None = None):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store, private')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if sid:
            secure = ('Secure; ' if self.headers.get('X-Forwarded-Proto') == 'https'
                      or os.getenv('PUBLIC_HTTPS') == '1' else '')
            self.send_header('Set-Cookie', f'{COOKIE_NAME}={sid}; Path=/; HttpOnly; {secure}SameSite=Lax; Max-Age={TTL}')
        self.end_headers()
        self.wfile.write(raw)

    def _get_session(self, create=False):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            sid = cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ''
        except Exception:
            sid = ''
        with lock:
            _cleanup()
            s = sessions.get(sid)
            if s and time.monotonic() - s.last_active <= TTL:
                s.last_active = time.monotonic()
                return sid, s
            if create:
                sid = secrets.token_urlsafe(32)
                sessions[sid] = Session(created=time.monotonic(), last_active=time.monotonic())
                return sid, sessions[sid]
        return None, None

    def _read_request(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if origin:
            u = urlsplit(origin)
            if u.netloc != host or u.scheme not in ('https', 'http'):
                raise ValueError('요청 출처가 허용되지 않았습니다.')
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            raise ValueError('JSON 요청만 지원합니다.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as exc:
            raise ValueError('잘못된 요청 길이입니다.') from exc
        if not 0 < length <= 8000:
            raise ValueError('요청이 너무 큽니다.')
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError('요청은 JSON 객체여야 합니다.')
        return value

    def do_GET(self):
        if urlsplit(self.path).path == '/api/health':
            self.json_reply(200, {'status': 'ok', 'kr_fetch_available': package_ready(),
                                  'url_fetch_available': package_ready(),
                                  'version': '2.6'})
            return
        if urlsplit(self.path).path == '/api/auth/status':
            _, s = self._get_session()
            self.json_reply(200, {'authenticated': bool(s and s.uid and s.token),
                                  'email': s.email if s and s.uid else '',
                                  'region': s.region if s and s.uid else 'kr'})
            return
        self.path = urlsplit(self.path).path
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        action = urlsplit(self.path).path
        if action not in ('/api/auth/send-code', '/api/auth/verify', '/api/auth/logout', '/api/convert'):
            return self.json_reply(404, {'error': '없는 API입니다.'})
        try:
            body = self._read_request()
            if action == '/api/auth/send-code':
                email = str(body.get('email', '')).strip().lower()
                region = str(body.get('region', 'kr')).lower()
                if region not in ('kr','jp','en'):
                    raise ValueError('인증 지역은 한국/일본/영문 중 선택해 주세요.')
                if not EMAIL.fullmatch(email) or len(email) > 254:
                    raise ValueError('올바른 Yostar 로그인 이메일을 입력해 주세요.')
                if not package_ready():
                    return self.json_reply(503, {'error': '서버 변환 라이브러리가 설치되지 않았습니다.'})
                sid, s = self._get_session(create=True)
                if s.code_sent and time.monotonic() - s.code_sent < 60:
                    raise ValueError('인증 메일 재전송은 60초 후 가능합니다.')
                # Per-address and per-client basic throttling, no email logs.
                _throttle('email:' + email, 4, 3600)
                _throttle('ip:' + self.client_address[0], 10, 3600)
                _converter()
                from regional_auth import regional_client
                client = regional_client(region, s.device_id if s.region == region else '')
                asyncio.run(asyncio.wait_for(client.send_email_code(email), timeout=40))
                device = client.device_id
                with lock:
                    s.email, s.device_id, s.region, s.code_sent = email, device, region, time.monotonic()
                    s.uid, s.token = "", ""
                return self.json_reply(200, {'ok': True, 'message': 'Yostar 인증 메일을 보냈습니다.'}, sid=sid)

            sid, s = self._get_session()
            if not s:
                return self.json_reply(401, {'error': 'Yostar 이메일 인증을 진행해 주세요.'})
            if action == '/api/auth/verify':
                code = str(body.get('code', '')).strip()
                if not re.fullmatch(r'\d{4,10}', code) or not s.email or not s.device_id:
                    raise ValueError('이메일 인증코드를 입력해 주세요.')
                _throttle('verify:' + sid, 8, 900)
                _converter()
                from regional_auth import regional_client
                client = regional_client(s.region, s.device_id)
                verified = asyncio.run(asyncio.wait_for(client.exchange_email_code(s.email, code), timeout=50))
                with lock:
                    s.uid, s.token, s.device_id = verified.uid, verified.token, verified.device_id
                return self.json_reply(200, {'ok': True, 'authenticated': True}, sid=sid)
            if action == '/api/auth/logout':
                with lock:
                    sessions.pop(sid, None)
                return self.json_reply(200, {'ok': True})
            if action == '/api/convert':
                if not s.uid or not s.token:
                    return self.json_reply(401, {'error': '먼저 Yostar 이메일 인증을 완료해 주세요.', 'needs_auth': True})
                url = extract_share_url(str(body.get('url', '')))
                _, host = parse_url(url)
                if host == 'mahjongsoul.game.yo-star.com' and s.region == 'jp':
                    return self.json_reply(409, {'code':'REGION_MISMATCH',
                        'error':'영문/한국 작혼 링크는 영문 또는 한국 Yostar 지역 인증을 선택해 주세요.'})
                if host in ('game.mahjongsoul.com','mahjongsoul.com','www.mahjongsoul.com') and s.region != 'jp':
                    return self.json_reply(409, {'code':'REGION_MISMATCH',
                        'error':'일본 작혼 링크는 일본 Yostar 지역 인증을 선택해 주세요.'})
                if host in ('game.maj-soul.com', 'game.maj-soul.net'):
                    raise ValueError('중국 서버 링크는 별도의 중국 서버 계정 인증이 필요합니다.')
                result = fetch_from_mahjongsoul(url, s)
                return self.json_reply(200, result)
        except ValueError as exc:
            return self.json_reply(400, {'error': str(exc)})
        except asyncio.TimeoutError:
            return self.json_reply(504, {'error': '작혼 서버 응답 시간 초과입니다. 잠시 후 다시 시도해 주세요.'})
        except Exception as exc:
            # Return safe, actionable classifications, never auth tokens, stack or OTP.
            typ = type(exc).__name__
            if typ == 'VerificationCodeRequired':
                return self.json_reply(401, {'error': '인증 세션이 만료되었습니다. 이메일 인증을 다시 진행해 주세요.', 'needs_auth': True})
            if typ in ('YostarApiError', 'RemoteReplayError', 'ReplayNotFoundError',
                       'AuthenticationRequired', 'VerificationCodeRequired'):
                if action.startswith('/api/auth'):
                    return self.json_reply(502, {'code': 'YOSTAR_AUTH_FAILED',
                                                 'error': 'Yostar 이메일 인증 서버에 연결하거나 로그인하지 못했습니다.'})
                status, data = public_fetch_error(exc)
                print('Replay fetch failed:', typ, data['code'])
                return self.json_reply(status, data)
            print('Internal error:', typ)
            return self.json_reply(500, {'error': '서버 내부 오류가 발생했습니다.'})


if __name__ == '__main__':
    port = int(os.getenv('PORT', '8765'))
    print(f'Paipu Select started: http://0.0.0.0:{port}')
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
