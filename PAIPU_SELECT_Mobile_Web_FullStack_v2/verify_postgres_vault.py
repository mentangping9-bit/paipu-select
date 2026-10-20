"""Opt-in deployment validation against a separate, disposable DB branch.

No game-server requests, real account data, timers, or public test endpoint.
Set PAIPU_VALIDATION_DATABASE_URL only for an intentional verification deploy.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from cryptography.fernet import Fernet
from psycopg.conninfo import conninfo_to_dict

from postgres_vault import PostgresVault, VaultBusy, VaultCorrupt
from service_account import ServiceAccount


def verify(test_dsn, production_dsn, session_factory):
    if conninfo_to_dict(test_dsn).get('host') == conninfo_to_dict(production_dsn).get('host'):
        raise ValueError('Validation requires a separate database branch')
    key = Fernet.generate_key().decode()
    vault = PostgresVault(test_dsn, key)
    if vault.load() is not None:
        raise ValueError('Validation requires an empty test vault')
    sample = session_factory(time.monotonic(), time.monotonic(),
                             email='vault-validation@example.invalid', region='kr',
                             uid='paipu-validation-uid', token='paipu-validation-token',
                             device_id='paipu-validation-device')
    manager = ServiceAccount(sample.email, 'kr', session_factory, vault)
    wrote_sample = False
    try:
        assert manager.enroll(sample)
        wrote_sample = True
        with vault.locked():
            conn = vault.local.connection
            assert conn.pgconn.ssl_in_use
            role = conn.execute(
                'SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls '
                'FROM pg_roles WHERE rolname=current_user').fetchone()
            assert role == (False, False, False, False)
            assert conn.execute('SELECT count(*) FROM pg_auth_members '
                                'WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)').fetchone()[0] == 0
            permissions = conn.execute(
                "SELECT has_table_privilege(current_user,'paipu_private.service_sessions','INSERT'), "
                "has_table_privilege(current_user,'paipu_private.service_sessions','DELETE'), "
                "has_schema_privilege(current_user,'paipu_private','CREATE')").fetchone()
            assert permissions == (False, False, False)
            rls = conn.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                               "WHERE oid='paipu_private.service_sessions'::regclass").fetchone()
            assert rls == (True, True)
            encrypted = conn.execute("SELECT ciphertext FROM paipu_private.service_sessions "
                                     "WHERE account_key='majsoul'").fetchone()[0]
            assert sample.token not in encrypted and sample.email not in encrypted
        restored = ServiceAccount(sample.email, 'kr', session_factory, PostgresVault(test_dsn, key))
        assert restored.ready_session().token == sample.token
        assert not restored.status()['shared_game_authenticated']
        try:
            PostgresVault(test_dsn, Fernet.generate_key().decode()).load()
            raise AssertionError('Wrong key accepted')
        except VaultCorrupt:
            pass
        blocked = []

        def contender():
            try:
                PostgresVault(test_dsn, key).load()
            except VaultBusy:
                blocked.append(True)

        class DownstreamFailure(Exception):
            pass

        try:
            with vault.locked():
                thread = threading.Thread(target=contender, daemon=True)
                thread.start()
                thread.join(timeout=18)
                assert not thread.is_alive() and blocked == [True]
                sample.token = 'paipu-validation-rotated'
                manager.save(sample)
                raise DownstreamFailure()
        except DownstreamFailure:
            pass
        expected = vault.load()
        assert expected['token'] == sample.token
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--restore'],
                               input=json.dumps({'dsn': test_dsn, 'key': key, 'expected': expected}),
                               capture_output=True, text=True, timeout=25)
        assert child.returncode == 0 and child.stdout.strip() == 'RESTORE_PASS'
        return {'status': 'passed', 'tls': True, 'restricted_role': True,
                'encryption': True, 'new_process_restore': True,
                'cross_connection_lock': True, 'rotation_before_failure': True}
    finally:
        if wrote_sample:
            # This is our synthetic row on the isolated validation branch.
            with vault.locked():
                vault.local.connection.execute("UPDATE paipu_private.service_sessions SET ciphertext=NULL "
                                               "WHERE account_key='majsoul'")


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['--restore']:
            raise ValueError('Use the intentional deployment verification mode')
        config = json.load(sys.stdin)
        assert PostgresVault(config['dsn'], config['key']).load() == config['expected']
        print('RESTORE_PASS')
    except Exception as exc:
        print('RESTORE_FAILED', type(exc).__name__)
        sys.exit(1)
