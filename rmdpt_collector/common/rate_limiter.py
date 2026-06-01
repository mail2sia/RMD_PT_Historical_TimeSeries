import time, random, threading

class DomainRateLimiter:
    def __init__(self, per_host_min_interval: dict[str,float] | None = None,
                 default_min: float = 1.0, default_max: float = 2.0):
        self._per_host = per_host_min_interval or {}
        self._def_min = default_min
        self._def_max = max(default_min, default_max)
        self._last = {}
        self._locks = {}

    def wait(self, domain: str):
        if domain not in self._locks:
            self._locks[domain] = threading.Lock()
        with self._locks[domain]:
            now = time.time()
            min_d = float(self._per_host.get(domain, self._def_min))
            max_d = max(min_d, self._def_max)
            last = self._last.get(domain, 0.0)
            wait = last + random.uniform(min_d, max_d) - now
            if wait > 0:
                time.sleep(wait)
            self._last[domain] = time.time()
