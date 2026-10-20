from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock
import threading

from login_diagnostic import diagnose_account, REVISION
from majsoul_client import GameError


def test_diagnostic_persists_rotated_token_and_does_not_repeat(monkeypatch, capsys):
    class Vault:
        def __init__(self): self.data = {'token':'secret-old'}
        def load(self): return dict(self.data)
        def save(self, value): self.data = dict(value)
    vault = Vault()
    session = SimpleNamespace(uid='private-id', token='secret-old', device_id='private-device')
    def save(s): vault.save({'token':s.token})
    account = SimpleNamespace(region='jp', vault=vault, operation=threading.Lock(),
        vault_lock=lambda:nullcontext(), restore=lambda:None, unavailable_reason='oauth_auth',
        session=session, save=save)
    refresh = AsyncMock(return_value=SimpleNamespace(uid=session.uid, token='secret-new',device_id=session.device_id))
    monkeypatch.setattr('regional_auth.regional_client', lambda *args:SimpleNamespace(refresh=refresh))
    probe = AsyncMock(side_effect=GameError('oauth_auth',110))
    diagnose_account(account,2,probe)
    diagnose_account(account,2,probe)
    assert refresh.call_count == probe.call_count == 1
    assert vault.data == {'token':'secret-new', 'login_diagnostic_revision':REVISION}
    assert account.unavailable_reason == 'oauth_auth'
    output = capsys.readouterr().out
    assert 'oauth_auth 110' in output
    assert 'secret' not in output and 'private' not in output
