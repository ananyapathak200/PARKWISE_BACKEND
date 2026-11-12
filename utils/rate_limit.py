"""
utils/rate_limit.py — slows down password guessing and form spam.

A small in-memory sliding-window limiter: no extra service to run.
Limits are per server process. With `gunicorn -w 2` each worker keeps its
own counts, so the real limit is up to 2x the numbers below — still
enough to stop scripted attacks. Use Redis if you scale to several servers.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: int, message: str):
        self.max_events = max_events
        self.window = window_seconds
        self.message = message
        self._events = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _prune(self, key: str, now: float) -> deque:
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def _sweep(self, now: float) -> None:
        # Forget idle keys now and then so memory can't grow without limit.
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        for key in [k for k, q in self._events.items() if not q or now - q[-1] > self.window]:
            del self._events[key]

    def blocked(self, key: str) -> bool:
        with self._lock:
            now = time.monotonic()
            return len(self._prune(key, now)) >= self.max_events

    def record(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._sweep(now)
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def hit(self, key: str) -> None:
        """Count one event; raise 429 Too Many Requests once over the limit."""
        with self._lock:
            now = time.monotonic()
            self._sweep(now)
            q = self._prune(key, now)
            if len(q) >= self.max_events:
                retry_after = int(self.window - (now - q[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail=self.message,
                    headers={"Retry-After": str(retry_after)},
                )
            q.append(now)

    def check(self, key: str) -> None:
        """Raise 429 if over the limit, without counting this request."""
        if self.blocked(key):
            raise HTTPException(status_code=429, detail=self.message, headers={"Retry-After": str(self.window)})


def client_ip(request: Request) -> str:
    # Behind Nginx, uvicorn/gunicorn rewrite request.client from
    # X-Forwarded-For (trusted only from 127.0.0.1 by default).
    return request.client.host if request.client else "unknown"


_WAIT = "Too many attempts. Please wait a few minutes and try again."

# Login: 5 wrong passwords per account per 15 min, 30 tries per IP per 15 min.
login_failures_by_email = RateLimiter(5, 15 * 60, _WAIT)
login_attempts_by_ip = RateLimiter(30, 15 * 60, _WAIT)
# Signup: 5 new accounts per IP per hour.
signup_by_ip = RateLimiter(5, 60 * 60, "Too many sign-ups from this network. Please try again later.")
# Password reset: 5 requests per IP per 15 min; 3 emails per address per hour.
forgot_by_ip = RateLimiter(5, 15 * 60, _WAIT)
forgot_by_email = RateLimiter(3, 60 * 60, _WAIT)
reset_by_ip = RateLimiter(10, 15 * 60, _WAIT)
# Address lookup: 30 per IP per minute (OpenStreetMap allows ~1 request/second overall).
geocode_by_ip = RateLimiter(30, 60, "Too many address lookups. Please wait a minute.")
# Bookings and reviews: stop scripted spam from a single account.
bookings_by_user = RateLimiter(20, 60 * 60, "Too many bookings in a short time. Please try again later.")
