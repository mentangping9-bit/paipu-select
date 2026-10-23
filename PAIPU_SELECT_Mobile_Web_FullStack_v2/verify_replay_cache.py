"""Real-driver verification on a separate branch, never the production auth row."""
from cryptography.fernet import Fernet
from psycopg.conninfo import conninfo_to_dict
from postgres_vault import PostgresVault
from replay_store import ReplayStore


def verify(test_dsn,production_dsn):
    test=conninfo_to_dict(test_dsn);production=conninfo_to_dict(production_dsn)
    if test.get('host','').replace('-pooler.','.')==production.get('host','').replace('-pooler.','.'):
        raise ValueError('A separate test branch is required')
    key=Fernet.generate_key().decode()
    vault=PostgresVault(test_dsn,key);store=ReplayStore(vault)
    cache_key=('integration-validation','replay-cache-v1')
    sample={'name':['A','B','C','D'],'title':['test',''], 'rule':{},'log':[[[0,0,0]]+[[]]*16]}
    store.put(cache_key,sample)
    assert ReplayStore(PostgresVault(test_dsn,key)).get(cache_key)==sample
    assert ReplayStore(PostgresVault(test_dsn,Fernet.generate_key().decode())).get(cache_key) is None
    with vault.locked():
        connection=vault.local.connection
        assert connection.pgconn.ssl_in_use
        assert connection.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()==(False,False)
        assert connection.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='paipu_private.replay_cache'::regclass").fetchone()==(True,True)
        stored=connection.execute('SELECT ciphertext FROM paipu_private.replay_cache WHERE cache_key=%s',(store.key(cache_key),)).fetchone()[0]
        assert '"name"' not in stored
    return {'status':'passed','tls':True,'restricted_role':True,'encrypted_roundtrip':True,
            'independent_connection_restore':True,'wrong_key_rejected':True,'rls':True}
