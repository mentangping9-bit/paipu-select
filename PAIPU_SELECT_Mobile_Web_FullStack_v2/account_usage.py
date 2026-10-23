"""Bounded operator-only counters, stored inside the existing encrypted vault.

Attempts are recorded before provider I/O. Outcomes use their completion date;
an interrupted process leaves an unfinished attempt instead of inventing a result.
"""
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


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
    account = usage['accounts'].setdefault(str(slot), {'total': [0, 0, 0]})
    if account.get('day') != day_at(now):
        account.update(day=day_at(now), today=[0, 0, 0])
    index = ('attempt', 'success', 'failure').index(event)
    account['total'][index] += 1
    account['today'][index] += 1
    account['last_' + event + '_at'] = now
    if event == 'failure':
        # Never persist exception strings, URLs, tokens or provider responses.
        account['last_error_code'] = error_code if type(error_code) is int else None


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
