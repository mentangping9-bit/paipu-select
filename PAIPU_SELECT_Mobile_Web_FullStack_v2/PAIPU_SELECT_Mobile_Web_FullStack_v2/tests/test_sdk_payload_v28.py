"""Offline contract test: never performs remote authentication."""
import asyncio
from dataclasses import dataclass
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

root=Path(__file__).resolve().parents[1]
models=ModuleType('mahjong_url_parser.models')
class ServerRegion:
    JP='jp'
    EN='en'
models.ServerRegion=ServerRegion
@dataclass
class YostarSession:
    uid: str
    token: str
    device_id: str

class YostarClient:
    def __init__(self, region, *,device_id=''):
        self.device_id=device_id or 'stub-device'
        self.region=region
        self.sent=[]
    def _head(self,*,uid='',token=''):
        return {'Region':'JP','PID':'JP-MJ','Lang':'ja','Version':'4.16.0','DeviceID':self.device_id}
    async def _post(self,endpoint,payload,*,uid='',token=''):
        self.sent.append((endpoint,payload))
        if endpoint=='yostar/get-auth':return {'Data': {'Token':'otp-test-token'}}
        if endpoint=='user/login':return {'Data': {'UserInfo': {'ID':'test-user','Token':'session-token'}}}
        return {'Code':200}
ys=ModuleType('mahjong_url_parser.sources.yostar')
ys.YostarClient=YostarClient;ys.YostarSession=YostarSession
sys.modules['mahjong_url_parser']=ModuleType('mahjong_url_parser')
sys.modules['mahjong_url_parser.models']=models
sys.modules['mahjong_url_parser.sources']=ModuleType('mahjong_url_parser.sources')
sys.modules['mahjong_url_parser.sources.yostar']=ys
spec=importlib.util.spec_from_file_location('regional_auth',root/'regional_auth.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
for region,expected in [('kr',('KR','KR-MAJONGSOUL','kr')),('jp',('JP','JP-MAJONGSOUL','jp')),('en',('US','US-MAJONGSOUL','en'))]:
    c=mod.regional_client(region,'test-device')
    head=c._head()
    assert (head['Region'],head['PID'],head['Lang'])==expected
    async def run():
        await c.send_email_code('test@example.com')
        user=await c.exchange_email_code('test@example.com','123456')
        assert user.uid=='test-user' and user.token=='session-token' and user.device_id=='test-device'
    asyncio.run(run())
    assert c.sent==[
       ('yostar/send-code',{'Account':'test@example.com'}),
       ('yostar/get-auth',{'Account':'test@example.com','Code':'123456'}),
       ('user/login',{'Type':'yostar','OpenID':'test@example.com','Token':'otp-test-token','Secret':'','CheckAccountPlus':0})
    ],c.sent
assert "'version': '2.8'" in (root/'server.py').read_text()
print('v2.8 contract tests passed for KR, JP, EN, login session, metadata and version')
