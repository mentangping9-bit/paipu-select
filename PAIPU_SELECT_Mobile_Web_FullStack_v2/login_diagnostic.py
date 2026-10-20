"""Bounded, persisted diagnostic for the two JP OAuth failures; no replay calls."""
import asyncio
from contextlib import suppress

REVISION = 'jp-oauth-20261020-jp-gateway'


async def probe_login(session, region):
    from majsoul_client import Profile, bootstrap, connect, login, MSRPCChannel, Lobby
    from version_resolver import resolve
    resolved = await resolve(region)
    profile = Profile(region, resolved['product'], resolved['resource'])
    endpoint, route = (await bootstrap(profile))[0]
    channel = MSRPCChannel(endpoint)
    try:
        await connect(channel, profile, route)
        await login(Lobby(channel), session, profile)
    finally:
        if channel._ws is not None:
            with suppress(Exception):
                await channel.close()


def diagnose_account(account, slot, probe=probe_login):
    if account.region != 'jp' or not account.vault:
        return
    with account.operation, account.vault_lock():
        account.restore()
        saved = account.vault.load() or {}
        if account.unavailable_reason != 'oauth_auth' or saved.get('login_diagnostic_revision') == REVISION:
            return
        session = account.session
        if not session or not session.uid or not session.token:
            return
        # Claim before network I/O, so restarts cannot repeat the same diagnostic.
        saved['login_diagnostic_revision'] = REVISION
        account.vault.save(saved)
        async def work():
            from regional_auth import regional_client
            sdk = await regional_client('jp', session.device_id).refresh(session.uid, session.token)
            session.uid, session.token, session.device_id = sdk.uid, sdk.token, sdk.device_id
            session.fresh_token_at = 0
            account.save(session)
            marked = account.vault.load()
            marked['login_diagnostic_revision'] = REVISION
            account.vault.save(marked)
            await probe(sdk, 'jp')
        try:
            asyncio.run(asyncio.wait_for(work(), timeout=90))
        except Exception as error:
            print('JP login diagnostic:', slot, type(error).__name__,
                  getattr(error, 'stage', 'transport'), getattr(error, 'code', 0), flush=True)
        else:
            account.unavailable_reason = ''
            session.game_verified = True
            account.save(session)
            print('JP login diagnostic:', slot, 'game_login_succeeded', flush=True)


def diagnose_pool(pool):
    for slot, account in enumerate(pool.accounts, 1):
        try:
            diagnose_account(account, slot)
        except Exception as error:
            print('JP login diagnostic unavailable:', slot, type(error).__name__, flush=True)
