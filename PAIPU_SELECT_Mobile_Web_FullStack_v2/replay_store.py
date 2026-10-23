"""Bounded encrypted replay cache and cross-deploy upstream admission.

Use the existing private DB/key. Cache keys contain only hashed replay IDs;
payloads never contain account credentials. No timers, polling or keep-alives.
"""
import hashlib
import json
import math
import zlib

from cryptography.fernet import InvalidToken
from postgres_vault import VaultUnavailable

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
        # Immutable SELECTs don't need the session advisory lock. Otherwise a
        # slow game request would block already-cached records for everyone.
        connection = None
        try:
            connection = self.vault.driver.connect(**self.vault.settings, autocommit=True)
            row = connection.execute(
                'SELECT ciphertext FROM paipu_private.replay_cache '
                'WHERE cache_key=%s AND expires_at>clock_timestamp()', (self.key(key),)).fetchone()
        except self.vault.driver.Error:
            raise VaultUnavailable('패보 캐시 저장소를 읽지 못했습니다.') from None
        finally:
            if connection is not None:
                connection.close()
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

    def policy(self, *, claim=False, limit=3, min_interval=20, success=None, check=False):
        import replay_policy
        import account_usage
        with self.vault.locked():
            try:
                now=float(self.vault.local.connection.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
            except self.vault.driver.Error:
                raise VaultUnavailable('조회 제한 저장소를 읽지 못했습니다.') from None
            saved=self.vault.load() or {'version':1}
            usage=account_usage.state(saved,now)
            value=replay_policy.state(usage.get('admission'))
            locked_count=replay_policy.locked_accounts(saved,now)
            opened=replay_policy.evaluate(value,now,locked_count)
            if opened:
                usage['admission']=value
                self.vault.save(saved)
            if claim or check:
                replay_policy.guard(value,now,limit=limit,min_interval=min_interval,admit=claim)
            if success is not None:
                opened=replay_policy.outcome(value,now,success=success,locked_count=locked_count) or opened
            if claim or success is not None:
                usage['admission']=value
                self.vault.save(saved)
            return {'paused':value['circuit_until']>now,
                    'retry_after':max(0,math.ceil(value['circuit_until']-now)),
                    'circuit_until':value['circuit_until'],'opened':opened,'locked_accounts':locked_count}

    def claim(self, limit=3, min_interval=20):
        return self.policy(claim=True,limit=limit,min_interval=min_interval)

    def check(self):
        import replay_policy
        saved,now=self.vault.protection_snapshot()
        value=replay_policy.state((saved or {}).get('usage',{}).get('admission'))
        if replay_policy.evaluate(value,now,replay_policy.locked_accounts(saved,now)):
            # Opening a previously unseen pause is serialized/persisted once.
            return self.policy(check=True)
        replay_policy.guard(value,now)

    def outcome(self, *, success=False):
        return self.policy(success=success)
