"""Shared, bounded replay safeguards. No provider calls or background timers."""
import math
from postgres_vault import VaultCorrupt

PER_MINUTE = 3
MIN_INTERVAL = 20
ACCOUNT_REST = 5*3600
LOCKED_THRESHOLD = 17
CIRCUIT_REST = 5*3600
CONGESTION_MESSAGE = '안정적인 서비스 제공을 위해 새로운 패보 조회를 일시적으로 중단했습니다. 안내된 시간 이후 다시 이용해 주세요.'


def valid_time(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0


def state(value=None):
    if value is not None and not isinstance(value,dict):
        raise VaultCorrupt('조회 제한 기록 형식이 올바르지 않습니다.')
    value = dict(value or {})
    value.setdefault('marks',[]);value.setdefault('pause_until',0)
    value.setdefault('circuit_until',0)
    value.setdefault('last_started_at',None)
    if (not isinstance(value['marks'],list) or len(value['marks'])>10
        or any(not valid_time(x) for x in value['marks'])
        or not valid_time(value['pause_until']) or not valid_time(value['circuit_until'])
        or (value['last_started_at'] is not None and not valid_time(value['last_started_at']))):
        raise VaultCorrupt('조회 제한 기록 형식이 올바르지 않습니다.')
    if value['last_started_at'] is None and value['marks']:
        value['last_started_at']=max(value['marks'])
    return value


def guard(value,now,*,limit=PER_MINUTE,min_interval=MIN_INTERVAL,admit=False):
    from replay_admission import ReplayLimited
    if value['circuit_until']>now:
        raise ReplayLimited('SERVER_CONGESTED',value['circuit_until']-now,503)
    if value['pause_until']>now:
        raise ReplayLimited('UPSTREAM_REPLAY_LIMITED',value['pause_until']-now)
    if not admit:return
    marks=sorted(x for x in value['marks'] if x>now-60)
    if len(marks)>=limit:
        raise ReplayLimited('SERVICE_RATE_LIMITED',marks[0]+60-now)
    if value['last_started_at'] is not None and now<value['last_started_at']+min_interval:
        raise ReplayLimited('SERVICE_RATE_LIMITED',value['last_started_at']+min_interval-now)
    value['marks']=marks+[now];value['last_started_at']=now


def evaluate(value,now,locked_count):
    if locked_count>=LOCKED_THRESHOLD and value['circuit_until']<=now:
        value['circuit_until']=now+CIRCUIT_REST
        return True
    return False


def outcome(value,now,*,success=False,locked_count=0):
    if success:
        return False
    value['pause_until']=max(value['pause_until'],now+60)
    return evaluate(value,now,locked_count)


def account_hold(account,usage=None):
    if not account or not account.get('rate_limit_count',0):return 0
    hold=account.get('rate_limit_until')
    if hold is not None:
        if not valid_time(hold):raise VaultCorrupt('계정 휴식 기록 형식이 올바르지 않습니다.')
        return hold
    # Upgrade only unrecovered legacy 540s, measured from their recorded failure,
    # never from restart time. A successful account is not put back into a hold.
    usage=usage or {}
    if not isinstance(usage,dict) or not valid_time(account.get('last_success_at',0)):
        raise VaultCorrupt('계정 휴식 기록 형식이 올바르지 않습니다.')
    failure=usage.get('last_failure_at',0)
    if (usage.get('last_error_code')==540 and valid_time(failure)
            and failure>account.get('last_success_at',0)):
        return failure+ACCOUNT_REST
    fallback=account.get('cooldown_until',0)
    if not valid_time(fallback):raise VaultCorrupt('계정 휴식 기록 형식이 올바르지 않습니다.')
    return fallback


def locked_accounts(saved,now):
    usage=(saved or {}).get('usage',{}).get('accounts',{})
    slots=dict((saved or {}).get('accounts',{}))
    if (saved or {}).get('email'):slots['1']=saved
    return sum(account_hold(value,usage.get(slot))>now for slot,value in slots.items())
