"""Bounded operator-only counters, stored inside the existing encrypted vault.

Attempts are recorded before provider I/O. Outcomes use their completion date;
an interrupted process leaves an unfinished attempt instead of inventing a result.
"""
from datetime import datetime, timezone, timedelta, date

KST = timezone(timedelta(hours=9))
DAILY_DAYS = 30


def day_at(now):
    return datetime.fromtimestamp(now, KST).date().isoformat()


def state(saved, now):
    usage = saved.setdefault('usage', {'version': 1, 'started_at': now, 'accounts': {}})
    if not isinstance(usage, dict) or usage.get('version') != 1 or not isinstance(usage.get('accounts'), dict):
        from postgres_vault import VaultCorrupt
        raise VaultCorrupt('계정 통계 형식이 올바르지 않습니다.')
    return usage


def record(saved, slot, event, now, error_code=None):
    usage = state(saved, now)
    if usage.get('started_at') is None:
        usage['started_at'] = now
    ensure_daily(saved, now)
    account = usage['accounts'].setdefault(str(slot), {'total': [0, 0, 0]})
    if account.get('day') != day_at(now):
        account.update(day=day_at(now), today=[0, 0, 0])
    index = ('attempt', 'success', 'failure').index(event)
    account['total'][index] += 1
    account['today'][index] += 1
    account['last_' + event + '_at'] = now
    daily = usage['daily']['days']
    daily.setdefault(day_at(now), [0, 0, 0])[index] += 1
    cutoff = (date.fromisoformat(day_at(now)) - timedelta(days=DAILY_DAYS-1)).isoformat()
    usage['daily']['days'] = {day:counts for day,counts in daily.items() if cutoff <= day <= day_at(now)}
    if event == 'failure':
        # Never persist exception strings, URLs, tokens or provider responses.
        account['last_error_code'] = error_code if type(error_code) is int else None


def ensure_daily(saved, now):
    """Seed only today's complete existing counters, never reconstruct old days.

    Called under the existing vault lock. No provider calls, identity tracking,
    schema changes, extra database connection or periodic jobs are involved.
    """
    saved.setdefault('usage', {'version':1, 'started_at':None, 'accounts':{}})
    usage = state(saved, now)
    if 'daily' in usage:
        return False
    today = day_at(now)
    counts = [0, 0, 0]
    for account in usage['accounts'].values():
        if account.get('day') == today:
            counts = [a+b for a,b in zip(counts, account.get('today', [0, 0, 0]))]
    usage['daily'] = {'started_day': today, 'days': {today: counts}}
    return True


def daily_snapshot(saved, now):
    usage = (saved or {}).get('usage', {})
    daily = usage.get('daily', {})
    today = date.fromisoformat(day_at(now))
    start = daily.get('started_day', today.isoformat())
    rows = []
    for offset in range(DAILY_DAYS-1, -1, -1):
        day = (today-timedelta(days=offset)).isoformat()
        known = day >= start
        counts = daily.get('days', {}).get(day, [0, 0, 0])
        rows.append({'day':day, 'known':known,
                     **dict(zip(('attempts','successes','failures'), counts if known else [None]*3))})
    return {'started_day':start, 'days':rows}


def snapshot(saved, slot, now):
    account = (saved or {}).get('usage', {}).get('accounts', {}).get(str(slot), {})
    total = account.get('total', [0, 0, 0])
    today = account.get('today', [0, 0, 0]) if account.get('day') == day_at(now) else [0, 0, 0]
    return {'total': dict(zip(('attempts', 'successes', 'failures'), total)),
            'today': dict(zip(('attempts', 'successes', 'failures'), today)),
            'unfinished': max(0, total[0] - total[1] - total[2]),
            'last_attempt_at': account.get('last_attempt_at'),
            'last_failure_at': account.get('last_failure_at'),
            'last_error_code': account.get('last_error_code')}
