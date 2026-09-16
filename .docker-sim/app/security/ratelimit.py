"""滑动窗口限流（内存态，单进程有效；多实例部署应换 Redis）。"""
import threading
import time


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window: int = 60):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits.get(key, [])
            q = [t for t in q if now - t < self.window]
            if len(q) >= self.limit:
                self._hits[key] = q
                return False
            q.append(now)
            self._hits[key] = q
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
