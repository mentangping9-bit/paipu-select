"""Conservative local policy, NOT a claim about Mahjong Soul's private quota.

All timestamps/counts live inside the existing encrypted usage row. Callers
serialize read/claim/outcome with the same advisory lock used for rotation.
No tokens, replay IDs, emails, IPs, timers or provider probes are stored here.
"""
import math
from postgres_vault import VaultCorrupt

MIN_GAP = 400
SHORT_WINDOW, SHORT_LIMIT = 600, 2
LONG_WINDOW, LONG_LIMIT = 21600, 18
REFILL_SECONDS, BURST = 1200, 3
MAX_LEVEL = 3
GLOBAL_MIN_GAP = 20
ERROR_WINDOW, RECOVERY_WINDOW = 600, 21600
GLOBAL_RECOVERY_SUCCESSES = 60


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def state(saved):
    usage = saved.setdefault('usage', {'version': 1, 'accounts': {}})
    if not isinstance(usage,dict) or usage.get('version')!=1 or not isinstance(usage.get('accounts'),dict):
        raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
    value = usage.setdefault('load_scheduler', {'version': 1, 'accounts': {},
        'last_start': 0, 'level': 0, 'last_error': 0, 'recovery_at': 0,
        'successes': 0, 'errors': []})
    if (not isinstance(value, dict) or value.get('version') != 1
        or not isinstance(value.get('accounts'), dict) or len(value['accounts']) > 20
        or type(value.get('level')) is not int or not 0 <= value['level'] <= MAX_LEVEL
        or any(not number(value.get(k)) for k in ('last_start', 'last_error', 'recovery_at'))
        or type(value.get('successes')) is not int or not 0 <= value['successes'] <= 1000000
        or not isinstance(value.get('errors'), list) or len(value['errors']) > 20):
        raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
    for item in value['errors']:
        if not isinstance(item,(list,tuple)) or len(item)!=2:
            raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
        slot,stamp=item
        if type(slot) is not int or not 1 <= slot <= 20 or not number(stamp):
            raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
    for slot, account in value['accounts'].items():
        if slot not in {str(i) for i in range(1,21)} or not isinstance(account, dict):
            raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
        if (any(not number(account.get(k)) for k in ('asof', 'credits', 'last', 'last_error', 'recovery_at'))
            or account['credits'] > BURST or type(account.get('level')) is not int
            or not 0 <= account['level'] <= MAX_LEVEL
            or type(account.get('probation')) is not bool
            or type(account.get('successes')) is not int or not 0 <= account['successes'] <= 1000000
            or not isinstance(account.get('history'), list) or len(account['history']) > LONG_LIMIT
            or any(not number(t) for t in account['history'])):
            raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
    return value


def account_state(saved, slot, now, legacy_limited=False):
    value = state(saved)
    saved['usage'].setdefault('started_at',now)
    value.setdefault('started_at',now)
    account = value['accounts'].get(str(slot))
    if account is None:
        old = saved.get('usage', {}).get('accounts', {}).get(str(slot), {})
        last = old.get('last_attempt_at', 0)
        if not number(last):raise VaultCorrupt('조회 부하 기록 형식이 올바르지 않습니다.')
        limited = legacy_limited or (old.get('last_error_code') == 540
            and old.get('last_failure_at', 0) > old.get('last_success_at', 0))
        # Unknown pre-upgrade history is not invented. Start with one credit;
        # a known unrecovered 540 starts in probation with a reduced refill.
        account = {'asof': now, 'credits': 1., 'last': last, 'history': [],
            'level': int(limited), 'probation': bool(limited),
            'last_error': now if limited else 0, 'recovery_at': now, 'successes': 0}
        value['accounts'][str(slot)] = account
    return account


def projected(account, now):
    capacity = 1 if account['probation'] else BURST
    period = REFILL_SECONDS * 2**account['level']
    credits = min(capacity, account['credits'] + max(0, now-account['asof'])/period)
    history = sorted(t for t in account['history'] if t > now-LONG_WINDOW)
    short = [t for t in history if t > now-SHORT_WINDOW]
    available = max(now, account['last']+MIN_GAP if account['last'] else now,
        now+max(0,1-credits)*period)
    if len(short) >= SHORT_LIMIT:available = max(available, short[-SHORT_LIMIT]+SHORT_WINDOW)
    if len(history) >= LONG_LIMIT:available = max(available, history[-LONG_LIMIT]+LONG_WINDOW)
    pressure = max(len(short)/SHORT_LIMIT, len(history)/LONG_LIMIT, 1-credits/capacity)
    return {'credits':credits, 'history':history, 'short':len(short),
        'available_at':available, 'pressure':pressure, 'refill_seconds':period}


