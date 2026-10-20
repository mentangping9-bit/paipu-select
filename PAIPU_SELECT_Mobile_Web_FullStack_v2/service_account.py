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
        self.cooldown_until = 0
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
                self.cooldown_until = 0
            else:
                if saved.get('email') != self.email or saved.get('region') != self.region:
                    raise VaultCorrupt('저장된 계정과 서버의 공용 계정 설정이 다릅니다.')
                cooldown = saved.get('cooldown_until', 0)
                if not isinstance(cooldown, (int, float)) or not 0 <= cooldown < 100000000000:
                    raise VaultCorrupt('계정 대기 정보 형식이 올바르지 않습니다.')
                self.cooldown_until = cooldown
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
                             'device_id': session.device_id, 'cooldown_until': self.cooldown_until})

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


class SlotVault:
    """Keep up to three encrypted profiles in the existing restricted DB row.

    Primary fields retain their legacy representation. Every merge occurs under
    the same advisory lock; replacing primary tokens preserves secondary slots.
    """
    def __init__(self, vault, slot):
        self.vault, self.slot = vault, str(slot)
        self.storage = vault.storage

    def locked(self):
        return self.vault.locked()

    def load(self):
        saved = self.vault.load()
        if not saved:
            return None
        if self.slot == '1':
            return saved if 'email' in saved else None
        slots = saved.get('accounts', {})
        if not isinstance(slots, dict) or any(key not in ('2','3') for key in slots):
            raise VaultCorrupt('저장된 조회 계정 슬롯이 올바르지 않습니다.')
        value = slots.get(self.slot)
        if value is not None and not isinstance(value, dict):
            raise VaultCorrupt('저장된 조회 계정 정보가 올바르지 않습니다.')
        return value

    def save(self, value):
        with self.vault.locked():
            previous = self.vault.load() or {'version':1}
            if self.slot == '1':
                merged = dict(value)
                if previous.get('accounts'):
                    merged['accounts'] = previous['accounts']
            else:
                merged = dict(previous)
                slots = dict(merged.get('accounts', {}))
                slots[self.slot] = value
                merged['accounts'] = slots
            self.vault.save(merged)


class AccountsCooling(RuntimeError):
    def __init__(self, seconds):
        self.retry_after = max(1, int(seconds)+1)
        super().__init__('조회 계정이 쉬는 중입니다.')


class AccountPool:
    def __init__(self, accounts, clock=time.time, cooldown=600):
        self.accounts, self.clock, self.cooldown = accounts, clock, cooldown
        self.cursor = 0
        self.lock = threading.RLock()

    def registration_account(self, slot):
        if not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= len(self.accounts):
            raise ValueError('등록할 조회 계정을 선택해 주세요.')
        return self.accounts[slot-1]

    def owner(self, session):
        return next((account for account in self.accounts if account.owns(session)), None)

    def flags(self):
        states = [account.status() for account in self.accounts]
        return {'shared_ready':any(s['shared_ready'] for s in states),
                'shared_game_authenticated':any(s['shared_game_authenticated'] for s in states),
                'shared_accounts':[{'slot':i+1, 'ready':s['shared_ready'],
                    'cooling':self.accounts[i].cooldown_until > self.clock()}
                    for i,s in enumerate(states)]}

    def fetch(self, text, fetch):
        with self.lock:
            eligible = [(i,a) for i,a in enumerate(self.accounts)
                        if a.status()['shared_ready'] and a.cooldown_until <= self.clock()]
            if not eligible:
                ready = [a for a in self.accounts if a.status()['shared_ready']]
                if ready:
                    raise AccountsCooling(min(a.cooldown_until for a in ready)-self.clock())
                from paipu_vendor.mahjong_url_parser.models import AuthenticationRequired
                raise AuthenticationRequired(self.accounts[0].region)
            index, account = min(eligible, key=lambda item:(item[0]-self.cursor)%len(self.accounts))
            self.cursor = (index+1)%len(self.accounts)
            session = account.ready_session()
        try:
            return fetch(text, session, account)
        except Exception as exc:
            if getattr(exc, 'stage', None) == 'fetch_record' and getattr(exc, 'code', None) == 540:
                # Persist the pause across Render restarts. This is a conservative
                # operating pause, not a claim about the provider's reset period.
                with account.operation, account.vault_lock():
                    account.restore()
                    account.cooldown_until = max(account.cooldown_until, self.clock()+self.cooldown)
                    if account.session:
                        account.save(account.session)
                ready = [a for a in self.accounts if a.status()['shared_ready']]
                exc.can_retry = any(a.cooldown_until <= self.clock() for a in ready)
                exc.retry_after = max(60, int(min(a.cooldown_until for a in ready)-self.clock())+1) if ready else 60
            raise
