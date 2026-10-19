"""No-network regression tests against upstream documented SDK request shape."""
import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regional_auth import regional_client


class TestSDKPayload(unittest.TestCase):
    def test_email_login_matches_upstream_yostar_body(self):
        class Region:
            JP = 'jp'
            EN = 'en'
        class FakeYostar:
            def __init__(self, region, *, device_id=''):
                self.device_id = device_id
                self.region = region
                self.base_url = 'https://jp-sdk-api.yostarplat.com'
                self.calls = []
            def _head(self, *, uid='', token=''):
                return {'Region':'JP', 'PID':'JP-MJ', 'Lang':'ja'}
            async def _post(self, endpoint, body, **kwargs):
                self.calls.append((endpoint, body))
                if endpoint == 'yostar/get-auth':
                    return {'Data':{'Token':'one-time-email-exchange-token'}}
                if endpoint == 'user/login':
                    return {'Data':{'UserInfo':{'ID':'test-uid','Token':'game-session-token'}}}
                return {'Data':{}}
        class Session:
            def __init__(self, uid, token, device_id):
                self.uid=uid
                self.token=token
                self.device_id=device_id
        models=types.ModuleType('mahjong_url_parser.models')
        models.ServerRegion=Region
        yostar=types.ModuleType('mahjong_url_parser.sources.yostar')
        yostar.YostarClient=FakeYostar
        yostar.YostarSession=Session
        with patch.dict(sys.modules, {
            'mahjong_url_parser': types.ModuleType('mahjong_url_parser'),
            'mahjong_url_parser.models': models,
            'mahjong_url_parser.sources': types.ModuleType('mahjong_url_parser.sources'),
            'mahjong_url_parser.sources.yostar': yostar,
        }):
            for region in ('kr', 'jp', 'en'):
                client=regional_client(region, 'device-1')
                asyncio.run(client.send_email_code('example@example.com'))
                session=asyncio.run(client.exchange_email_code('example@example.com','123456'))
                self.assertEqual(session.token, 'game-session-token')
                self.assertEqual(client.calls[0][1],{
                    'Account':'example@example.com', 'Randstr':'', 'Ticket':''})
                self.assertEqual(client.calls[1][1], {
                    'Account':'example@example.com','Code':'123456'})
                endpoint, body=client.calls[2]
                self.assertEqual(endpoint, 'user/login')
                self.assertEqual(body['CheckAccount'],0)
                self.assertEqual(body['Type'],'yostar')
                self.assertEqual(body['UserName'],'example@example.com')
                self.assertEqual(body['Token'],'one-time-email-exchange-token')
                self.assertEqual(set(body['Geetest']), {
                    'CaptchaID','CaptchaOutput','GenTime','LotNumber','PassToken'})
                self.assertNotIn('CheckAccountPlus',body)

if __name__=='__main__':
    unittest.main()

class TestOAuthTypes(unittest.TestCase):
    def test_oauth_types_are_region_specific(self):
        from regional_auth import patch_connection_handshake
        class Region:
            JP = 'jp'
            EN = 'en'
        class Msg:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        class Login:
            def __init__(self):
                self.type=None
                self.access_token=''
                self.reconnect=False
                self.device=object()
                self.random_key=''
                self.client_version=types.SimpleNamespace(resource='')
                self.DESCRIPTOR=types.SimpleNamespace(fields_by_name={'client_version':1})
                self.currency_platforms=[]
        class Base:
            def __init__(self, endpoint=''):
                self._endpoint=endpoint
            async def connect(self, origin):
                pass
            async def send_request(self, method, packet):
                return b''
        class Lobby:
            async def oauth2_auth(self, req):
                self.type_seen=req.type
                return Msg(error=Msg(code=0), access_token='from-auth')
            async def oauth2_check(self, req):
                self.type_checked=req.type
                return Msg(error=Msg(code=0), has_account=True)
            async def oauth2_login(self, req):
                self.type_logged_in=req.type
                return Msg(error=Msg(code=0))
        pb=types.ModuleType('ms.protocol_pb2')
        pb.ReqOauth2Auth=Msg
        pb.ReqOauth2Check=Msg
        pb.ReqOauth2Login=Login
        pb.ResRequestConnection=type('Connection',(object,),{
            'ParseFromString':lambda self, s: None})
        ms=types.ModuleType('ms')
        ms.protocol_pb2=pb
        upstream=types.SimpleNamespace(
            MSRPCChannel=Base,
            ServerRegion=Region,
            _oauth_login=lambda *args:None,
            _fill_device=lambda d:None,
            _set_if_present=lambda *args:None,
            RemoteReplayError=RuntimeError,
        )
        with patch.dict(sys.modules, {'ms':ms,'ms.protocol_pb2':pb}):
            patch_connection_handshake(upstream)
            for region, expected in [(Region.JP,21),(Region.EN,22)]:
                lobby=Lobby()
                session=Msg(uid='test',token='not-a-real-token')
                asyncio.run(upstream._oauth_login(
                    lobby,session,'WebGL_2022-0.16.213',region))
                self.assertEqual((lobby.type_seen,lobby.type_checked,lobby.type_logged_in),
                                 (expected,expected,expected))
