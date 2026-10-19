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


async def _fetch_global_region_first(reference, credentials):
    """Fetch KR/EN shares on EN gateways first, with JP as a fallback.

    Upstream fetch_majsoul always tries JP first even for an EN URL and only
    falls back for some failures. A Yostar login can succeed while the JP
    game-account login fails, preventing the lookup of a KR record entirely.

    Keep upstream authentication, bootstrap, websocket and Tenhou conversion
    logic. Only correct the region ordering for EN / Korean shared URLs.
    """
    from mahjong_url_parser.models import (
        AuthenticationRequired, RemoteReplayError, ReplayNotFoundError,
        ServerRegion, VerificationCodeRequired,
    )
    from mahjong_url_parser.sources import majsoul as upstream
    login_session = await upstream.authenticate_yostar(credentials)
    failures = []
    for region in (ServerRegion.EN, ServerRegion.JP):
        try:
            version, gateways = await upstream._bootstrap(region)
            last_gateway_error = None
            for endpoint in gateways:
                try:
                    return await upstream._fetch_from_gateway(
                        endpoint, reference, credentials, version,
                        target_region=region, yostar_session=login_session,
                    )
                except (ReplayNotFoundError, AuthenticationRequired,
                        VerificationCodeRequired, RemoteReplayError):
                    # Semantic failures aren't resolved by switching endpoints
                    # within the same region, but another region may work.
                    raise
                except Exception as exc:
                    last_gateway_error = exc
            raise RemoteReplayError(
                f"{region.value} gateway unavailable ({type(last_gateway_error).__name__})"
            ) from last_gateway_error
        except (AuthenticationRequired, VerificationCodeRequired):
            raise
        except Exception as exc:
            # Try the other region, but keep the EN error for diagnosis if both
            # fail. No credentials or raw server response go to the browser.
            failures.append(exc)
    if failures:
        raise failures[0]
    raise RemoteReplayError('No replay gateways available')


def fetch_from_mahjongsoul(text: str, session: Session) -> dict:
    (Credentials, Region, _, _, _, fetch, parse) = _converter()
    # Keep path (/kr/ if present), host, paipu ID and viewer suffix intact.
    reference = parse(extract_share_url(text))
    credentials = Credentials(region=Region.JP, email=session.email,
                              yostar_uid=session.uid, yostar_token=session.token,
                              yostar_device_id=session.device_id)
    async def run():
        if reference.source_region is Region.EN:
            return await _fetch_global_region_first(reference, credentials)
        return await fetch(reference, credentials)
    result = asyncio.run(asyncio.wait_for(run(), timeout=100))
    if result.yostar_session:
        with lock:
            session.uid = result.yostar_session.uid
            session.token = result.yostar_session.token
            session.device_id = result.yostar_session.device_id
    return check_tenhou(result.payload)


def public_fetch_error(error: Exception) -> tuple[int, dict]:
    """Actionable diagnosis without exposing login tokens or upstream URLs."""
    kind = type(error).__name__
    detail = str(error)
    if kind == 'ReplayNotFoundError' or '没有找到' in detail:
        return 404, {'code': 'REPLAY_NOT_FOUND', 'error': '작혼 서버에 이 패보가 없습니다. 공유 링크의 서버 지역과 패보 공개 여부를 확인해 주세요.'}
    if kind in ('AuthenticationRequired', 'VerificationCodeRequired') or any(
        flag in detail for flag in ('OAuth2', '授权', '登录失败', '未绑定雀魂账号')
    ):
        return 401, {'code': 'GAME_LOGIN_FAILED', 'needs_auth': True,
                     'error': 'Yostar 인증은 완료됐지만 게임 서버 로그인에 실패했습니다. 해당 지역의 작혼 계정 연결을 확인하고 다시 인증해 주세요.'}
    if any(flag in detail for flag in ('转换为 Tenhou', '转换组件不完整', '校验', '牌谱数据')):
        return 502, {'code': 'CONVERSION_FAILED',
                     'error': '패보를 받았지만 천봉 JSON 변환에 실패했습니다. 서버 변환기 업데이트가 필요할 수 있습니다.'}
    if any(flag in detail for flag in ('无法连接', '连接超时', '配置服务器', '网页未返回', 'gateway unavailable', 'NetworkError')):
        return 503, {'code': 'GAME_GATEWAY_UNREACHABLE',
                     'error': '작혼 게임 서버 연결 또는 클라이언트 버전 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.'}
    return 502, {'code': 'UPSTREAM_REPLAY_FAILED',
                 'error': '작혼 패보를 가져오지 못했습니다. Render 서버의 최신 Deploy 로그에서 REPLAY_FAILED 분류를 확인해 주세요.'}


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
                                  'url_fetch_available': package_ready()})
            return
        if urlsplit(self.path).path == '/api/auth/status':
            _, s = self._get_session()
            self.json_reply(200, {'authenticated': bool(s and s.uid and s.token),
                                  'email': s.email if s and s.uid else ''})
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
                (_, Region, _, send, _, _, _) = _converter()
                device = asyncio.run(asyncio.wait_for(send(Region.JP, email, device_id=s.device_id), timeout=40))
                with lock:
                    s.email, s.device_id, s.code_sent = email, device, time.monotonic()
                return self.json_reply(200, {'ok': True, 'message': 'Yostar 인증 메일을 보냈습니다.'}, sid=sid)

            sid, s = self._get_session()
            if not s:
                return self.json_reply(401, {'error': 'Yostar 이메일 인증을 진행해 주세요.'})
            if action == '/api/auth/verify':
                code = str(body.get('code', '')).strip()
                if not re.fullmatch(r'\d{4,10}', code) or not s.email or not s.device_id:
                    raise ValueError('이메일 인증코드를 입력해 주세요.')
                _throttle('verify:' + sid, 8, 900)
                (Credentials, Region, _, _, authenticate, _, _) = _converter()
                credentials = Credentials(region=Region.JP, email=s.email, verification_code=code,
                                          yostar_device_id=s.device_id)
                verified = asyncio.run(asyncio.wait_for(authenticate(credentials), timeout=50))
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
