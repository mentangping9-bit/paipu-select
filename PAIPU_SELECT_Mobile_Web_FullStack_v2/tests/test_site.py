import sys, os, unittest, threading, json, urllib.request, urllib.error, http.cookiejar, time
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

URL='https://game.mahjongsoul.com/?paipu=261014-f0ee926e-6cbc-491b-8f6b-e1e460a2cdfe_a924951866'
FIXTURE = json.loads((Path(__file__).parent/'fixture.json').read_text())

class Basic(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(server.parse_url(URL)[0], '261014-f0ee926e-6cbc-491b-8f6b-e1e460a2cdfe_a924951866')
        for u in ['http://game.mahjongsoul.com/?paipu=x123456789012','https://evil.example/?paipu=x123456789012', 'https://user:pwd@game.mahjongsoul.com/?paipu=x123456789012','https://game.mahjongsoul.com/?paipu=bad']:
            with self.subTest(url=u), self.assertRaises(ValueError): server.parse_url(u)
    def test_shape(self):
        assert len(server.check_tenhou(FIXTURE)['log'])==10
        with self.assertRaises(ValueError): server.check_tenhou({'log':[1]})

@dataclass
class Cred:
    region:object=None
    email:str=''
    verification_code:str=''
    yostar_device_id:str=''
    yostar_uid:str=''
    yostar_token:str=''
class Region:
    JP='jp'; EN='en'
@dataclass
class Ref:
    source_region:str='jp'
@dataclass
class Result:
    payload:dict=None
    yostar_session:object=None
@dataclass
class Auth:
    uid:str='demo-uid'
    token:str='demo-token'
    device_id:str='device-1'
async def code_fn(region,email,device_id=''):
    assert '@' in email
    return 'device-1'
async def authenticate(c):
    assert c.verification_code=='123456'
    return Auth()
async def fetch(ref, credentials):
    assert ref.source_region=='en', 'Korean must allow EN fallback'
    assert credentials.yostar_token == 'demo-token'
    return Result(FIXTURE, Auth())

def fake_conv():return Cred,Region,Exception,code_fn,authenticate,fetch,lambda url:Ref()

class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patcher=patch.object(server,'_converter',fake_conv)
        cls.patcher.start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.worker.join(timeout=5);cls.server.server_close()
        cls.patcher.stop()
    def test_login_and_convert(self):
        jar=http.cookiejar.CookieJar()
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        def post(path,value):
            raw=json.dumps(value).encode()
            return json.load(opener.open(urllib.request.Request(self.url+path,data=raw,headers={'Content-Type':'application/json'})))
        self.assertTrue(json.load(opener.open(self.url+'/api/health'))['kr_fetch_available'])
        self.assertFalse(json.load(opener.open(self.url+'/api/auth/status'))['authenticated'])
        self.assertTrue(post('/api/auth/send-code',{'email':'sample@example.com'})['ok'])
        self.assertTrue(post('/api/auth/verify',{'code':'123456'})['authenticated'])
        self.assertTrue(json.load(opener.open(self.url+'/api/auth/status'))['authenticated'])
        self.assertEqual(len(post('/api/convert',{'url':URL})['log']),10)
        self.assertTrue(post('/api/auth/logout',{})['ok'])
        self.assertFalse(json.load(opener.open(self.url+'/api/auth/status'))['authenticated'])

if __name__=='__main__':unittest.main()
