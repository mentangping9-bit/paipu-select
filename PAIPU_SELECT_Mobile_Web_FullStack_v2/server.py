"""PAIPU SELECT mobile web server.

Actual Mahjong Soul KR/JP/US retrieval is implemented through the MIT-licensed
LekangZou/Mahjong-Replay-Converter Python library. Authenticated replay fetching
requires Yostar email verification, never a password or external service token.

Run: python server.py
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from service_account import ServiceAccount, SessionVault
from postgres_vault import PostgresVault, VaultBusy, VaultCorrupt, VaultUnavailable

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
try:
    BUILD = os.getenv('RENDER_GIT_COMMIT') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
except (OSError, subprocess.SubprocessError):
    BUILD = 'local'
gateway_probe = {'status': 'not_run', 'authenticated': False}
HOSTS = {"game.mahjongsoul.com", "mahjongsoul.game.yo-star.com", "mahjongsoul.com", "www.mahjongsoul.com", "game.maj-soul.com", "game.maj-soul.net"}
PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,160}$")
SHARE_URL = re.compile(r"https://[^\s\xa0<>\"'`]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ")]}>,.!?;:。．，、！？）」』】"
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
COOKIE_NAME = "ps_session"
TTL = 2 * 60 * 60
MAX_JSON = 12 * 1024 * 1024
SESSION_LIMIT = 1500
OPERATOR_KEY = os.getenv('PAIPU_OPERATOR_KEY', '')
STATIC_PATHS = {'/styles.css', '/app.js', '/converter.js', '/link-utils.js', '/i18n.js'}


class RateLimited(ValueError):
    pass


class BoundedHTTPServer(ThreadingHTTPServer):
    """Bound accepted handler threads; slow clients cannot create unlimited work."""
    daemon_threads = True

    def __init__(self, *args, max_connections=24, **kwargs):
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

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
    fresh_token_at: float = 0
    game_verified: bool = False
    operation: threading.Lock = field(default_factory=threading.Lock, repr=False)

sessions: dict[str, Session] = {}
auth_attempts: dict[str, list[float]] = {}
lock = threading.RLock()


def configure_service_account():
    email = os.getenv('PAIPU_SERVICE_EMAIL', '').strip().lower()
    region = os.getenv('PAIPU_SERVICE_REGION', 'kr').strip().lower()
    if email and (not EMAIL.fullmatch(email) or region not in ('kr', 'jp', 'en')):
        raise ValueError('공용 계정 환경 설정이 올바르지 않습니다.')
    path, key = os.getenv('PAIPU_ACCOUNT_FILE', ''), os.getenv('PAIPU_ACCOUNT_KEY', '')
    database = os.getenv('PAIPU_DATABASE_URL', '')
    if path and database:
        raise ValueError('공용 계정 저장소는 한 가지만 설정해 주세요.')
    if bool(path or database) != bool(key):
        raise ValueError('공용 계정 저장소와 암호화 키를 함께 설정해야 합니다.')
    vault = PostgresVault(database, key) if database else SessionVault(path, key, PUBLIC) if path else None
    return ServiceAccount(email, region, Session, vault)


service_account = configure_service_account()


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
    # tensoul emits NamedTuple Round headers and tuple result records. JSON
    # represents both as arrays; validate that wire representation, not Python
    # container implementation details. This does not change any tile or score.
    try:
        v = json.loads(json.dumps(v, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        raise ValueError('천봉 JSON으로 표현할 수 없는 데이터입니다.') from None
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
    from paipu_vendor.mahjong_url_parser.urls import parse_replay_url
    from majsoul_client import fetch_record
    from tensoul.downloader import MajsoulPaipuDownloader
    return parse_replay_url, fetch_record, MajsoulPaipuDownloader


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
        _cleanup()
        if key not in auth_attempts and len(auth_attempts) >= 4096:
            raise RateLimited('요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.')
        marks = auth_attempts.setdefault(key, [])
        marks[:] = [x for x in marks if now - x < duration]
        if len(marks) >= limit:
            raise RateLimited("인증 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        marks.append(now)


def fetch_from_mahjongsoul(text: str, session: Session) -> dict:
    _converter()
    from paipu_vendor.mahjong_url_parser.urls import parse_replay_url
    from paipu_vendor.mahjong_url_parser.sources.yostar import YostarSession
    from regional_auth import regional_client
    from majsoul_client import fetch_record
    reference = parse_replay_url(extract_share_url(text))
    shared = service_account.owns(session)
    if not session.operation.acquire(timeout=5 if shared else 0):
        raise ValueError("같은 계정의 패보를 조회하고 있습니다. 완료 후 다시 시도해 주세요.")
    async def work():
        if shared and not service_account.owns(session):
            raise ValueError('공용 계정이 갱신되었습니다. 다시 조회해 주세요.')
        fresh = bool(session.fresh_token_at and time.monotonic() - session.fresh_token_at < 300)
        if fresh:
            sdk = YostarSession(session.uid, session.token, session.device_id)
        else:
            sdk = await regional_client(session.region, session.device_id).refresh(session.uid, session.token)
        # Persist a rotated SDK token even when game authentication fails.
        with lock:
            session.uid, session.token, session.device_id = sdk.uid, sdk.token, sdk.device_id
            session.fresh_token_at = 0
        if service_account.owns(session):
            service_account.save(session)
        payload = await fetch_record(reference.replay_id, sdk, session.region)
        with lock:
            session.game_verified = True
        return check_tenhou(payload)
    try:
        with service_account.vault_lock() if shared else nullcontext():
            if shared:
                try:
                    service_account.restore()
                except (VaultUnavailable, VaultCorrupt):
                    service_account.storage_error = True
                    raise
                if not service_account.owns(session) or not session.token:
                    from paipu_vendor.mahjong_url_parser.models import AuthenticationRequired
                    raise AuthenticationRequired(session.region)
            try:
                return asyncio.run(asyncio.wait_for(work(), timeout=100))
            except Exception as exc:
                if type(exc).__name__ == 'VerificationCodeRequired':
                    # Still under both locks: don't erase a newer token saved
                    # by another deployment after this request releases them.
                    service_account.invalidate(session)
                    session.uid, session.token, session.game_verified = '', '', False
                raise
    finally:
        session.operation.release()


def public_fetch_error(error: Exception) -> tuple[int, dict]:
    if type(error).__name__ == 'YostarApiError':
        return 502, {'code': 'SDK_REFRESH_REJECTED', 'server_code': error.code,
                     'error': 'Yostar가 저장된 세션의 자동 인증을 거부했습니다. 인증 정보는 보존했습니다. 잠시 후 다시 시도하고, 계속 실패하면 운영자 설정에서 이메일 재인증해 주세요.'}
    if type(error).__name__ == 'GameError':
        stage, code = error.stage, error.code
        message = {
            'oauth_auth': '게임 서버가 Yostar 세션을 거부했습니다. 해당 계정의 인증 지역과 세션을 확인해야 합니다.',
            'oauth_check': '게임 서버 OAuth 세션 확인에 실패했습니다.',
            'oauth_login': '게임 계정 로그인에 실패했습니다.',
            'client_version': '공식 작혼 리소스 배포에서 현재 클라이언트 버전을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.',
            'account_unbound': '이 Yostar 인증 지역에 연결된 작혼 계정이 없습니다. 공식 작혼에서 계정 연결을 확인해 주세요.',
            'conversion': '패보는 받았지만 천봉 JSON 변환 검증에 실패했습니다.',
            'fetch_record': '작혼 서버에서 해당 패보를 읽지 못했습니다.',
        }.get(stage, '작혼 서버 연결 또는 패보 응답 검증에 실패했습니다.')
        if code == 151:
            message = '게임 서버가 클라이언트 프로토콜 또는 버전을 거부했습니다. 서버 측 점검이 필요합니다.'
        return 502, {'code': 'GAME_' + stage.upper(), 'stage': stage,
                     'server_code': code, 'error': message + (f' (코드 {code})' if code else '')}
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
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def version_string(self):
        return 'PAIPU SELECT'

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'")
        if os.getenv('PUBLIC_HTTPS') == '1':
            self.send_header('Strict-Transport-Security', 'max-age=15552000')
        super().end_headers()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, format, *args):
        # Don't put OTP, e-mail or replay URL in logs.
        print('request', self.command, urlsplit(self.path).path)

    def json_reply(self, status: int, value: dict, *, sid: str | None = None):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store, private')
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
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise ValueError('요청 출처가 허용되지 않았습니다.')
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if origin:
            u = urlsplit(origin)
            if (u.netloc != host or u.scheme not in ('https', 'http') or
                    (os.getenv('PUBLIC_HTTPS') == '1' and u.scheme != 'https')):
                raise ValueError('요청 출처가 허용되지 않았습니다.')
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise ValueError('JSON 요청만 지원합니다.')
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            raise ValueError('잘못된 요청 길이입니다.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as exc:
            raise ValueError('잘못된 요청 길이입니다.') from exc
        if not 0 < length <= 16384:
            raise ValueError('요청이 너무 큽니다.')
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError('요청은 JSON 객체여야 합니다.')
        return value

    def _operator_authorized(self):
        if not service_account.configured:
            return True
        supplied = self.headers.get('X-Paipu-Operator-Key', '')
        return bool(32 <= len(OPERATOR_KEY) <= 128 and len(supplied) <= 128 and
                    secrets.compare_digest(supplied.encode('utf-8'), OPERATOR_KEY.encode('utf-8')))

    def do_HEAD(self):
        # HEAD must enforce the same public file boundary as GET.
        path = urlsplit(self.path).path
        if path not in STATIC_PATHS | {'/', '/index.html'}:
            self.send_error(404)
            return
        target = (PUBLIC / (path.lstrip('/') or 'index.html')).resolve()
        if not target.is_relative_to(PUBLIC.resolve()) or not target.is_file():
            self.send_error(404)
            return
        return super().do_HEAD()

    def do_GET(self):
        if urlsplit(self.path).path == '/api/health':
            from version_resolver import status as version_status
            self.json_reply(200, {'status': 'ok', 'kr_fetch_available': package_ready(),
                                  'url_fetch_available': package_ready(),
                                  'version': '3.2.1',
                                  'build_commit': BUILD,
                                  'gateway_probe': gateway_probe,
                                  'resolved_versions': version_status(),
                                  'auth_protocol': 'yostar-21-22-23-live-resource',
                                  'converter_installed': package_ready()})
            return
        if urlsplit(self.path).path == '/api/auth/status':
            _, s = self._get_session()
            self.json_reply(200, {'authenticated': bool(s and s.uid and s.token),
                                  'email': s.email if s and s.uid else '',
                                  'region': s.region if s and s.uid else 'kr',
                                  'game_authenticated': bool(s and s.game_verified),
                                  'operator_auth_required': service_account.configured,
                                  **service_account.status()})
            return
        self.path = urlsplit(self.path).path
        if self.path in ('/', '/index.html'):
            # A cached script from the previous deploy must not silently hide a
            # newly configured authentication mode. Bind assets to this build.
            html = (PUBLIC / 'index.html').read_text(encoding='utf-8')
            for name in ('app.js', 'converter.js', 'link-utils.js', 'i18n.js', 'styles.css'):
                html = html.replace(f'./{name}"', f'./{name}?v={BUILD}"')
            raw = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path not in STATIC_PATHS:
            return self.json_reply(404, {'error': '없는 경로입니다.'})
        path = (PUBLIC / self.path.lstrip('/')).resolve()
        if not path.is_relative_to(PUBLIC.resolve()) or not path.is_file():
            return self.json_reply(404, {'error': '없는 경로입니다.'})
        return super().do_GET()

    def do_POST(self):
        action = urlsplit(self.path).path
        s = None
        held_operation = None
        if action not in ('/api/auth/send-code', '/api/auth/verify', '/api/auth/logout', '/api/convert'):
            return self.json_reply(404, {'error': '없는 API입니다.'})
        try:
            body = self._read_request()
            if action.startswith('/api/auth/') and not self._operator_authorized():
                return self.json_reply(403, {'code': 'OPERATOR_AUTH_REQUIRED',
                    'error': '공용 계정의 인증 설정에는 운영자 인증키가 필요합니다.'})
            if action == '/api/auth/send-code':
                use_service = body.get('service_account') is True
                if use_service and not service_account.configured:
                    raise ValueError('공용 계정이 설정되지 않았습니다.')
                email = service_account.email if use_service else str(body.get('email', '')).strip().lower()
                region = service_account.region if use_service else str(body.get('region', 'kr')).lower()
                if region not in ('kr','jp','en'):
                    raise ValueError('인증 지역은 한국/일본/영문 중 선택해 주세요.')
                if not EMAIL.fullmatch(email) or len(email) > 254:
                    raise ValueError('올바른 Yostar 로그인 이메일을 입력해 주세요.')
                if not package_ready():
                    return self.json_reply(503, {'error': '서버 변환 라이브러리가 설치되지 않았습니다.'})
                sid, s = self._get_session(create=True)
                if not s.operation.acquire(blocking=False):
                    raise ValueError('인증 처리가 진행 중입니다. 잠시 후 다시 시도해 주세요.')
                held_operation = s.operation
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
                    s.fresh_token_at = 0
                    s.game_verified = False
                return self.json_reply(200, {'ok': True, 'message': 'Yostar 인증 메일을 보냈습니다.'}, sid=sid)

            sid, s = self._get_session()
            if action == '/api/convert':
                # Resolve and validate before touching the shared upstream account.
                url = extract_share_url(str(body.get('url', '')))
                _, host = parse_url(url)
                if host in ('game.maj-soul.com', 'game.maj-soul.net'):
                    raise ValueError('중국 서버 링크는 별도의 중국 서버 계정 인증이 필요합니다.')
                s = service_account.ready_session() or s
                if not s or not s.uid or not s.token:
                    message = ('공용 조회 계정의 최초 인증이 필요합니다. 운영자 설정 화면에서 인증해 주세요.'
                               if service_account.configured else '먼저 Yostar 이메일 인증을 완료해 주세요.')
                    return self.json_reply(401, {'error': message, 'needs_auth': True})
                if service_account.owns(s):
                    _throttle('public-fetch:' + self.client_address[0], 30, 60)
                result = fetch_from_mahjongsoul(url, s)
                return self.json_reply(200, result)
            if not s:
                return self.json_reply(401, {'error': 'Yostar 이메일 인증을 진행해 주세요.'})
            if action == '/api/auth/verify':
                if not s.operation.acquire(blocking=False):
                    raise ValueError('인증 처리가 진행 중입니다. 잠시 후 다시 시도해 주세요.')
                held_operation = s.operation
                code = str(body.get('code', '')).strip()
                if not re.fullmatch(r'[0-9]{4,10}', code) or not s.email or not s.device_id:
                    raise ValueError('이메일 인증코드를 입력해 주세요.')
                _throttle('verify:' + sid, 8, 900)
                _converter()
                from regional_auth import regional_client
                client = regional_client(s.region, s.device_id)
                with service_account.registration(s) as shared_registration:
                    verified = asyncio.run(asyncio.wait_for(client.exchange_email_code(s.email, code), timeout=50))
                    with lock:
                        s.uid, s.token, s.device_id = verified.uid, verified.token, verified.device_id
                        s.fresh_token_at = time.monotonic()
                        s.game_verified = False
                    enrolled = service_account.enroll(s, registered=True) if shared_registration else False
                return self.json_reply(200, {'ok': True, 'authenticated': True,
                                             'shared_enrolled': enrolled}, sid=sid)
            if action == '/api/auth/logout':
                with lock:
                    sessions.pop(sid, None)
                return self.json_reply(200, {'ok': True})
        except (VaultBusy, VaultUnavailable, VaultCorrupt) as exc:
            if not isinstance(exc, VaultBusy):
                service_account.storage_error = True
            return self.json_reply(503, {'code': 'ACCOUNT_STORAGE_UNAVAILABLE', 'error': str(exc)})
        except RateLimited:
            return self.json_reply(429, {'code': 'RATE_LIMITED', 'error': '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.'})
        except ValueError as exc:
            return self.json_reply(400, {'error': str(exc)})
        except asyncio.TimeoutError:
            return self.json_reply(504, {'error': '작혼 서버 응답 시간 초과입니다. 잠시 후 다시 시도해 주세요.'})
        except Exception as exc:
            # Return safe, actionable classifications, never auth tokens, stack or OTP.
            typ = type(exc).__name__
            if typ == 'VerificationCodeRequired':
                return self.json_reply(401, {'error': '저장된 인증 세션을 사용할 수 없습니다. 이메일 인증을 다시 진행해 주세요.', 'needs_auth': True})
            if typ in ('GameError', 'YostarApiError', 'RemoteReplayError', 'ReplayNotFoundError',
                       'AuthenticationRequired', 'VerificationCodeRequired'):
                if action.startswith('/api/auth'):
                    return self.json_reply(502, {'code': 'YOSTAR_AUTH_FAILED',
                                                 'error': 'Yostar 이메일 인증에 실패했습니다. 인증코드와 계정 지역을 확인해 주세요.',
                                                 'server_code': getattr(exc, 'code', 0)})
                status, data = public_fetch_error(exc)
                print('Replay fetch failed:', typ, data['code'])
                return self.json_reply(status, data)
            print('Internal error:', typ)
            return self.json_reply(500, {'error': '서버 내부 오류가 발생했습니다.'})
        finally:
            if held_operation:
                held_operation.release()


def probe_gateway():
    """One unauthenticated connection check on startup, never a login claim."""
    global gateway_probe
    async def probe():
        from majsoul_client import bootstrap, connect, profile_for, MSRPCChannel
        from contextlib import suppress
        profile = profile_for('kr')
        routes = await bootstrap(profile)
        channel = MSRPCChannel(routes[0][0])
        try:
            await connect(channel, profile, routes[0][1])
        finally:
            if channel._ws is not None:
                with suppress(Exception):
                    await channel.close()
    gateway_probe = {'status': 'checking', 'authenticated': False}
    try:
        asyncio.run(asyncio.wait_for(probe(), timeout=45))
        gateway_probe = {'status': 'connected', 'authenticated': False}
    except Exception as exc:
        gateway_probe = {'status': 'failed', 'authenticated': False,
                         'stage': getattr(exc, 'stage', 'connect'),
                         'error_type': type(exc).__name__, 'server_code': getattr(exc, 'code', 0)}
    print('Gateway probe:', gateway_probe, flush=True)


if __name__ == '__main__':
    validation_dsn = os.getenv('PAIPU_VALIDATION_DATABASE_URL', '')
    if validation_dsn:
        from verify_postgres_vault import verify
        try:
            validation = verify(validation_dsn, os.getenv('PAIPU_DATABASE_URL', ''), Session)
            print('Vault integration validation:', json.dumps(validation), flush=True)
        except Exception as exc:
            # No DSN, keys, SQL parameters or raw driver messages in logs.
            from postgres_vault import safe_database_error
            print('Vault integration validation failed:', json.dumps(safe_database_error(exc)), flush=True)
            raise SystemExit(1) from None
    threading.Thread(target=probe_gateway, daemon=True).start()
    port = int(os.getenv('PORT', '8765'))
    print(f'Runtime Python: {sys.version.split()[0]}', flush=True)
    print(f'Paipu Select started: http://0.0.0.0:{port}')
    BoundedHTTPServer(('0.0.0.0', port), Handler).serve_forever()
