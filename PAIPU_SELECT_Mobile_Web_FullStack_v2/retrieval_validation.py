"""Opt-in, durable one-shot validation. At most two normally admitted requests."""
import os
import re
import account_usage


def validate(pool, admission, normalize_url, fetch, connections, *, revision=None, urls=None):
    revision=os.getenv('PAIPU_REUSE_VALIDATION_ID','') if revision is None else revision
    urls=os.getenv('PAIPU_REUSE_VALIDATION_URLS','').splitlines() if urls is None else urls
    if not revision or not urls:
        return
    slot=0
    try:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',revision) or not pool.vault or len(urls)!=2:
            raise ValueError()
        from paipu_vendor.mahjong_url_parser.urls import parse_replay_url
        urls=[normalize_url(url) for url in urls]
        keys=[('international',parse_replay_url(url).replay_id) for url in urls]
        with pool.lock,pool.vault.locked():
            saved=pool.vault.load() or {'version':1}
            pool._restore_rotation(saved)
            usage=account_usage.state(saved,pool.clock())
            if usage.get('reuse_validation_revision')==revision:
                return
            ready=pool.eligible()
            if not ready:
                print('Replay reuse validation:',revision,'skipped no eligible account',flush=True)
                return
            index,_=min(ready,key=lambda item:(item[0]-pool.cursor)%len(pool.accounts))
            slot=index+1
            usage['reuse_validation_revision']=revision
            pool.vault.save(saved)
        before=connections.stats()
        for number,(url,key) in enumerate(zip(urls,keys),1):
            # Bounded private probe intentionally refreshes two cache entries.
            # Admission, all account holds and the 540 pause remain in force.
            result,cache=admission.run(key,'operator-reuse-validation',
                lambda:pool.fetch(url,fetch,preferred_slot=slot),read_cache=False)
            print('Replay reuse validation:',revision,'slot',slot,'replay',number,
                  'success rounds',len(result.get('log',[])),cache,flush=True)
        after=connections.stats()
        print('Replay reuse validation:',revision,'complete opened',after['opened']-before['opened'],
              'reused',after['reused']-before['reused'],flush=True)
    except Exception as error:
        stage=getattr(error,'stage','unclassified')
        if stage not in ('fetch_record','oauth_auth','oauth_check','oauth_login','sdk_login',
                         'sdk_refresh','account_unbound','client_version','gateway','connection',
                         'connection_result','conversion','record_shape','record_download','record_size'):
            stage='unclassified'
        code=getattr(error,'code',None)
        print('Replay reuse validation:',revision if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',revision) else 'invalid',
              'slot',slot,'failed',type(error).__name__,stage,code if type(code) is int else 0,flush=True)
