"""Bounded encrypted replay cache and cross-deploy upstream admission.

Use the existing private DB/key. Cache keys contain only hashed replay IDs;
payloads never contain account credentials. No timers, polling or keep-alives.
"""
import hashlib
import json
import math
import zlib

from cryptography.fernet import InvalidToken
from postgres_vault import VaultUnavailable, VaultCorrupt

MAX_JSON_BYTES = 12*1024*1024
MAX_CACHE_ENTRY = 2*1024*1024
MAX_CACHE_BYTES = 8*1024*1024
MAX_CACHE_ENTRIES = 128


class ReplayStore:
    def __init__(self, vault):
        self.vault = vault

    @staticmethod
    def key(key):
        return hashlib.sha256(json.dumps(key, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()

    def get(self, key):
        with self.vault.locked():
            try:
                row = self.vault.local.connection.execute(
                    'SELECT ciphertext FROM paipu_private.replay_cache '
                    'WHERE cache_key=%s AND expires_at>clock_timestamp()', (self.key(key),)).fetchone()
            except self.vault.driver.Error:
                raise VaultUnavailable('패보 캐시 저장소를 읽지 못했습니다.') from None
        if row is None:
            return None
        try:
            if not isinstance(row[0], str) or len(row[0]) > MAX_CACHE_ENTRY:
                return None
            packed = self.vault.cipher.decrypt(row[0].encode('ascii'))
            decoder = zlib.decompressobj()
            raw = decoder.decompress(packed, MAX_JSON_BYTES+1)
            if len(raw)>MAX_JSON_BYTES or not decoder.eof or decoder.unused_data:
                return None
            value = json.loads(raw)
            if not isinstance(value, dict) or not isinstance(value.get('log'), list) or not value['log']:
                return None
            return value
        except (InvalidToken, ValueError, TypeError, UnicodeError, zlib.error):
            # An unreadable optional cache entry never deletes SDK credentials.
            return None

    def put(self, key, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        if len(raw)>MAX_JSON_BYTES:
            return
        ciphertext = self.vault.cipher.encrypt(zlib.compress(raw, 6)).decode('ascii')
        if len(ciphertext)>MAX_CACHE_ENTRY:
            return
        with self.vault.locked():
            connection = self.vault.local.connection
            try:
                # One advisory lock bounds storage across processes. Eviction
                # affects only reproducible replay cache data, never sessions.
                connection.execute('DELETE FROM paipu_private.replay_cache WHERE expires_at<=clock_timestamp()')
                rows = connection.execute(
                    'SELECT cache_key,length(ciphertext) FROM paipu_private.replay_cache '
                    'WHERE cache_key<>%s ORDER BY cached_at,cache_key', (self.key(key),)).fetchall()
                size = sum(row[1] for row in rows)+len(ciphertext)
                count = len(rows)+1
                remove = []
                for cache_key, length in rows:
                    if size<=MAX_CACHE_BYTES and count<=MAX_CACHE_ENTRIES:
                        break
                    remove.append(cache_key);size-=length;count-=1
                if remove:
                    connection.execute('DELETE FROM paipu_private.replay_cache WHERE cache_key=ANY(%s)', (remove,))
                connection.execute(
                    'INSERT INTO paipu_private.replay_cache(cache_key,ciphertext,expires_at) '
                    "VALUES(%s,%s,clock_timestamp()+interval '30 days') "
                    'ON CONFLICT(cache_key) DO UPDATE SET ciphertext=excluded.ciphertext, '
                    'cached_at=clock_timestamp(),expires_at=excluded.expires_at', (self.key(key),ciphertext))
            except self.vault.driver.Error:
                raise VaultUnavailable('패보 캐시를 저장하지 못했습니다.') from None

    def claim(self, limit=10):
        from replay_admission import ReplayLimited
        import account_usage
        with self.vault.locked():
            try:
                now = float(self.vault.local.connection.execute(
                    'SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
            except self.vault.driver.Error:
                raise VaultUnavailable('조회 제한 저장소를 읽지 못했습니다.') from None
            saved = self.vault.load() or {'version':1}
            usage = account_usage.state(saved, now)
            state = usage.get('admission', {'marks':[], 'pause_until':0})
            if not isinstance(state, dict):
                raise VaultCorrupt('조회 제한 기록 형식이 올바르지 않습니다.')
            marks, pause = state.get('marks'), state.get('pause_until')
            if (not isinstance(marks,list) or len(marks)>10 or
                any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in marks) or
                type(pause) not in (int,float) or not math.isfinite(pause) or pause<0):
                raise VaultCorrupt('조회 제한 기록 형식이 올바르지 않습니다.')
            if pause>now:
                raise ReplayLimited('UPSTREAM_REPLAY_LIMITED', pause-now)
            marks = sorted(x for x in marks if x>now-60)
            if len(marks)>=min(10,limit):
                raise ReplayLimited('SERVICE_RATE_LIMITED', marks[0]+60-now)
            marks.append(now)
            usage['admission'] = {'marks':marks, 'pause_until':pause}
            self.vault.save(saved)

    def pause(self, seconds=60):
        import account_usage
        with self.vault.locked():
            try:
                now = float(self.vault.local.connection.execute(
                    'SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
            except self.vault.driver.Error:
                raise VaultUnavailable('조회 제한 저장소를 읽지 못했습니다.') from None
            saved = self.vault.load() or {'version':1}
            state = account_usage.state(saved, now).setdefault('admission', {'marks':[], 'pause_until':0})
            if (not isinstance(state, dict) or type(state.get('pause_until')) not in (int,float)
                    or not math.isfinite(state['pause_until']) or state['pause_until']<0):
                raise VaultCorrupt('조회 제한 기록 형식이 올바르지 않습니다.')
            state['pause_until'] = max(state['pause_until'], now+seconds)
            self.vault.save(saved)
