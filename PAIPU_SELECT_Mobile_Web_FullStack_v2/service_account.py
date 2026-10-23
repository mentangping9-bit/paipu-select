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
import account_usage
from contextlib import contextmanager, nullcontext

from postgres_vault import VaultUnavailable, VaultCorrupt, VaultBusy, MAX_CIPHERTEXT_BYTES

_UNSET = object()
MAX_ACCOUNTS = 20

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
            if len(raw) > MAX_CIPHERTEXT_BYTES:
                raise ValueError()
            value = json.loads(self.cipher.decrypt(raw))
            if not isinstance(value, dict) or value.get('version') != 1:
                raise ValueError()
            return value
        except Exception:
            raise RuntimeError('공용 계정 저장 파일을 복원하지 못했습니다.') from None

    def save(self, value):
        raw = self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode())
        if len(raw) > MAX_CIPHERTEXT_BYTES:
            raise VaultUnavailable('인증 정보가 저장소 크기 한도를 초과했습니다.')
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
        self.rate_limit_count = 0
        self.rate_limit_until = 0
        self.last_success_at = 0
        self.unavailable_reason = ''
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

    def restore(self, saved=_UNSET):
        """Caller serializes mutation. Re-read under the cross-process lock."""
        if not self.vault:
            return
        saved = self.vault.load() if saved is _UNSET else saved
        with self.lock:
            if not saved:
                self.session = None
                self.cooldown_until = 0
                self.rate_limit_count, self.last_success_at, self.unavailable_reason = 0, 0, ''
                self.rate_limit_until = 0
            else:
                if saved.get('email') != self.email or saved.get('region') != self.region:
                    raise VaultCorrupt('저장된 계정과 서버의 공용 계정 설정이 다릅니다.')
                cooldown = saved.get('cooldown_until', 0)
                if not isinstance(cooldown, (int, float)) or not 0 <= cooldown < 100000000000:
                    raise VaultCorrupt('계정 대기 정보 형식이 올바르지 않습니다.')
                self.cooldown_until = cooldown
                count = saved.get('rate_limit_count', 1 if cooldown else 0)
                success = saved.get('last_success_at', 0)
                reason = saved.get('unavailable_reason', '')
                if not isinstance(count, int) or not 0 <= count <= 1000 or not isinstance(success, (int,float)) or not 0 <= success < 100000000000 or reason not in ('', 'account_unbound', 'oauth_auth', 'oauth_check', 'oauth_login', 'session_auth'):
                    raise VaultCorrupt('계정 상태 정보 형식이 올바르지 않습니다.')
                self.rate_limit_count, self.last_success_at, self.unavailable_reason = count, success, reason
                from replay_policy import account_hold
                self.rate_limit_until=account_hold(saved)
                self.cooldown_until=max(self.cooldown_until,self.rate_limit_until)
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
        # Email authentication must not erase a provider's existing 540 hold.
        self.unavailable_reason = ''
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
                             'device_id': session.device_id, 'cooldown_until': self.cooldown_until,
                             'rate_limit_count': self.rate_limit_count, 'last_success_at':self.last_success_at,
                             'rate_limit_until':self.rate_limit_until,
                             'unavailable_reason': self.unavailable_reason})

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
    """Keep up to twenty encrypted profiles in the existing restricted DB row.

    Primary fields retain their legacy representation. Every merge occurs under
    the same advisory lock; replacing primary tokens preserves secondary slots.
    """
    def __init__(self, vault, slot, region=None):
        self.vault, self.slot, self.region = vault, str(slot), region
        self.storage = vault.storage

    def locked(self):
        return self.vault.locked()

    def _slot(self, saved):
        if not saved:
            return None
        if self.slot == '1':
            return saved if 'email' in saved else None
        slots = saved.get('accounts', {})
        if not isinstance(slots, dict) or any(key not in {str(i) for i in range(2, MAX_ACCOUNTS+1)} for key in slots):
            raise VaultCorrupt('저장된 조회 계정 슬롯이 올바르지 않습니다.')
        value = slots.get(self.slot)
        if value is not None and not isinstance(value, dict):
            raise VaultCorrupt('저장된 조회 계정 정보가 올바르지 않습니다.')
        return value

    def load(self):
        return self.load_from(self.vault.load())

    def load_from(self, saved):
        """Read one profile from an already locked, shared snapshot."""
        value = self._slot(saved)
        if value is not None and self.region is not None and value.get('region') != self.region:
            profiles = value.get('regional_profiles', {})
            if not isinstance(profiles, dict) or any(r not in ('kr','jp','en') for r in profiles):
                raise VaultCorrupt('저장된 인증 지역 정보가 올바르지 않습니다.')
            value=profiles.get(self.region)
            if value is not None and not isinstance(value,dict):
                raise VaultCorrupt('저장된 인증 지역 정보가 올바르지 않습니다.')
        if value is None:return None
        from replay_policy import account_hold
        usage=(saved or {}).get('usage',{}).get('accounts',{}).get(self.slot,{})
        hold=account_hold(value,usage)
        return {**value,'rate_limit_until':hold,'cooldown_until':max(value.get('cooldown_until',0),hold)}

    def save(self, value):
        with self.vault.locked():
            previous = self.vault.load() or {'version':1}
            prior_slot = self._slot(previous)
            merged_slot = dict(value)
            if prior_slot:
                profiles = dict(prior_slot.get('regional_profiles', {}))
                if prior_slot.get('region') != value.get('region'):
                    profiles[prior_slot['region']] = {k:v for k,v in prior_slot.items()
                        if k not in ('regional_profiles','accounts','rotation','usage')}
                profiles.pop(value.get('region'), None)
                if profiles:
                    merged_slot['regional_profiles'] = profiles
            if self.slot == '1':
                merged = merged_slot
                if previous.get('accounts'):
                    merged['accounts'] = previous['accounts']
                if 'rotation' in previous:
                    merged['rotation'] = previous['rotation']
                if 'usage' in previous:
                    merged['usage'] = previous['usage']
            else:
                merged = dict(previous)
                slots = dict(merged.get('accounts', {}))
                slots[self.slot] = merged_slot
                merged['accounts'] = slots
            self.vault.save(merged)


