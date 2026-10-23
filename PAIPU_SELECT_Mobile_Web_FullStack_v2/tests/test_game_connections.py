"""Real local WebSocket protocol + SDK freshness tests, no provider calls."""
import asyncio
import base64
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
import websockets
from ms import protocol_pb2 as pb
import server
import majsoul_client as game
from service_account import ServiceAccount
from paipu_vendor.mahjong_url_parser.sources.yostar import YostarSession

URL='https://game.mahjongsoul.com/?paipu=261020-f5be3e18-149e-4a08-9060-9d304e07f891_a460096575'

@pytest.mark.asyncio
async def test_two_replays_use_one_login_on_real_local_socket_and_idle_closes():
    calls=Counter();connections=[]
    fixture=pb.ResGameRecord()
    fixture.ParseFromString(base64.b64decode(Path(__file__).with_name('converter_record.res.b64').read_text()))
    if not fixture.head.accounts:
        for seat in range(4):
            player=fixture.head.accounts.add(seat=seat, nickname=f'Player {seat+1}')
            player.level.id=10101
    async def provider(socket):
        connections.append(socket)
        async for packet in socket:
            request=pb.Wrapper();request.ParseFromString(packet[3:])
            method=request.name.split('.')[-1];calls[method]+=1
            if method=='requestConnection':response=pb.ResRequestConnection(result=1)
            elif method=='oauth2Auth':response=pb.ResOauth2Auth(access_token='fake-game-token')
            elif method=='oauth2Check':response=pb.ResOauth2Check(has_account=True)
            elif method=='oauth2Login':response=pb.ResLogin(account_id=123)
            elif method=='fetchGameRecord':
                body=pb.ReqGameRecord();body.ParseFromString(request.data)
                response=pb.ResGameRecord();response.CopyFrom(fixture);response.head.uuid=body.game_uuid
            else:raise AssertionError(method)
            wrapped=pb.Wrapper(data=response.SerializeToString()).SerializeToString()
            await socket.send(b'\x03'+packet[1:3]+wrapped)
    async with websockets.serve(provider,'127.0.0.1',0) as endpoint:
        port=endpoint.sockets[0].getsockname()[1]
        pool=game.GameConnections(idle_seconds=0.2)
        sdk=SimpleNamespace(uid='fake-uid',token='fake-token',device_id='fake-device')
        with patch.object(game,'bootstrap',new=AsyncMock(return_value=[(f'ws://127.0.0.1:{port}','jp-1')])):
            try:
                first=await pool.fetch('first-record',sdk,game.profile_for('jp'))
                second=await pool.fetch('second-record',sdk,game.profile_for('jp'))
                assert first['log'] and second['log']
                assert len(connections)==1
                assert calls['requestConnection']==calls['oauth2Auth']==calls['oauth2Check']==calls['oauth2Login']==1
                assert calls['fetchGameRecord']==2
                assert pool.stats()=={'opened':1,'reused':1,'closed':0,'active':1}
                await asyncio.sleep(0.3)
                assert pool.stats()['active']==0 and pool.stats()['closed']==1
                assert calls['fetchGameRecord']==2
            finally:await pool.close_all()

@pytest.mark.asyncio
async def test_token_rotation_logout_and_540_close_without_automatic_retry():
    channels=[];hooks=[]
    def channel(_):
        result=SimpleNamespace(_ws=object(),_msg_dispatcher=None,close=AsyncMock(),add_hook=lambda name,hook:hooks.append(hook))
        channels.append(result);return result
    sdk=SimpleNamespace(uid='uid',token='token-1',device_id='device')
    pool=game.GameConnections();profile=game.profile_for('kr')
    with patch.object(game,'RequestChannel',side_effect=channel),patch.object(game,'Lobby'),patch.object(game,'connect',new=AsyncMock()),patch.object(game,'login',new=AsyncMock()) as login,patch.object(game,'bootstrap',new=AsyncMock(return_value=[('wss://unused','en-1')])),patch.object(game,'_read_record',new=AsyncMock(return_value={'log':[1]})) as read:
        try:
            await pool.fetch('one',sdk,profile)
            sdk.token='token-2';await pool.fetch('two',sdk,profile)
            assert login.await_count==2 and channels[0].close.await_count==1
            await hooks[-1](b'');await pool.fetch('three',sdk,profile)
            assert login.await_count==3 and channels[1].close.await_count==1
            read.side_effect=game.GameError('fetch_record',540)
            with pytest.raises(game.GameError):await pool.fetch('limited',sdk,profile)
            assert read.await_count==4 and pool.stats()['active']==0
            assert channels[2].close.await_count==1
        finally:await pool.close_all()

def test_sdk_freshness_reuses_for_five_minutes_and_rechecks_after_expiry():
    owner=ServiceAccount('test@example.com','jp',server.Session)
    owner.enroll(server.Session(0,0,email=owner.email,region='jp',uid='test-uid',token='test-token',device_id='test-device'))
    sdk=SimpleNamespace(refresh=AsyncMock(return_value=YostarSession('test-uid','rotated-token','test-device')))
    fixture={'log':[[[0,0,0]]+[[]]*16]}
    with patch.object(server,'_converter'),patch('regional_auth.regional_client',return_value=sdk),patch.object(game,'fetch_record',new=AsyncMock(return_value=fixture)):
        server.fetch_from_mahjongsoul(URL,owner.session,owner)
        refreshed=owner.session.fresh_token_at
        for _ in range(2):server.fetch_from_mahjongsoul(URL,owner.session,owner)
        assert owner.session.fresh_token_at==refreshed
        assert sdk.refresh.await_count==1
        owner.session.fresh_token_at-=301
        server.fetch_from_mahjongsoul(URL,owner.session,owner)
        assert sdk.refresh.await_count==2
