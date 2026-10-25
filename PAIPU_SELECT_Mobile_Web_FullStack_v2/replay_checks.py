"""Private, explicitly requested, at-most-once account checks.

Selected checks bypass only the normal preference order, never a protection
hold, per-account budget or shared admission. No public trigger or secret data.
"""
import json
import os
import re
import time

from postgres_vault import VaultCorrupt
from replay_admission import ReplayLimited


class AlreadyChecked(RuntimeError):
    pass


def claimed(saved, revision, slot):
    return str(slot) in saved.get('usage', {}).get('replay_check_runs', {}).get(revision, {}).get('slots', {})


def claim(saved, revision, slot, now):
    if not isinstance(revision,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',revision):raise ValueError('Invalid check revision')
    runs=saved.setdefault('usage',{'version':1,'accounts':{}}).setdefault('replay_check_runs',{})
    if not isinstance(runs,dict) or len(runs)>8:raise VaultCorrupt('조회 점검 기록 형식이 올바르지 않습니다.')
    if revision not in runs:
        if len(runs)>=8:raise VaultCorrupt('조회 점검 기록 한도에 도달했습니다.')
        runs[revision]={'started_at':now,'slots':{}}
    slots=runs[revision]['slots']
    if not isinstance(slots,dict) or len(slots)>5:raise VaultCorrupt('조회 점검 기록 형식이 올바르지 않습니다.')
    if str(slot) in slots:raise AlreadyChecked()
    if len(slots)>=5:raise ValueError('At most five accounts per check')
    slots[str(slot)]={'state':'claimed','started_at':now}


def finish(pool,revision,slot,result):
    with pool.lock,pool.vault.locked():
        saved=pool.vault.load()
        row=saved['usage']['replay_check_runs'][revision]['slots'][str(slot)]
        row.update(result,finished_at=pool.clock())
        pool.vault.save(saved)


def emit(revision,slot,state,**details):
    print('Replay account check:',json.dumps(dict(revision=revision,slot=slot,state=state,**details),separators=(',',':')),flush=True)


def run(pool,admission,normalize_url,fetch, *, revision=None,url=None,slots=None,sleep=time.sleep,max_wait=1800):
    revision=os.getenv('PAIPU_SELECTED_CHECK_ID','') if revision is None else revision
    url=os.getenv('PAIPU_SELECTED_CHECK_URL','') if url is None else url
    slots=os.getenv('PAIPU_SELECTED_CHECK_SLOTS','') if slots is None else slots
    if not revision or not url or not slots:return
    try:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',revision) or not pool.vault:raise ValueError()
        if not isinstance(slots,str) or not re.fullmatch(r'\d{1,2}(,\d{1,2}){0,4}',slots):raise ValueError()
        slots=[int(x) for x in slots.split(',')]
        if len(set(slots))!=len(slots):raise ValueError()
        for slot in slots:pool.registration_account(slot)
        url=normalize_url(url)
    except Exception:
        emit('invalid',0,'invalid_configuration');return
    deadline=pool.clock()+min(1800,max_wait)
    emit(revision,0,'started',slots=slots)
    for slot in slots:
        while True:
            if pool.clock()>=deadline:
                emit(revision,slot,'not_attempted',reason='deadline');break
            try:
                with pool.lock,pool.vault.locked():
                    saved=pool.vault.load() or {'version':1}
                    pool._restore_rotation(saved)
                    if claimed(saved,revision,slot):
                        emit(revision,slot,'already_claimed');break
                    account=pool.registration_account(slot)
                    candidates=[item for item in pool.eligible() if item[0]==slot-1]
                    if not candidates:
                        emit(revision,slot,'not_attempted',reason='account_unavailable',
                            cooldown_seconds=max(0,int(account.cooldown_until-pool.clock())));break
                    wait=0
                    if pool.load_control:
                        import load_scheduler
                        _,wait,_,_=load_scheduler.plan(saved,pool.accounts,candidates,pool.clock(),pool.cursor)
                if wait>1e-6:
                    sleep(min(30,wait,max(0,deadline-pool.clock())));continue
                # A known cached replay is deliberately re-fetched for this
                # requested check. Quotas and all account holds still apply.
                result,_=admission.run(('selected-check',revision,slot),'selected-check',
                    lambda:pool.fetch(url,fetch,diagnostic_slot=slot,check_revision=revision),
                    charge=False,read_cache=False)
                outcome={'state':'success','rounds':len(result.get('log',[]))}
                finish(pool,revision,slot,outcome)
                emit(revision,slot,**outcome);break
            except AlreadyChecked:
                emit(revision,slot,'already_claimed');break
            except ReplayLimited as error:
                if error.code in ('ACCOUNT_LOAD_LIMITED','SERVICE_RATE_LIMITED','UPSTREAM_REPLAY_LIMITED','REPLAY_BUSY'):
                    sleep(min(30,error.retry_after,max(0,deadline-pool.clock())));continue
                emit(revision,slot,'not_attempted',reason=error.code);break
            except Exception as error:
                stage=getattr(error,'stage','unclassified')
                if stage not in ('fetch_record','oauth_auth','oauth_check','oauth_login','sdk_login',
                    'sdk_refresh','account_unbound','client_version','gateway','connection',
                    'connection_result','conversion','record_shape','record_download','record_size'):
                    stage='unclassified'
                code=getattr(error,'code',None)
                outcome={'state':'failed','stage':stage,'code':code if type(code) is int else 0,
                    'kind':type(error).__name__ if type(error).__name__ in ('GameError','YostarApiError','VaultUnavailable','VaultBusy','VaultCorrupt','TimeoutError') else 'OtherError'}
                try:
                    with pool.lock,pool.vault.locked():was_claimed=claimed(pool.vault.load() or {},revision,slot)
                    if was_claimed:finish(pool,revision,slot,outcome)
                except Exception:pass
                emit(revision,slot,**outcome);break
    emit(revision,0,'complete')
