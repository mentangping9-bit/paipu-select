"""Encrypted singleton session storage; direct PostgreSQL connections only.

No pool, timers or keep-alive jobs. A session advisory lock spans SDK refresh
and replay retrieval, while each token write commits before game-server I/O.
Consequently a downstream failure cannot roll back a rotated SDK token.
"""
from contextlib import contextmanager
import json
import threading

from cryptography.fernet import Fernet, InvalidToken


class VaultUnavailable(RuntimeError):
    pass


class VaultCorrupt(RuntimeError):
    pass


class VaultBusy(RuntimeError):
    pass


def safe_database_error(error):
    """Classify driver failures without exposing DSNs, parameters or messages."""
    root = error
    seen = set()
    while root.__context__ is not None and id(root) not in seen:
        seen.add(id(root))
        root = root.__context__
    message = str(root).lower()
    reason = 'unclassified'
    for marker, code in (
        ('certificate verify failed', 'tls_certificate'),
        ('root certificate', 'tls_root_store'),
        ('failed to resolve', 'dns'),
        ('could not translate host', 'dns'),
        ('password authentication failed', 'authentication'),
        ('authentication failed', 'authentication'),
        ('timeout', 'timeout'),
        ('timed out', 'timeout'),
        ('connection refused', 'connection_refused'),
        ('server closed', 'connection_closed'),
        ('connection has been closed', 'connection_closed'),
        ('channel binding', 'channel_binding'),
        ('unsupported startup parameter', 'startup_parameter'),
    ):
        if marker in message:
            reason = code
            break
    return {'error_type': type(root).__name__, 'sqlstate': getattr(root, 'sqlstate', None),
            'reason': reason}


class PostgresVault:
    storage = 'encrypted_postgres'
    # One dedicated account per deployment/database. Not a secret.
    LOCK_ID = 57829917421901

    def __init__(self, dsn, key):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        try:
            settings = conninfo_to_dict(dsn)
            host = settings.get('host', '')
            # Transaction poolers cannot retain session advisory locks.
            if not host or ',' in host or '-pooler' in host or settings.get('port') == '6543':
                raise ValueError()
            if settings.get('hostaddr') or settings.get('service'):
                raise ValueError()
            if host not in ('localhost', '127.0.0.1', '::1'):
                settings.update(sslmode='verify-full', sslrootcert='system')
            settings.update(connect_timeout='10', application_name='paipu-session-vault',
                            options='-c statement_timeout=10000 -c lock_timeout=5000')
            self.cipher = Fernet(key.encode('ascii'))
        except Exception:
            raise ValueError('공용 계정 DB 연결 설정 또는 암호화 키가 올바르지 않습니다.') from None
        self.settings = settings
        self.local = threading.local()
        self.driver = psycopg

    @contextmanager
    def locked(self):
        # load/save in this thread reuse exactly the locked connection.
        if getattr(self.local, 'connection', None) is not None:
            yield
            return
        connection = None
        try:
            connection = self.driver.connect(**self.settings, autocommit=True)
            connection.execute('SELECT pg_advisory_lock(%s)', (self.LOCK_ID,))
        except self.driver.errors.LockNotAvailable:
            if connection:
                connection.close()
            raise VaultBusy('다른 서버에서 공용 계정을 사용 중입니다. 잠시 후 다시 시도해 주세요.') from None
        except self.driver.Error:
            if connection:
                connection.close()
            raise VaultUnavailable('계정 저장소에 연결하지 못했습니다. 저장된 인증 정보는 보존됩니다.') from None
        self.local.connection = connection
        try:
            yield
        finally:
            self.local.connection = None
            # Closing the direct connection releases the session lock even
            # after a query/network error. Never mask the original exception.
            connection.close()

    def load(self):
        with self.locked():
            try:
                row = self.local.connection.execute(
                    "SELECT ciphertext FROM paipu_private.service_sessions WHERE account_key = 'majsoul'"
                ).fetchone()
            except self.driver.Error:
                raise VaultUnavailable('계정 저장소를 읽지 못했습니다. 서버 저장 설정을 확인해 주세요.') from None
            if row is None:
                raise VaultUnavailable('계정 저장소의 초기 설정이 완료되지 않았습니다.')
            if row[0] is None:
                return None
            try:
                if not isinstance(row[0], str) or len(row[0]) > 16384:
                    raise ValueError()
                saved = json.loads(self.cipher.decrypt(row[0].encode('ascii')))
                if not isinstance(saved, dict) or saved.get('version') != 1:
                    raise ValueError()
                return saved
            except (InvalidToken, ValueError, TypeError, UnicodeError):
                raise VaultCorrupt('저장된 계정 정보를 복호화하지 못했습니다. 암호화 키를 확인해 주세요.') from None

    def save(self, value):
        raw = self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode('ascii')
        with self.locked():
            try:
                result = self.local.connection.execute(
                    "UPDATE paipu_private.service_sessions SET ciphertext=%s, updated_at=now() "
                    "WHERE account_key = 'majsoul'", (raw,))
                if result.rowcount != 1:
                    raise VaultUnavailable('계정 저장소의 초기 설정이 완료되지 않았습니다.')
            except self.driver.Error:
                raise VaultUnavailable('인증 정보를 영구 저장하지 못했습니다. 저장소 연결을 확인해 주세요.') from None
