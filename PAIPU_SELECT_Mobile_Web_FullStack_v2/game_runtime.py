"""One lazy event loop for request-driven game connections; no wake-up jobs."""
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
import threading


class GameRuntime:
    def __init__(self):
        self.lock = threading.Lock()
        self.loop = None
        self.thread = None
        self.work_lock = None

    def run(self, work, timeout=105):
        with self.lock:
            if self.loop is None:
                ready = threading.Event()
                def serve():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    self.loop = loop
                    self.work_lock = asyncio.Lock()
                    ready.set()
                    loop.run_forever()
                self.thread = threading.Thread(target=serve, name='paipu-game-loop', daemon=True)
                self.thread.start()
                ready.wait()
        async def serialized():
            started = False
            try:
                async with self.work_lock:
                    started = True
                    return await work
            finally:
                if not started:
                    work.close()
        future = asyncio.run_coroutine_threadsafe(serialized(), self.loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError('게임 서버 응답 시간 초과입니다.') from None
