"""guac abuse/quota limits — lightweight in-process rate limiting.

Per-process counters (reset on restart). Good enough to stop scripted abuse
(signup spam, a leaked key burning tokens); not a distributed limiter. For a
real launch behind multiple replicas, move to a shared store (Redis).
"""
import threading
import time

import config

_LOCK = threading.RLock()

# signup: client_ip -> [(ts, ...)] sliding hour window
_signup_hits = {}
# tokens: user_key -> {date: total_tokens}
_token_usage = {}


def allow_signup(client_ip: str) -> bool:
    """True if this IP hasn't exceeded the hourly signup cap."""
    if config.SIGNUP_PER_IP_PER_HOUR <= 0:
        return True
    now = time.time()
    window = 3600.0
    with _LOCK:
        hits = _signup_hits.setdefault(client_ip, [])
        hits[:] = [t for t in hits if now - t < window]
        if len(hits) >= config.SIGNUP_PER_IP_PER_HOUR:
            return False
        hits.append(now)
        return True


def token_budget_ok(user_key: str, extra: int) -> bool:
    """True if adding `extra` tokens for this key today stays under the cap."""
    if config.DAILY_TOKEN_CAP <= 0:
        return True
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with _LOCK:
        used = _token_usage.get(user_key, {}).get(today, 0)
        return used + extra <= config.DAILY_TOKEN_CAP


def record_tokens(user_key: str, tokens: int) -> None:
    if config.DAILY_TOKEN_CAP <= 0 or tokens <= 0:
        return
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with _LOCK:
        day = _token_usage.setdefault(user_key, {})
        day[today] = day.get(today, 0) + tokens
