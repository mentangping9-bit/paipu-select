"""Isolated fake upstream test: real EN-first orchestration without network or credentials."""
import asyncio
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class Region(StrEnum):
    EN = 'en'
    JP = 'jp'
class RemoteError(RuntimeError): pass
class NotFound(RemoteError): pass
class AuthError(RuntimeError): pass
class CodeError(RuntimeError): pass

@dataclass
class Reference:
    source_region: Region = Region.EN
@dataclass
class Session:
    uid: str = 'uid'
    token: str = 'token'
    device_id: str = 'device'
@dataclass
class Replay:
    payload: dict = None
    yostar_session: Session = None

class TestRegionOrder(unittest.TestCase):
    def _run_case(self, fail_en=False):
        checked=[]
        models=types.ModuleType('mahjong_url_parser.models')
        models.ServerRegion=Region
        models.RemoteReplayError=RemoteError
        models.ReplayNotFoundError=NotFound
        models.AuthenticationRequired=AuthError
        models.VerificationCodeRequired=CodeError
        provider=types.ModuleType('mahjong_url_parser.sources.majsoul')
        async def authenticate(c): return Session()
        async def bootstrap(region):
            checked.append(('bootstrap', region))
            return ('web-1', [f'wss://{region.value}.example'])
        async def fetch(endpoint, ref, credentials, version, *, target_region, yostar_session):
            checked.append(('fetch', target_region))
            self.assertEqual(endpoint, f'wss://{target_region.value}.example')
            self.assertEqual(yostar_session.uid,'uid')
            if target_region is Region.EN and fail_en:
                raise NotFound('EN game record not found')
            return Replay({'log': ['sample']}, yostar_session)
        provider.authenticate_yostar=authenticate
        provider._bootstrap=bootstrap
        provider._fetch_from_gateway=fetch
        sources=types.ModuleType('mahjong_url_parser.sources')
        sources.majsoul=provider
        pkg=types.ModuleType('mahjong_url_parser')
        pkg.__path__=[]
        sources.__path__=[]
        modules={
            'mahjong_url_parser':pkg,
            'mahjong_url_parser.models':models,
            'mahjong_url_parser.sources':sources,
            'mahjong_url_parser.sources.majsoul':provider,
        }
        with patch.dict(sys.modules,modules):
            replay=asyncio.run(server._fetch_global_region_first(Reference(), object()))
        return checked, replay

    def test_korean_link_fetches_global_first(self):
        calls, result=self._run_case()
        self.assertEqual(calls,[('bootstrap',Region.EN),('fetch',Region.EN)])
        self.assertEqual(result.payload['log'],['sample'])

    def test_korean_missing_then_japan_fallback(self):
        calls, result=self._run_case(fail_en=True)
        self.assertEqual(calls,[('bootstrap',Region.EN),('fetch',Region.EN),
                                ('bootstrap',Region.JP),('fetch',Region.JP)])
        self.assertEqual(result.payload['log'],['sample'])

if __name__ == '__main__': unittest.main()
