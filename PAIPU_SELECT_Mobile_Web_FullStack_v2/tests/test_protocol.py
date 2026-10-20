"""Offline protocol regressions; these do NOT prove successful live login."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ms import protocol_pb2 as pb
from majsoul_client import (GameError, connection_payload, login, profile_for,
                            safe_record_url, select_gateway_routes)
from regional_auth import regional_client


def test_connection_matches_published_capture():
    # Published successful July 2026 capture in InjusticeJudge issue #37.
    # Excludes only the outer RPC Wrapper, which ms-api serializes separately.
    assert connection_payload('en-2', 1785043692).hex() == '10011a04656e2d3220ecb596d3063203576562'


@pytest.mark.asyncio
@pytest.mark.parametrize('region,product,resource,oauth_type', [('kr','4.0.12','0.16.266',23),('jp','4.0.12','0.16.267',21),('en','4.0.10','0.16.266',22)])
async def test_yostar_oauth_uses_client_enum_and_separate_versions(region, product, resource, oauth_type):
    lobby=SimpleNamespace(
        oauth2_auth=AsyncMock(return_value=pb.ResOauth2Auth(access_token='oauth-token')),
        oauth2_check=AsyncMock(return_value=pb.ResOauth2Check(has_account=True)),
        oauth2_login=AsyncMock(return_value=pb.ResLogin(account_id=1)),
    )
    await login(lobby, SimpleNamespace(uid='sdk-id',token='sdk-session'), profile_for(region))
    auth=lobby.oauth2_auth.call_args.args[0]
    request=lobby.oauth2_login.call_args.args[0]
    assert auth.type==request.type==oauth_type
    assert auth.code=='sdk-session'
    assert auth.uid=='sdk-id'
    assert auth.client_version_string=='WebGL_2022-'+resource
    assert request.access_token=='oauth-token'
    assert request.client_version.resource==resource
    assert request.client_version.package==product
    assert request.tag==region
    assert request.reconnect is False


@pytest.mark.asyncio
async def test_oauth_failure_stops_before_login_and_contains_no_token():
    lobby=SimpleNamespace(oauth2_auth=AsyncMock(return_value=pb.ResOauth2Auth(error=pb.Error(code=110))),
                          oauth2_check=AsyncMock(),oauth2_login=AsyncMock())
    with pytest.raises(GameError) as error:
        await login(lobby,SimpleNamespace(uid='sensitive-id',token='sensitive-token'),profile_for('kr'))
    assert error.value.stage=='oauth_auth' and error.value.code==110
    assert 'sensitive' not in str(error.value)
    lobby.oauth2_check.assert_not_called()
    lobby.oauth2_login.assert_not_called()


def test_routes_and_download_urls_reject_untrusted_addresses():
    valid={'id':'en-1','domain':'engs.mahjongsoul.com:443','ssl':True}
    bad=[{**valid,'domain':x} for x in ['evil.example','engs.mahjongsoul.com.evil.test','127.0.0.1','engs.mahjongsoul.com:8443','jpgs.mahjongsoul.com']]
    assert select_gateway_routes([*bad,valid],'engs.mahjongsoul.com')==[('wss://engs.mahjongsoul.com','en-1')]
    for url in ['http://x.mahjongsoul.com/a','https://127.0.0.1/a','https://evil.example/a',
                'https://user:secret@x.mahjongsoul.com/a','https://x.mahjongsoul.com:443/a']:
        with pytest.raises(GameError):safe_record_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize('region,pid,language', [('kr','KR-MAJONGSOUL','kr'),('jp','JP-MJ','ja'),('en','US-MAJONGSOUL','en')])
async def test_sdk_http_signature_and_token_exchange(region,pid,language):
    # Real HTTP serialization to a local SDK stub, including Authorization signature.
    import hashlib,json
    from aiohttp import web
    from paipu_vendor.mahjong_url_parser.sources.yostar import SIGNING_SALT
    seen=[]
    async def endpoint(request):
        body=await request.text()
        auth=json.loads(request.headers['Authorization'])
        compact=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':'))
        assert auth['Sign']==hashlib.md5((compact(auth['Head'])+body+SIGNING_SALT).encode()).hexdigest().upper()
        seen.append((request.path,json.loads(body),auth['Head']))
        data={'Token':'otp-exchange'} if request.path.endswith('get-auth') else {'UserInfo':{'ID':'uid-1','Token':'device-session'}}
        return web.json_response({'Code':200,'Data':data})
    app=web.Application();app.router.add_post('/{tail:.*}',endpoint)
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    try:
        client=regional_client(region,'fixed-device')
        client.base_url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        await client.send_email_code('example@example.com')
        session=await client.exchange_email_code('example@example.com','123456')
        assert session.token=='device-session' and session.device_id=='fixed-device'
        assert seen[0][1]=={'Account':'example@example.com'}
        assert seen[2][1]=={'Type':'yostar','OpenID':'example@example.com','Token':'otp-exchange','Secret':'','CheckAccountPlus':0}
        assert all(item[2]['PID']==pid and item[2]['Lang']==language for item in seen)
        assert all('Token' not in item[2] for item in seen)
    finally:
        await runner.cleanup()


def test_project_not_found_is_server_configuration_error_not_invalid_otp():
    from server import public_fetch_error
    from paipu_vendor.mahjong_url_parser.sources.yostar import YostarApiError
    error=YostarApiError(300200,'private-provider-message')
    error.stage='exchange_code'
    status,data=public_fetch_error(error)
    assert status==503 and data['code']=='SDK_PROJECT_CONFIG_ERROR'
    assert data['stage']=='exchange_code' and 'private-provider-message' not in str(data)


def test_jp_gateway_matches_official_entrance_tail():
    routes=[{"id":"jp-1","domain":"jpgs.mahjongsoul.com:443","ssl":True}]
    assert select_gateway_routes(routes,"jpgs.mahjongsoul.com")==[("wss://jpgs.mahjongsoul.com/gateway","jp-1")]