def reconcile_recovered(saved, accounts, now):
    """Normalize old penalties only when persisted real success proves recovery.

    Never infer provider recovery from elapsed time, re-enrollment or a cache hit.
    Preserve histories, last attempt, global protection and earned credits.
    """
    raw = (saved or {}).get('usage', {}).get('load_scheduler')
    if raw is None:return []
    value = state(saved)
    changed = []
    for i,owner in enumerate(accounts):
        account = value['accounts'].get(str(i+1))
        success = getattr(owner,'last_success_at',0)
        if (account and (account['level'] or account['probation']) and number(success)
            and success > account['last_error'] and not owner.rate_limit_count
            and not owner.unavailable_reason and owner.cooldown_until <= now):
            credits = projected(account,now)['credits']
            account.update(level=0,probation=False,asof=max(now,account['asof']),
                credits=credits,recovery_at=now)
            changed.append(i+1)
    return changed


def plan(saved, accounts, candidates, now, cursor=0):
    reconcile_recovered(saved,accounts,now)
    value = state(saved)
    views = {}
    rate = 0.
    for i, owner in enumerate(accounts):
        account = account_state(saved, i+1, now, owner.rate_limit_count > 0)
        view = projected(account, now)
        views[i] = view
        if owner.status()['shared_ready'] and not owner.unavailable_reason and owner.cooldown_until <= now:
            rate += 1/view['refill_seconds']
    interval = max(GLOBAL_MIN_GAP, 1/rate if rate else GLOBAL_MIN_GAP)*2**value['level']
    global_at = value['last_start']+interval if value['last_start'] else now
    ready = [(i,a) for i,a in candidates if views[i]['available_at'] <= now+1e-6]
    wait = max(0, global_at-now)
    if not ready:
        wait = max(wait, min((views[i]['available_at']-now for i,a in candidates), default=0))
    # Expired holds receive a single real recovery opportunity. Historical
    # penalties must not permanently sort them behind every healthy account.
    chosen = min(ready, key=lambda item:(round(views[item[0]]['pressure'],9),
        value['accounts'][str(item[0]+1)]['last'], (item[0]-cursor)%len(accounts))) if ready and wait <= 1e-6 else None
    return chosen, max(0,wait), interval, views


def claim(saved, slot, now):
    value = state(saved);account = value['accounts'][str(slot)]
    view = projected(account, now)
    if view['available_at'] > now+1e-6:raise ValueError('조회 부하 예약 순서가 올바르지 않습니다.')
    account.update(asof=max(now,account['asof']),credits=max(0,view['credits']-1),
        last=now, history=view['history']+[now])
    value['last_start'] = now


def outcome(saved, slot, now, *, success=False, limited=False):
    value = state(saved)
    account = account_state(saved, slot, now)
    if limited:
        account.update(level=min(MAX_LEVEL,account['level']+1), credits=0., asof=now,
            probation=True, last_error=now, recovery_at=now, successes=0)
        errors = [(s,t) for s,t in value['errors'] if t > now-ERROR_WINDOW]
        errors.append((slot,now));value['errors'] = errors[-20:]
        value.update(last_error=now, recovery_at=now, successes=0)
        if len({s for s,t in errors}) >= 2:
            value['level'] = min(MAX_LEVEL,value['level']+1)
            value['errors'] = []
    elif success:
        # One real successful retrieval restores normal account treatment.
        # Discard holiday credits to prevent a post-rest catch-up burst.
        if account['probation'] or account['level']:
            account.update(level=0,probation=False,credits=0.,asof=now,recovery_at=now)
        account['successes'] = min(1000000,account['successes']+1)
        value['successes'] = min(1000000,value['successes']+1)
        if value['level'] and now-max(value['last_error'],value['recovery_at']) >= RECOVERY_WINDOW and value['successes'] >= GLOBAL_RECOVERY_SUCCESSES:
            value.update(level=value['level']-1,successes=0,recovery_at=now)
