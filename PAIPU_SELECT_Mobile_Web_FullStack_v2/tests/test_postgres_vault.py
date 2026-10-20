"""Failure/concurrency coverage with a simulated DB, not a live DB claim."""
import threading
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
import psycopg
import pytest

import majsoul_client
import regional_auth
import server
from postgres_vault import PostgresVault, VaultUnavailable, VaultCorrupt
from service_account import ServiceAccount
from test_service_account import session, URL
from paipu_vendor.mahjong_url_parser.sources.yostar import YostarApiError, YostarSession


class SimulatedDatabase:
    def __init__(self):
        self.ciphertext = None
        self.lock = threading.Lock()
        self.connections = []
        self.fail = False

    def connect(self, **settings):
        if self.fail:
            raise psycopg.OperationalError('password=must-never-leak')
        assert settings['autocommit'] is True
        db = self

        class Connection:
            locked = False
            closed = False

            def execute(self, sql, params=None):
                assert not self.closed
                if 'pg_advisory_lock' in sql:
                    assert db.lock.acquire(timeout=2)
                    self.locked = True
                elif sql.startswith('UPDATE'):
                    assert self.locked
                    assert 'private-token' not in sql and '%s' in sql
                    db.ciphertext = params[0]
                elif sql.startswith('SELECT ciphertext'):
                    assert self.locked
                else:
                    raise AssertionError(sql)
                return self

            def fetchone(self):
                return (db.ciphertext,)

            @property
            def rowcount(self):
                return 1

            def close(self):
                self.closed = True
                if self.locked:
                    self.locked = False
                    db.lock.release()

        conn = Connection()
        self.connections.append(conn)
        return conn


@pytest.fixture
def database():
    db = SimulatedDatabase()
    with patch('psycopg.connect', side_effect=db.connect):
        yield db
    assert not db.lock.locked()
    assert all(c.closed for c in db.connections)


def vault(key=None):
    return PostgresVault('postgresql://runtime:private@ep-test.us-west-2.aws.neon.tech/neondb',
                         key or Fernet.generate_key().decode())


def manager(store):
    return ServiceAccount('service@example.com', 'kr', server.Session, store)


def test_ciphertext_only_restart_and_fail_closed(database):
    key = Fernet.generate_key().decode()
    store = vault(key)
    owner = manager(store)
    owner.enroll(session())
    assert 'private-token' not in database.ciphertext
    assert 'service@example.com' not in database.ciphertext
    restored = manager(vault(key))
    assert restored.ready_session().token == 'private-token'
    assert not restored.status()['shared_game_authenticated']
    corrupted = manager(vault())
    assert corrupted.status()['shared_storage_available'] is False
    with pytest.raises(VaultCorrupt):
        corrupted.enroll(session())
    assert restored.ready_session().token == 'private-token'


def test_direct_tls_connection_required():
    store = vault()
    assert store.settings['sslmode'] == 'verify-full'
    assert store.settings['sslrootcert'] == 'system'
    for dsn in ['postgresql://u:p@ep-test-pooler.aws.neon.tech/db',
                'postgresql://u:p@host:6543/db', 'service=unexpected',
                'host=expected hostaddr=127.0.0.1']:
        with pytest.raises(ValueError):
            PostgresVault(dsn, Fernet.generate_key().decode())


def test_latest_token_loaded_before_refresh_and_saved_before_game_call(database):
    store = vault()
    first = manager(store)
    first.enroll(session())
    second = manager(store)
    other = second.ready_session()
    other.token = 'newer-process-token'
    second.save(other)
    client = type('Client', (), {'refresh': AsyncMock(return_value=YostarSession(
        'private-uid', 'rotated-secret', 'private-device'))})()

    async def game_failure(*args):
        # The write is already committed, with the global lock still held.
        assert store.load()['token'] == 'rotated-secret'
        assert database.lock.locked()
        raise majsoul_client.GameError('oauth_auth', 110)

    with patch.object(server, 'service_account', first), patch.object(regional_auth, 'regional_client', return_value=client), patch.object(
            majsoul_client, 'fetch_record', new=game_failure):
        with pytest.raises(majsoul_client.GameError):
            server.fetch_from_mahjongsoul(URL, first.ready_session())
    client.refresh.assert_awaited_once_with('private-uid', 'newer-process-token')
    assert store.load()['token'] == 'rotated-secret'


