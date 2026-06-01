# rmdpt_collector/common/session.py
from __future__ import annotations
import time
import random
from typing import Dict, Any
from .rate_limiter import DomainRateLimiter

class Session:
    """HTTP session wrapper with throttling support."""
    
    def __init__(self, throttle: Dict[str, float], headers: Dict[str, str]):
        self.throttle = throttle
        self.headers = headers
        self.rate_limiter = DomainRateLimiter(
            per_host_min_interval={},
            default_min=throttle.get("min_sleep_s", 1.0),
            default_max=throttle.get("max_sleep_s", 2.0)
        )
        
    def get_headers(self) -> Dict[str, str]:
        """Get the session headers."""
        return self.headers.copy()
        
    def wait_for_domain(self, domain: str):
        """Wait according to throttling rules for the given domain."""
        self.rate_limiter.wait(domain)
