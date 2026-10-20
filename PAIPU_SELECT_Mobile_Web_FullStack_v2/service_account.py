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


class SessionVault:
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
        if self.email and vault:
            saved = vault.load()
            if saved and saved.get('email') == self.email and saved.get('region') == region:
                fields = {k: saved.get(k, '') for k in ('uid', 'token', 'device_id')}
                if all(isinstance(v, str) and v for v in fields.values()):
                    self.session = session_factory(time.monotonic(), time.monotonic(),
                                                   email=self.email, region=region, **fields)
                    self.session.operation = self.operation

    @property
    def configured(self):
        return bool(self.email)

    def ready_session(self):
        with self.lock:
            s = self.session
            return s if s and s.uid and s.token else None

    def enroll(self, session):
        if not self.configured or session.email != self.email or session.region != self.region:
            return False
        with self.lock:
            # Separate from the operator's browser session: logout and TTL cleanup
            # must never clear the service account used by other visitors.
            s = self.session_factory(time.monotonic(), time.monotonic(), email=self.email,
                                     region=self.region, uid=session.uid, token=session.token,
                                     device_id=session.device_id,
                                     fresh_token_at=session.fresh_token_at)
            if not self.operation.acquire(blocking=False):
                raise ValueError('공용 계정 조회가 끝난 후 다시 인증해 주세요.')
            try:
                s.operation = self.operation
                self.save(s)
                self.session = s
            finally:
                self.operation.release()
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
        s = self.ready_session()
        return {'shared_configured': self.configured, 'shared_ready': s is not None,
                'shared_game_authenticated': bool(s and s.game_verified),
                'shared_session_storage': 'encrypted_file' if self.vault else 'memory'}
