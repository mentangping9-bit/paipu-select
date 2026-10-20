"""Bound upstream work while allowing normal browser use and duplicate replays.

Only completed replay JSON is cached. No credentials or caller IPs are stored.
Counters/cache are intentionally process-local; session durability is separate.
"""
from collections import OrderedDict, deque
from concurrent.futures import Future, TimeoutError as FutureTimeout
import json
import math
import secrets
import threading
import time


class ReplayLimited(ValueError):
    def __init__(self, code, retry_after, status=429):
        self.code = code
        self.retry_after = max(1, math.ceil(retry_after))
        self.status = status
        super().__init__('요청이 많습니다. 안내된 시간 후 다시 시도해 주세요.')


class ReplayAdmission:
    def __init__(self, *, clock=time.monotonic, per_minute=12, per_hour=120,
                 global_per_minute=10, max_pending=5, queue_timeout=20,
                 cache_ttl=900, cache_bytes=8*1024*1024, cache_entries=64):
        self.clock = clock
        self.per_minute, self.per_hour = per_minute, per_hour
        self.global_per_minute = global_per_minute
        self.max_pending, self.queue_timeout = max_pending, queue_timeout
        self.cache_ttl, self.cache_bytes, self.cache_entries = cache_ttl, cache_bytes, cache_entries
        self.lock = threading.RLock()
        self.worker = threading.Lock()
        self.visitors = OrderedDict()
        self.upstream_marks = deque()
        self.cache = OrderedDict()
        self.cached_bytes = 0
        self.flights = {}
        self.active_visitors = {}
        self.joiners = 0

    def _visitor(self, visitor, now):
        marks = self.visitors.pop(visitor, deque())
        while marks and marks[0] <= now-3600:
            marks.popleft()
        self.visitors[visitor] = marks
        while len(self.visitors) > 4096:
            self.visitors.popitem(last=False)
        recent = [stamp for stamp in marks if stamp > now-60]
        if len(recent) >= self.per_minute:
            raise ReplayLimited('VISITOR_RATE_LIMITED', recent[-self.per_minute]+60-now)
        if len(marks) >= self.per_hour:
            raise ReplayLimited('VISITOR_RATE_LIMITED', marks[0]+3600-now)
        marks.append(now)

    def _read_cache(self, key, now):
        for expired in [k for k, (expiry, _) in self.cache.items() if expiry <= now]:
            _, raw = self.cache.pop(expired)
            self.cached_bytes -= len(raw)
        entry = self.cache.get(key)
        if entry:
            self.cache.move_to_end(key)
            return entry[1]
        return None

    def _save_cache(self, key, raw):
        # Skip exceptionally large records instead of letting one evict all data.
        if len(raw) > min(self.cache_bytes, 2*1024*1024):
            return
        previous = self.cache.pop(key, None)
        if previous:
            self.cached_bytes -= len(previous[1])
        self.cache[key] = (self.clock()+self.cache_ttl, raw)
        self.cached_bytes += len(raw)
        while self.cached_bytes > self.cache_bytes or len(self.cache) > self.cache_entries:
            _, (_, removed) = self.cache.popitem(last=False)
            self.cached_bytes -= len(removed)

    def run(self, key, visitor, fetch, *, charge=True):
        with self.lock:
            now = self.clock()
            if charge:
                self._visitor(visitor, now)
            raw = self._read_cache(key, now)
            if raw is not None:
                return json.loads(raw), 'HIT'
            future = self.flights.get(key)
            if future is not None:
                if self.joiners >= 8:
                    raise ReplayLimited('REPLAY_BUSY', 3, 503)
                self.joiners += 1
                leader = False
            else:
                if visitor in self.active_visitors or len(self.flights) >= self.max_pending:
                    raise ReplayLimited('REPLAY_BUSY', 3, 503)
                future = Future()
                self.flights[key] = future
                self.active_visitors[visitor] = key
                leader = True

        if not leader:
            try:
                # One bounded wait, no polling or repeated upstream calls.
                return json.loads(future.result(timeout=self.queue_timeout+110)), 'SHARED'
            except FutureTimeout:
                raise ReplayLimited('REPLAY_BUSY', 5, 503) from None
            finally:
                with self.lock:
                    self.joiners -= 1

        acquired = False
        try:
            acquired = self.worker.acquire(timeout=self.queue_timeout)
            if not acquired:
                raise ReplayLimited('REPLAY_BUSY', 5, 503)
            with self.lock:
                now = self.clock()
                while self.upstream_marks and self.upstream_marks[0] <= now-60:
                    self.upstream_marks.popleft()
                if len(self.upstream_marks) >= self.global_per_minute:
                    raise ReplayLimited('SERVICE_RATE_LIMITED', self.upstream_marks[0]+60-now)
                self.upstream_marks.append(now)
            # This callback has its own SDK/DB timeouts and cross-process lock.
            result = fetch()
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False,
                             separators=(',', ':')).encode('utf-8')
            with self.lock:
                self._save_cache(key, raw)
                future.set_result(raw)
            return json.loads(raw), 'MISS'
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            if acquired:
                self.worker.release()
            with self.lock:
                self.flights.pop(key, None)
                self.active_visitors.pop(visitor, None)