def test_storage_outage_does_not_break_app_or_destroy_token(database):
    store = vault()
    owner = manager(store)
    owner.enroll(session())
    encrypted = database.ciphertext
    database.fail = True
    restarted = manager(store)
    assert not restarted.status()['shared_storage_available']
    with pytest.raises(VaultUnavailable, match='저장된 인증 정보는 보존'):
        restarted.ready_session()
    assert database.ciphertext == encrypted
    database.fail = False
    assert restarted.ready_session().token == 'private-token'


def test_sdk_error_and_malformed_response_preserve_credentials(database):
    owner = manager(vault())
    owner.enroll(session())
    client = regional_auth.regional_client('kr', 'private-device')
    error = YostarApiError(999999, 'unclassified provider error')
    with patch.object(client, '_post', new=AsyncMock(side_effect=error)), patch.object(
            regional_auth, 'regional_client', return_value=client), patch.object(server, 'service_account', owner):
        with pytest.raises(YostarApiError):
            server.fetch_from_mahjongsoul(URL, owner.ready_session())
    assert owner.vault.load()['token'] == 'private-token'
    assert not server.public_fetch_error(error)[1].get('needs_auth')
    with patch.object(client, '_post', new=AsyncMock(return_value={'Data': {}})):
        with pytest.raises(Exception, match='세션 정보가 없습니다'):
            __import__('asyncio').run(client.refresh('private-uid', 'private-token'))


def test_status_has_no_db_or_game_side_effects(database):
    owner = manager(vault())
    count = len(database.connections)
    for _ in range(5):
        assert owner.status()['shared_session_storage'] == 'encrypted_postgres'
    assert len(database.connections) == count


def test_two_deployments_cannot_refresh_the_same_snapshot(database):
    key = Fernet.generate_key().decode()
    first = vault(key)
    # Each process has its own vault/connection; they share only the DB lock.
    second = vault(key)
    original = {'version': 1, 'token': 'original'}
    first.save(original)
    started, acquired = threading.Event(), threading.Event()
    observed = []

    def contender():
        started.set()
        with second.locked():
            acquired.set()
            observed.append(second.load()['token'])

    with first.locked():
        thread = threading.Thread(target=contender)
        thread.start()
        assert started.wait(1)
        assert not acquired.wait(0.05)
        first.save({'version': 1, 'token': 'rotated-before-release'})
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert observed == ['rotated-before-release']


def test_http_storage_failure_is_safe_and_json_ui_still_served(database):
    import json
    from http.server import ThreadingHTTPServer
    import urllib.request
    import urllib.error

    owner = manager(vault())
    owner.enroll(session())
    database.fail = True
    owner.storage_error = True
    api = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{api.server_port}'
    try:
        with patch.object(server, 'service_account', owner):
            request = urllib.request.Request(base+'/api/convert', data=json.dumps({'url': URL}).encode(),
                                             headers={'Content-Type': 'application/json'})
            with pytest.raises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            assert caught.value.code == 503
            body = json.load(caught.value)
            assert body['code'] == 'ACCOUNT_STORAGE_UNAVAILABLE'
            assert 'password=' not in str(body) and 'private-token' not in str(body)
            assert urllib.request.urlopen(base+'/').status == 200
            status = json.load(urllib.request.urlopen(base+'/api/auth/status'))
            assert status['shared_storage_available'] is False
    finally:
        api.shutdown()
        thread.join()
        api.server_close()
