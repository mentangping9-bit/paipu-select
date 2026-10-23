"""Bulk operator enrollment uses stubbed Yostar calls; never sends real mail."""
import json
import time
from unittest.mock import AsyncMock, patch

import server
import regional_auth
from service_account import AccountPool, ServiceAccount
from test_security import endpoint, request, KEY
from paipu_vendor.mahjong_url_parser.sources.yostar import YostarApiError, YostarSession


def accounts():
    return [ServiceAccount(f'enroll{i}@example.com','jp',server.Session) for i in range(1,21)]


def client():
    return type('Client',(),{
        'device_id':'test-device',
        'send_email_code':AsyncMock(),
        'exchange_email_code':AsyncMock(return_value=YostarSession('test-uid','test-token','test-device')),
    })()


def sender(port):
    cookie=''
    def post(path, data, key=KEY):
        nonlocal cookie
        status, headers, raw=request(port,path,data,{'X-Paipu-Operator-Key':key,'Cookie':cookie})
        if 'Set-Cookie' in headers:
            cookie=headers['Set-Cookie'].split(';',1)[0]
        return status,json.loads(raw)
    return post


def test_operator_can_enroll_twenty_and_resend_despite_old_mail_limits(endpoint):
    owners=accounts();sdk=client();post=sender(endpoint)
    now=time.monotonic()
    server.auth_attempts.update({'email:'+owners[0].email:[now]*4,'ip:127.0.0.1':[now]*10})
    with patch.object(server,'service_account',owners[0]),patch.object(server,'service_pool',AccountPool(owners)),patch.object(server,'OPERATOR_KEY',KEY),patch.object(server,'_converter'),patch.object(server,'package_ready',return_value=True),patch.object(regional_auth,'regional_client',return_value=sdk):
        assert post('/api/auth/send-code',{'service_account':True},key='wrong')[0]==403
        sdk.send_email_code.assert_not_awaited()
        # Same browser/IP, no clock advance: bypass both aggregate mail counts
        # and the old 60-second cooldown between different accounts.
        for slot in range(1,21):
            assert post('/api/auth/send-code',{'service_account':True,'account_slot':slot})[0]==200
        for _ in range(5):
            assert post('/api/auth/send-code',{'service_account':True,'account_slot':1})[0]==200
        assert sdk.send_email_code.await_count==25
        assert sdk.send_email_code.await_args.args==(owners[0].email,)
        # Provider rejections stay visible, and do not impose a local wait.
        sdk.send_email_code.side_effect=YostarApiError(300200,'test rejection')
        status,data=post('/api/auth/send-code',{'service_account':True})
        assert status==503 and data['server_code']==300200
        sdk.send_email_code.side_effect=None
        assert post('/api/auth/send-code',{'service_account':True})[0]==200
        # Exemption is not granted to arbitrary-address mail requests.
        assert post('/api/auth/send-code',{'email':'other@example.com','region':'jp'})[0]==400
        server.auth_attempts['ip:127.0.0.1']=[now]*10
        assert sender(endpoint)('/api/auth/send-code',{'email':'other@example.com','region':'jp'})[0]==429


def test_verification_budget_is_per_account_and_still_blocks_wrong_code_spam(endpoint):
    owners=accounts();sdk=client();post=sender(endpoint)
    with patch.object(server,'service_account',owners[0]),patch.object(server,'service_pool',AccountPool(owners)),patch.object(server,'OPERATOR_KEY',KEY),patch.object(server,'_converter'),patch.object(server,'package_ready',return_value=True),patch.object(regional_auth,'regional_client',return_value=sdk):
        # More than eight accounts must be verifiable in one browser session.
        for slot in range(1,21):
            assert post('/api/auth/send-code',{'service_account':True,'account_slot':slot})[0]==200
            status,data=post('/api/auth/verify',{'code':'123456'})
            assert status==200 and data['shared_enrolled']
        assert all(a.status()['shared_ready'] for a in owners)
        assert post('/api/auth/send-code',{'service_account':True,'account_slot':1})[0]==200
        sdk.exchange_email_code.side_effect=YostarApiError(400,'test wrong code')
        for _ in range(7):
            assert post('/api/auth/verify',{'code':'000000'})[0]==502
        assert post('/api/auth/verify',{'code':'000000'})[0]==429
        # Account 2 still has its own remaining allowance.
        assert post('/api/auth/send-code',{'service_account':True,'account_slot':2})[0]==200
        sdk.exchange_email_code.side_effect=None
        assert post('/api/auth/verify',{'code':'123456'})[0]==200
