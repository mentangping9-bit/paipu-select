"""Operator-configured one-shot replay diagnostic, never a public cooldown reset.

Claim inside the encrypted vault before I/O so overlapping deploys and restarts
cannot repeat it. No timers, automatic retries or provider payloads in logs.
"""
import os
import re

import account_usage


def diagnose_replay(pool, admission, normalize_url, fetch, *, revision=None, url=None):
    revision = os.getenv('PAIPU_REPLAY_DIAGNOSTIC_ID', '') if revision is None else revision
    url = os.getenv('PAIPU_REPLAY_DIAGNOSTIC_URL', '') if url is None else url
    if not revision or not url:
        return
    slot = None
    try:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', revision) or not pool.vault:
            raise ValueError()
        url = normalize_url(url)
        with pool.lock, pool.vault.locked():
            saved = pool.vault.load() or {'version':1}
            pool._restore_rotation(saved)
            usage = account_usage.state(saved, pool.clock())
            if usage.get('replay_diagnostic_revision') == revision:
                return
            ready = [(i+1, a) for i, a in enumerate(pool.accounts)
                     if a.status()['shared_ready'] and not a.unavailable_reason]
            if not ready:
                return
            slot, _ = min(ready, key=lambda item:item[1].cooldown_until)
            # This marker is bounded and survives primary/secondary token saves.
            # Deliberately don't retry even if a process stops after claiming.
            usage['replay_diagnostic_revision'] = revision
            pool.vault.save(saved)
        result, _ = admission.run(('diagnostic', revision), 'operator-diagnostic',
            lambda:pool.fetch(url, fetch, diagnostic_slot=slot))
        print('Replay diagnostic:', revision, 'slot', slot, 'success',
              'rounds', len(result.get('log', [])), flush=True)
    except Exception as error:
        stage = getattr(error, 'stage', None)
        if stage not in ('fetch_record', 'oauth_auth', 'oauth_check', 'oauth_login',
                         'sdk_login', 'sdk_refresh', 'account_unbound', 'client_version',
                         'gateway', 'connection', 'connection_result', 'conversion'):
            stage = 'unclassified'
        code = getattr(error, 'code', None)
        print('Replay diagnostic:', revision if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', revision) else 'invalid',
              'slot', slot or 0, 'failed', type(error).__name__, stage,
              code if type(code) is int else 0, flush=True)
