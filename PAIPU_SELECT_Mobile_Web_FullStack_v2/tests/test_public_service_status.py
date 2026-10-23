"""Anonymous protection status exposes no credentials and never probes the game."""
import json
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server
from postgres_vault import VaultUnavailable
from replay_admission import ReplayAdmission
from test_replay_store import storage
from test_circuit_protection import seed


def test_restart_snapshot_uses_persisted_deadline_and_database_clock(storage):
    db,make,_=seed(storage,17)
    make().policy()
    original=make().vault.load()
    assert make().public_status()=={'paused':True,'retry_after':18000}
    db.now+=123
    assert make().public_status()=={'paused':True,'retry_after':17877}
    assert make().vault.load()==original # status does not refresh credentials or extend pause
    db.now+=18000
    assert make().public_status()=={'paused':False,'retry_after':0}


def test_status_cache_coalesces_reads_and_preserves_unknown_state():
    admission=ReplayAdmission()
    with patch.object(admission,'durable') as durable,patch.object(server,'replay_admission',admission),patch.object(server.time,'monotonic',return_value=100) as clock:
        durable.public_status.return_value={'paused':True,'retry_after':18000}
        status=server.PublicServiceStatus()
        with ThreadPoolExecutor(max_workers=8) as workers:
            results=list(workers.map(lambda _:status.read(),range(20)))
        assert all(result==(True,{'paused':True,'retry_after':18000}) for result in results)
        durable.public_status.assert_called_once()
        clock.return_value=110
        assert status.read()==(True,{'paused':True,'retry_after':17990})
        clock.return_value=116;durable.public_status.side_effect=VaultUnavailable('private details')
        assert status.read()[0] is False


def test_anonymous_http_status_cors_allowlist_and_no_secrets(storage):
    db,make,_=seed(storage,17);make().policy()
    admission=ReplayAdmission(durable=make())
    api=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=api.serve_forever,daemon=True);thread.start()
    try:
        with patch.object(server,'replay_admission',admission),patch.object(server,'public_service_status',server.PublicServiceStatus()),patch.object(server,'fetch_from_mahjongsoul') as provider:
            req=urllib.request.Request(f'http://127.0.0.1:{api.server_port}/api/service/status',headers={'Origin':'https://paipu-select-web.onrender.com'})
            with urllib.request.urlopen(req) as response:
                assert response.status==200
                assert response.headers['Access-Control-Allow-Origin']=='https://paipu-select-web.onrender.com'
                assert json.load(response)=={'paused':True,'retry_after':18000}
            with urllib.request.urlopen(f'http://127.0.0.1:{api.server_port}/assets/mascot-apology.webp') as response:
                assert response.status==200 and response.headers['Content-Type']=='image/webp'
            provider.assert_not_called()
    finally:api.shutdown();api.server_close();thread.join(timeout=2)
