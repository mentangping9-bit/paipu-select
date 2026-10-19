"""Offline regression test: do not quick-login over an immediately issued SDK token."""
import asyncio
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import regional_auth

class TestInitialToken(unittest.TestCase):
    def test_new_device_skips_quick_login_but_saved_device_refreshes(self):
        @dataclass
        class Session:
            uid: str
            token: str
            device_id: str

        models = ModuleType('mahjong_url_parser.models')
        models.RemoteReplayError = type('RemoteReplayError', (Exception,), {})
        models.ReplayNotFoundError = type('ReplayNotFoundError', (Exception,), {})
        models.ServerRegion = SimpleNamespace(JP='jp', EN='en')
        base = ModuleType('mahjong_url_parser')
        sources = ModuleType('mahjong_url_parser.sources')
        yostar = ModuleType('mahjong_url_parser.sources.yostar')
        yostar.YostarSession = Session
        majsoul = ModuleType('mahjong_url_parser.sources.majsoul')
        seen = []
        async def fetch(endpoint, reference, credentials, version, *, target_region, yostar_session):
            seen.append((target_region, yostar_session.token))
            return SimpleNamespace(payload={'log':[]}, yostar_session=yostar_session)
        majsoul._fetch_from_gateway = fetch
        sources.majsoul = majsoul

        calls = []
        class Client:
            async def refresh(self, uid, token):
                calls.append('quick-login')
                return Session(uid, 'refreshed-token', 'device')
        async def bootstrap(upstream, region):
            return 'WebGL_2022-0.16.213', [('wss://engs.mahjongsoul.com/gateway', 'kr-2')]
        credentials = SimpleNamespace(yostar_uid='uid', yostar_token='initial-token', yostar_device_id='device')
        modules = {'mahjong_url_parser':base,'mahjong_url_parser.models':models,
                   'mahjong_url_parser.sources':sources,'mahjong_url_parser.sources.yostar':yostar,
                   'mahjong_url_parser.sources.majsoul':majsoul}
        with patch.dict(sys.modules, modules), \
             patch.object(regional_auth, 'regional_client', lambda region, device: Client()), \
             patch.object(server, '_bootstrap_for_account', bootstrap):
            asyncio.run(server._fetch_by_region(None,credentials,'kr',use_fresh_session=True))
            self.assertEqual(calls, [])
            self.assertEqual(seen[-1], ('en','initial-token'))
            asyncio.run(server._fetch_by_region(None,credentials,'kr',use_fresh_session=False))
            self.assertEqual(calls, ['quick-login'])
            self.assertEqual(seen[-1], ('en','refreshed-token'))

if __name__ == '__main__':
    unittest.main()