class AccountsCooling(RuntimeError):
    def __init__(self, seconds):
        self.retry_after = max(1, int(seconds)+1)
        super().__init__('조회 계정이 쉬는 중입니다.')


class AccountPool:
    def __init__(self, accounts, clock=time.time, cooldown=18000):
        self.accounts, self.clock, self.cooldown = accounts, clock, cooldown
        self.cursor = 0
        self.lock = threading.RLock()
        self.active_slot = self.last_slot = self.last_success_slot = None
        self.memory_usage = {}
        # Every SlotVault points at the same encrypted singleton row, even
        # when each account has its own PostgresVault connection factory.
        self.vault = accounts[0].vault.vault if accounts and all(
            isinstance(a.vault, SlotVault) for a in accounts) else None
        if self.vault:
            try:
                with self.vault.locked():
                    self._restore_rotation(self.vault.load())
            except (VaultUnavailable, VaultCorrupt, VaultBusy):
                # The UI and JSON uploads still work. A real retrieval must
                # reload durable state successfully before claiming any slot.
                pass

    def _restore_rotation(self, saved):
        for account in self.accounts:
            account.restore(account.vault.load_from(saved))
        state = (saved or {}).get('rotation')
        if state is None:
            # Upgrade the legacy row using actual successful retrieval times.
            # Prefer never-used slots; don't send the rotation back to slot 1.
            latest = max(range(len(self.accounts)), key=lambda i:self.accounts[i].last_success_at)
            used = self.accounts[latest].last_success_at > 0
            self.last_slot = self.last_success_slot = latest+1 if used else None
            self.cursor = (latest+1)%len(self.accounts) if used else 0
            return
        if (not isinstance(state, dict) or state.get('version') != 1 or
            any(isinstance(state.get(k), bool) or not isinstance(state.get(k), int)
                or not 1 <= state[k] <= MAX_ACCOUNTS for k in ('next_slot',)) or
            any(state.get(k) is not None and (isinstance(state[k], bool)
                or not isinstance(state[k], int) or not 1 <= state[k] <= MAX_ACCOUNTS)
                for k in ('last_used_slot','last_success_slot'))):
            raise VaultCorrupt('계정 순환 정보 형식이 올바르지 않습니다.')
        self.cursor = (state['next_slot']-1)%len(self.accounts)
        self.last_slot = state.get('last_used_slot')
        self.last_success_slot = state.get('last_success_slot')

    def _save_rotation(self, saved):
        value = dict(saved or {'version':1})
        value['rotation'] = {'version':1, 'next_slot':self.cursor+1,
                            'last_used_slot':self.last_slot,
                            'last_success_slot':self.last_success_slot}
        self.vault.save(value)

    def registration_account(self, slot):
        if not isinstance(slot, int) or isinstance(slot, bool) or not 1 <= slot <= len(self.accounts):
            raise ValueError('등록할 조회 계정을 선택해 주세요.')
        return self.accounts[slot-1]

    def owner(self, session):
        return next((account for account in self.accounts if account.owns(session)), None)

    def eligible(self, exclude=()):
        return [(i,a) for i,a in enumerate(self.accounts)
                    if i not in exclude and a.status()['shared_ready'] and a.cooldown_until <= self.clock()
                    and not a.unavailable_reason]

    def flags(self):
        states = [account.status() for account in self.accounts]
        return {'shared_ready':any(s['shared_ready'] for s in states),
                'shared_game_authenticated':any(s['shared_game_authenticated'] for s in states),
                'shared_accounts':[{'slot':i+1, 'region':self.accounts[i].region, 'ready':s['shared_ready'],
                    'cooling':self.accounts[i].cooldown_until > self.clock()}
                    for i,s in enumerate(states)]}

    def operator_status(self):
        with self.lock, self.vault.locked() if self.vault else nullcontext():
            saved = self.vault.load() if self.vault else self.memory_usage
            if self.vault:
                self._restore_rotation(saved)
            eligible = self.eligible()
            next_item = min(eligible, key=lambda item:(item[0]-self.cursor)%len(self.accounts)) if eligible else None
            return {'usage_started_at':(saved or {}).get('usage', {}).get('started_at'),
                    'usage_timezone':'Asia/Seoul', 'usage_day':account_usage.day_at(self.clock()),
                    'usage_persistent':bool(self.vault),
                    'active_slot':self.active_slot, 'last_used_slot':self.last_slot,
                    'last_success_slot':self.last_success_slot,
                    'next_slot':next_item[0]+1 if next_item else None,
                    'accounts':[{'slot':i+1, 'email':a.email, 'region':a.region,
                        'authenticated':a.status()['shared_ready'],
                        'cooldown_seconds':max(0,int(a.cooldown_until-self.clock())+1),
                        'rate_limit_count':a.rate_limit_count,
                        'rate_limit_seconds':max(0,int(a.rate_limit_until-self.clock())),
                        'last_success_at':a.last_success_at,
                        'usage':account_usage.snapshot(saved, i+1, self.clock()),
                        'unavailable_reason':a.unavailable_reason}
                        for i,a in enumerate(self.accounts)]}

    def queued_fetch(self, text, fetch):
        # Each queued replay gets its own bounded set. A failed slot is never
        # tried twice for that replay, even if its short cooldown expires.
        tried = set()
        return lambda: self.fetch(text, fetch, tried=tried)

    def fetch(self, text, fetch, *, tried=None, diagnostic_slot=None, preferred_slot=None):
        tried = tried if tried is not None else set()
        with self.lock, self.vault.locked() if self.vault else nullcontext():
            saved = self.vault.load() if self.vault else None
            if self.vault:
                self._restore_rotation(saved)
            eligible = self.eligible(tried)
            if preferred_slot is not None:
                # Validation can reuse one healthy connection; it cannot bypass
                # a provider hold or choose a slot through a public request.
                self.registration_account(preferred_slot)
                eligible = [(i,a) for i,a in eligible if i==preferred_slot-1]
            if diagnostic_slot is not None:
                # Internal one-shot diagnostic only. HTTP callers cannot set
                # this argument. Keep the persisted hold and normal outcome
                # handling; never clear all account cooldowns to run a probe.
                self.registration_account(diagnostic_slot)
                eligible = [(i,a) for i,a in eligible if i==diagnostic_slot-1]
            if not eligible:
                ready = [a for i, a in enumerate(self.accounts) if i not in tried
                         and a.status()['shared_ready'] and not a.unavailable_reason]
                if ready:
                    raise AccountsCooling(min(a.cooldown_until for a in ready)-self.clock())
                from paipu_vendor.mahjong_url_parser.models import AuthenticationRequired
                raise AuthenticationRequired(self.accounts[0].region)
            index, account = min(eligible, key=lambda item:(item[0]-self.cursor)%len(self.accounts))
            tried.add(index)
            self.cursor = (index+1)%len(self.accounts)
            self.last_slot = index+1
            saved = dict(saved or {'version':1}) if self.vault else self.memory_usage
            account_usage.record(saved, index+1, 'attempt', self.clock())
            if self.vault:
                # Commit before upstream I/O: failures and process restarts
                # advance the cursor too. Never hold this lock during fetch.
                self._save_rotation(saved)
            self.active_slot = index+1
        print('Replay account slot selected:', index+1, flush=True)
        succeeded, failure_code = False, None
        try:
            session = account.ready_session()
            if session is None:
                from paipu_vendor.mahjong_url_parser.models import AuthenticationRequired
                raise AuthenticationRequired(account.region)
            result = fetch(text, session, account)
            with account.operation, account.vault_lock():
                account.restore()
                account.last_success_at = self.clock()
                account.rate_limit_count, account.cooldown_until, account.unavailable_reason = 0, 0, ''
                account.rate_limit_until=0
                if account.session:
                    account.session.game_verified = True
                    account.save(account.session)
            with self.lock, self.vault.locked() if self.vault else nullcontext():
                if self.vault:
                    saved = self.vault.load()
                    self._restore_rotation(saved)
                self.last_success_slot = index+1
                account_usage.record(saved if self.vault else self.memory_usage,
                                     index+1, 'success', self.clock())
                if self.vault:
                    self._save_rotation(saved)
                succeeded = True
            print('Replay account slot succeeded:', index+1, flush=True)
            return result
        except Exception as exc:
            stage, code = getattr(exc, 'stage', None), getattr(exc, 'code', None)
            failure_code = code
            # Never log exception strings or provider payloads: both can contain
            # credentials. A numeric code and a known stage are enough to
            # distinguish replay throttling from login/network/storage errors.
            safe_stage = stage if stage in ('fetch_record', 'oauth_auth', 'oauth_check',
                'oauth_login', 'account_unbound', 'sdk_login', 'sdk_refresh',
                'client_version', 'gateway', 'connection', 'connection_result',
                'conversion', 'record_shape', 'record_download', 'record_size') else 'unclassified'
            print('Replay account failure:', index+1, type(exc).__name__, safe_stage,
                  code if type(code) is int else 0, flush=True)
            if stage == 'fetch_record' and code == 540:
                exc.account_slot=index+1
                with account.operation, account.vault_lock():
                    account.restore()
                    account.rate_limit_count = min(1000, account.rate_limit_count+1)
                    pause = max(18000,self.cooldown)
                    account.rate_limit_until=self.clock()+pause
                    account.cooldown_until = max(account.cooldown_until, self.clock()+pause)
                    if account.session:
                        account.save(account.session)
                exc.locked_accounts=sum(a.rate_limit_until>self.clock() for a in self.accounts)
                ready = [a for a in self.accounts if a.status()['shared_ready'] and not a.unavailable_reason]
                exc.retry_after = max(60, int(min(a.cooldown_until for a in ready)-self.clock())+1) if ready else 60
            elif stage in ('account_unbound','oauth_auth','oauth_check','oauth_login') and code != 151:
                with account.operation, account.vault_lock():
                    account.restore()
                    account.unavailable_reason = stage
                    if account.session:
                        account.save(account.session)
            elif type(exc).__name__ in ('VerificationCodeRequired','AuthenticationRequired'):
                with account.operation, account.vault_lock():
                    account.restore()
                    account.unavailable_reason = 'session_auth'
                    if account.session:
                        account.save(account.session)
            elif (type(exc).__name__ == 'YostarApiError' or
                  isinstance(exc, (TimeoutError, ConnectionError, OSError)) or
                  stage in ('gateway', 'connection', 'connection_result') or
                  _network_error(exc)):
                # An SDK rejection is not proof that the saved token expired.
                # Preserve it and temporarily rest this account; don't re-send OTP.
                with account.operation, account.vault_lock():
                    account.restore()
                    pause = 300 if type(exc).__name__ == 'YostarApiError' else 60
                    account.cooldown_until = max(account.cooldown_until, self.clock()+pause)
                    if account.session:
                        account.save(account.session)
            else:
                # Invalid replay, shared protocol/version or storage failure:
                # switching accounts cannot repair these errors.
                raise
            exc.can_retry = any(i not in tried and a.status()['shared_ready']
                                and not a.unavailable_reason
                                for i, a in enumerate(self.accounts))
            exc.retry_kind = 'account'
            raise
        finally:
            self.active_slot = None
            if not succeeded:
                try:
                    with self.lock, self.vault.locked() if self.vault else nullcontext():
                        saved = (self.vault.load() or {'version':1}) if self.vault else self.memory_usage
                        account_usage.record(saved, index+1, 'failure', self.clock(), failure_code)
                        if self.vault:
                            # Preserve the latest rotation written by other processes.
                            self.vault.save(saved)
                except (VaultUnavailable, VaultCorrupt, VaultBusy):
                    # Keep the original retrieval error; the durable attempt is
                    # reported as unfinished when its outcome cannot be saved.
                    print('Replay account outcome could not be stored:', index+1, flush=True)


def _network_error(error):
    import aiohttp
    return isinstance(error, aiohttp.ClientError)