class ReplayQueue:
    """One bounded FIFO worker; HTTP handlers only submit or read their own ticket.

    Queue state/results expire in memory. The durable SDK session is independent.
    No polling operation calls the provider. Limited jobs retry only after a
    shared cooldown, with at most three provider attempts.
    """
    def __init__(self, admission, error_mapper, *, spacing=6, cooldown=60,
                 max_pending=20, ttl=600, result_bytes=8*1024*1024, max_wait=1800):
        self.admission, self.error_mapper = admission, error_mapper
        self.spacing, self.cooldown = spacing, cooldown
        self.max_pending, self.ttl, self.result_bytes = max_pending, ttl, result_bytes
        self.max_wait = max_wait
        self.condition = threading.Condition(admission.lock)
        self.pending = deque()
        self.jobs = OrderedDict()
        self.tickets = {}
        self.visitors = {}
        self.running = None
        self.thread = None
        self.last_start = None
        self.pause_until = 0
        self.saved_bytes = 0

    def _discard(self, key):
        job = self.jobs.pop(key)
        self.saved_bytes -= len(job.get('raw', b''))
        for visitor, ticket in job['watchers'].items():
            self.tickets.pop(ticket, None)
            if self.visitors.get(visitor) == key:
                self.visitors.pop(visitor, None)

    def _prune(self):
        now = self.admission.clock()
        for key, job in list(self.jobs.items()):
            if job['state'] == 'done' and now-job['finished'] >= self.ttl:
                self._discard(key)
        for key, job in list(self.jobs.items()):
            if len(self.jobs) <= 64 and self.saved_bytes <= self.result_bytes:
                break
            if job['state'] == 'done':
                self._discard(key)

    def _delay(self):
        now = self.admission.clock()
        marks = self.admission.upstream_marks
        while marks and marks[0] <= now-60:
            marks.popleft()
        delay = max(0, self.pause_until-now)
        if self.last_start is not None:
            delay = max(delay, self.last_start+self.spacing-now)
        if len(marks) >= self.admission.global_per_minute:
            delay = max(delay, marks[0]+60-now)
        return delay

    def _view(self, key, visitor):
        job = self.jobs[key]
        if job['state'] == 'done':
            if 'raw' in job:
                return 200, json.loads(job['raw'])
            return job['status'], dict(job['error'])
        if job['state'] == 'processing':
            position, seconds = 0, 0
        else:
            position = list(self.pending).index(key)+1
            seconds = math.ceil(self._delay()+(position-1)*self.spacing)
        return 202, {'job':job['watchers'][visitor], 'state':job['state'],
                     'position':position, 'wait_seconds':seconds,
                     'cooldown':self.pause_until > self.admission.clock(),
                     'poll_after':2, 'limit_per_minute':self.admission.global_per_minute}

    def submit(self, key, visitor, fetch):
        with self.condition:
            self._prune()
            self.admission._visitor(visitor, self.admission.clock())
            raw = self.admission._read_cache(key, self.admission.clock())
            if raw is not None:
                return 200, json.loads(raw), 'HIT'
            previous = self.visitors.get(visitor)
            if previous is not None and previous != key:
                raise ReplayLimited('REPLAY_ALREADY_QUEUED', 3, 429)
            job = self.jobs.get(key)
            if job is not None and job['state'] == 'done':
                # Success may have left the smaller cache; allow a new request,
                # without retaining or automatically retrying a failed job.
                self._discard(key)
                job = None
            if job is None:
                if len(self.tickets) >= 256:
                    raise ReplayLimited('REPLAY_QUEUE_FULL', 10, 503)
                if len(self.pending)+(self.running is not None) >= self.max_pending:
                    raise ReplayLimited('REPLAY_QUEUE_FULL', 10, 503)
                job = {'state':'queued', 'watchers':{}, 'fetch':fetch,
                       'submitted':self.admission.clock(), 'attempts':0}
                self.jobs[key] = job
                self.pending.append(key)
            if visitor not in job['watchers']:
                if len(job['watchers']) >= 9 or len(self.tickets) >= 256:
                    raise ReplayLimited('REPLAY_QUEUE_FULL', 10, 503)
                ticket = secrets.token_urlsafe(24)
                job['watchers'][visitor] = ticket
                self.tickets[ticket] = (key, visitor)
                self.visitors[visitor] = key
            result = self._view(key, visitor)
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._work, daemon=True,
                                               name='replay-queue')
                self.thread.start()
            self.condition.notify_all()
            return *result, 'QUEUED'

    def status(self, ticket, visitor):
        with self.condition:
            self._prune()
            pair = self.tickets.get(ticket)
            if pair is None or pair[1] != visitor:
                return 404, {'code':'REPLAY_QUEUE_EXPIRED',
                             'error':'대기 요청이 만료되었거나 서버가 재시작됐습니다. 다시 접수해 주세요.'}
            return self._view(pair[0], visitor)

    def _work(self):
        while True:
            with self.condition:
                if not self.pending:
                    self.thread = None
                    return
                first = self.jobs[self.pending[0]]
                if self.admission.clock()-first['submitted'] >= self.max_wait:
                    key = self.pending.popleft()
                    first.update(state='done', finished=self.admission.clock(), status=408,
                                 error={'code':'REPLAY_QUEUE_EXPIRED', 'error':'대기 시간이 만료됐습니다. 다시 접수해 주세요.'})
                    first.pop('fetch', None)
                    for visitor in first['watchers']:
                        self.visitors.pop(visitor, None)
                    continue
                delay = self._delay()
                if delay > 0:
                    self.condition.wait(timeout=min(delay, self.max_wait-(self.admission.clock()-first['submitted'])))
                    continue
                key = self.pending.popleft()
                job = self.jobs[key]
                self.running = key
                job['state'] = 'processing'
                self.last_start = self.admission.clock()
                job['attempts'] += 1
                fetch = job['fetch']
            retry = False
            try:
                # Admission still enforces the rolling cap as a second guard.
                result, _ = self.admission.run(key, 'queue-worker', fetch, charge=False)
                raw = json.dumps(result, ensure_ascii=False, allow_nan=False,
                                 separators=(',', ':')).encode('utf-8')
                if len(raw) > self.result_bytes:
                    raise ValueError('Replay result exceeds queue memory bound')
                status, error = 200, None
            except Exception as exc:
                raw = None
                status, error = self.error_mapper(exc)
                if getattr(exc, 'stage', None) == 'fetch_record' and getattr(exc, 'code', None) == 540:
                    with self.condition:
                        self.pause_until = self.admission.clock()+max(self.cooldown, getattr(exc, 'retry_after', 0))
                    retry = job['attempts'] < 3
                    status, error = 429, {'code':'UPSTREAM_REPLAY_LIMITED',
                        'server_code':540, 'retry_after':math.ceil(max(self.cooldown, getattr(exc, 'retry_after', 0))),
                        'error':'작혼의 패보 조회 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.'}
                elif type(exc).__name__ == 'AccountsCooling':
                    with self.condition:
                        self.pause_until = self.admission.clock()+exc.retry_after
                    job['attempts'] -= 1
                    retry = True
            finally:
                fetch = None
            with self.condition:
                if retry:
                    job['state'] = 'queued'
                    self.running = None
                    self.pending.appendleft(key)
                    self.condition.notify_all()
                    continue
                job.pop('fetch', None)
                job['state'], job['finished'] = 'done', self.admission.clock()
                if raw is not None:
                    job['raw'] = raw
                    self.saved_bytes += len(raw)
                else:
                    job['status'], job['error'] = status, error
                for visitor in job['watchers']:
                    if self.visitors.get(visitor) == key:
                        self.visitors.pop(visitor, None)
                self.running = None
                self._prune()
                self.condition.notify_all()
