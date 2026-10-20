"""Bound upstream work while allowing normal browser use and duplicate replays.

Only completed replay JSON is cached. No credentials or caller IPs are stored.
Counters/cache are intentionally process-local; session durability is separate.
"""
from collections import OrderedDict, deque
from concurrent.futures import Future, TimeoutError as FutureTimeout
import json
import math
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
                 global_per_minute=20, max_pending=5, queue_timeout=20,
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

    def run(self, key, visitor, fetch):
        with self.lock:
            now = self.clock()
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
