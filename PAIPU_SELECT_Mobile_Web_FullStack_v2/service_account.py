"""Server-only service account and optional encrypted durable session file.

An explicitly configured email can enroll through the existing Yostar OTP flow.
Other accounts cannot replace it. Public visitors only receive readiness flags.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
from contextlib import contextmanager, nullcontext

from postgres_vault import VaultUnavailable, VaultCorrupt, VaultBusy


class SessionVault:
    storage = 'encrypted_file'
    def __init__(self, path: str, key: str, public_dir: Path):
        from cryptography.fernet import Fernet
        self.path = Path(path).resolve()
        if self.path.is_relative_to(public_dir.resolve()):
            raise ValueError('계정 저장 경로는 공개 폴더 외부여야 합니다.')
        self.cipher = Fernet(key.encode('ascii'))

    def load(self):
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            if len(raw) > 16384:
                raise ValueError()
            value = json.loads(self.cipher.decrypt(raw))
            if not isinstance(value, dict) or value.get('version') != 1:
                raise ValueError()
            return value
        except Exception:
            raise RuntimeError('공용 계정 저장 파일을 복원하지 못했습니다.') from None

    def save(self, value):
        raw = self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode())
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='.session-', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class ServiceAccount:
    def __init__(self, email, region, session_factory, vault=None):
        self.email = email.strip().lower()
        self.region = region
        self.vault = vault
        self.session_factory = session_factory
        self.session = None
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.storage_error = False
        if self.email and vault:
            try:
                self.restore()
            except (VaultUnavailable, VaultCorrupt, VaultBusy):
                # Keep the JSON-upload/UI path available during a DB outage.
                # Authenticated retrieval fails closed; never fall back to an
                # independent in-memory copy which could rotate stale tokens.
                self.storage_error = True

    def vault_lock(self):
        return self.vault.locked() if hasattr(self.vault, 'locked') else nullcontext()

    def restore(self):
        """Caller serializes mutation. Re-read under the cross-process lock."""
        if not self.vault:
            return
        saved = self.vault.load()
        with self.lock:
            if not saved:
                self.session = None
            else:
                if saved.get('email') != self.email or saved.get('region') != self.region:
                    raise VaultCorrupt('저장된 계정과 서버의 공용 계정 설정이 다릅니다.')
                fields = {k: saved.get(k, '') for k in ('uid', 'token', 'device_id')}
                if not all(isinstance(v, str) for v in fields.values()) or (
                        bool(fields['uid']) != bool(fields['token'])) or (
                        fields['uid'] and not fields['device_id']):
                    raise VaultCorrupt('저장된 계정 정보 형식이 올바르지 않습니다.')
                s = self.session
                if s is None:
                    s = self.session_factory(time.monotonic(), time.monotonic(),
                                             email=self.email, region=self.region)
                    s.operation = self.operation
                if any(getattr(s, k) != value for k, value in fields.items()):
                    s.fresh_token_at, s.game_verified = 0, False
                for k, value in fields.items():
                    setattr(s, k, value)
                self.session = s
            self.storage_error = False

    @property
    def configured(self):
        return bool(self.email)

    def ready_session(self):
        # A second deployment may have enrolled the account since startup.
        # This is on a real user request, never a scheduled wake-up job.
        if self.vault and (self.session is None or not self.session.token or self.storage_error):
            if not self.operation.acquire(timeout=5):
                raise ValueError('공용 계정 연결 처리가 진행 중입니다. 잠시 후 다시 시도해 주세요.')
            try:
                with self.vault_lock():
                    self.restore()
            finally:
                self.operation.release()
        with self.lock:
            s = self.session
            return s if s and s.uid and s.token else None

    @contextmanager
    def registration(self, session):
        matches = self.configured and session.email == self.email and session.region == self.region
        if not matches:
            yield False
            return
        if not self.operation.acquire(timeout=5):
            raise ValueError('공용 계정 조회가 끝난 후 다시 인증해 주세요.')
        try:
            with self.vault_lock():
                # Validate storage BEFORE exchanging the OTP/rotating tokens.
                self.restore()
                yield True
        finally:
            self.operation.release()

    def enroll(self, session, registered=False):
        if not registered:
            with self.registration(session) as matches:
                return self.enroll(session, registered=True) if matches else False
        # Separate from the operator's browser session: logout and TTL cleanup
        # must never clear the service account used by other visitors.
        s = self.session_factory(time.monotonic(), time.monotonic(), email=self.email,
                                 region=self.region, uid=session.uid, token=session.token,
                                 device_id=session.device_id,
                                 fresh_token_at=session.fresh_token_at)
        s.operation = self.operation
        self.save(s)
        with self.lock:
            self.session = s
        return True

    def owns(self, session):
        with self.lock:
            return session is not None and session is self.session

    def save(self, session):
        if self.vault:
            self.vault.save({'version': 1, 'email': self.email, 'region': self.region,
                             'uid': session.uid, 'token': session.token,
                             'device_id': session.device_id})

    def invalidate(self, session):
        with self.lock:
            if session is self.session:
                session.uid, session.token, session.game_verified = '', '', False
                self.save(session)

    def status(self):
        # Reporting status must not connect to the game/rotate credentials.
        with self.lock:
            s = self.session
            s = s if s and s.uid and s.token and not self.storage_error else None
        return {'shared_configured': self.configured, 'shared_ready': s is not None,
                'shared_game_authenticated': bool(s and s.game_verified),
                'shared_session_storage': self.vault.storage if self.vault else 'memory',
                'shared_storage_available': not self.storage_error}
