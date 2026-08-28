"""guac supplier pool — deterministic quality scoring + failover routing.

Sourcing rule (non-negotiable): never "cheapest miner wins". Each supplier is
scored on real, measured quality (latency + success), and the router only ever
picks a supplier that clears a minimum quality threshold. A supplier that
degrades is dropped until it recovers; a request that fails fails over to the
next-best healthy supplier.

Score (deterministic, no LLM judge):
    score = base_bid * success_rate - latency_penalty

State is a simple JSON file so restarts don't forget measured quality.
"""
import json
import os
import time

import config

# A supplier classified proven_bad (enough failures, score below gate) is NOT
# dropped forever. After this cooldown since its last attempt, it becomes
# retry-eligible: the router probes it once more. If it succeeds it re-earns
# health; if it fails the cooldown resets. This prevents a transient failure
# (e.g. a dead model slug, a temporary outage) from permanently removing a
# supplier.
RECOVERY_COOLDOWN_S = 300.0


class Supplier:
    def __init__(self, name, base_url, key="", bid=1.0, min_score=0.0,
                 warmup_successes=1, model=None, key_env=None):
        self.name = name
        self.base_url = base_url.rstrip("/")
        # key can be given directly, or loaded from an env var by name.
        self.key = key or (os.environ.get(key_env, "") if key_env else "")
        self.key_env = key_env
        self.bid = float(bid)            # base quality/priority weight
        self.min_score = float(min_score)
        self.warmup_successes = int(warmup_successes)
        self.model = model               # default model slug for this supplier
        # runtime stats (also persisted via pool.save_state)
        self.successes = 0
        self.failures = 0
        self.total_latency_ms = 0.0
        self.last_attempt_ts = 0.0

    # -- quality metrics ------------------------------------------------
    @property
    def attempts(self):
        return self.successes + self.failures

    def success_rate(self):
        if self.attempts == 0:
            return 1.0 if self.warmup_successes == 0 else 0.0
        return self.successes / self.attempts

    def avg_latency_ms(self):
        return self.total_latency_ms / self.successes if self.successes else 0.0

    def score(self):
        """Deterministic quality score: bid-weighted, latency-penalised.

        Latency penalty only bites above a grace threshold (4s). Cheap
        cross-provider inference routinely runs 1-3s even when reliable, so
        penalising linearly from 0ms would drop a 100%-reliable supplier over
        nothing. We only dock score once latency exceeds the grace band.
        """
        sr = self.success_rate()
        # Need enough observations to trust the score (warmup gate).
        if self.successes < self.warmup_successes:
            return -1.0
        # Penalty: below LATENCY_GRACE_MS there is no penalty (cheap suppliers
        # are naturally 1-3s even when reliable); above it, score falls toward 0.
        grace = config.LATENCY_GRACE_MS
        latency_pen = 0.0
        avg = self.avg_latency_ms()
        if avg > grace:
            latency_pen = min(1.0, (avg - grace) / (config.LATENCY_HARD_MS - grace))
        return self.bid * sr - latency_pen

    def proven_bad(self):
        """Has enough attempts AND a score below the gate — exclude from routing."""
        return self.attempts >= self.warmup_successes and self.score() < self.min_score

    def retry_eligible(self):
        """A proven_bad supplier may be probed again after the cooldown elapses,
        so a transient failure doesn't remove it permanently."""
        if not self.proven_bad():
            return False
        return (time.time() - self.last_attempt_ts) >= RECOVERY_COOLDOWN_S

    def healthy(self):
        """Routable: not proven-bad, OR retry-eligible after cooldown.
        Unproven suppliers are tried optimistically so they can earn a score;
        proven-bad ones are retried only after the recovery cooldown."""
        return (not self.proven_bad()) or self.retry_eligible()

    def record(self, ok, latency_ms):
        self.last_attempt_ts = time.time()
        if ok:
            self.successes += 1
            self.total_latency_ms += latency_ms
        else:
            self.failures += 1

    def to_dict(self):
        return {
            "name": self.name,
            "base_url": self.base_url,
            "key_env": self.key_env,
            "model": self.model,
            "bid": self.bid,
            "min_score": self.min_score,
            "warmup_successes": self.warmup_successes,
            "successes": self.successes,
            "failures": self.failures,
            "total_latency_ms": self.total_latency_ms,
            "last_attempt_ts": self.last_attempt_ts,
        }

    @classmethod
    def from_dict(cls, d):
        s = cls(d["name"], d["base_url"], d.get("key", ""),
                d.get("bid", 1.0), d.get("min_score", 0.0),
                d.get("warmup_successes", 1),
                d.get("model"), d.get("key_env"))
        s.successes = d.get("successes", 0)
        s.failures = d.get("failures", 0)
        s.total_latency_ms = d.get("total_latency_ms", 0.0)
        s.last_attempt_ts = d.get("last_attempt_ts", 0.0)
        return s


class SupplierPool:
    def __init__(self, suppliers=None):
        self.suppliers = suppliers or []
        self._state_file = config.SUPPLIER_STATE_FILE
        self._load_state()

    # -- state persistence ---------------------------------------------
    def _load_state(self):
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            for sup in self.suppliers:
                if sup.name in data:
                    # overlay persisted quality, keep fresh config fields
                    prev = data[sup.name]
                    sup.successes = prev.get("successes", 0)
                    sup.failures = prev.get("failures", 0)
                    sup.total_latency_ms = prev.get("total_latency_ms", 0.0)
                    sup.last_attempt_ts = prev.get("last_attempt_ts", 0.0)
        except Exception:
            pass

    def save_state(self):
        data = {s.name: s.to_dict() for s in self.suppliers}
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(data, indent=2))

    # -- routing -------------------------------------------------------
    def ordered(self):
        """Healthy suppliers, best quality first. Unhealthy dropped."""
        healthy = [s for s in self.suppliers if s.healthy()]
        healthy.sort(key=lambda s: s.score(), reverse=True)
        return healthy

    def pick(self):
        """Best healthy supplier, or None if none cleared the gate."""
        h = self.ordered()
        return h[0] if h else None

    def stats(self):
        return {s.name: {"score": round(s.score(), 3), "healthy": s.healthy(),
                         "successes": s.successes, "failures": s.failures,
                         "avg_latency_ms": round(s.avg_latency_ms(), 1)}
                for s in self.suppliers}


def load_pool():
    """Load the supplier pool from config (env-overridable JSON file)."""
    path = config.SUPPLIERS_FILE
    if not path.exists():
        # fall back to the plain upstream as a single supplier
        return SupplierPool([Supplier("default", config.UPSTREAM_BASE,
                                     config.UPSTREAM_KEY)])
    data = json.loads(path.read_text())
    # accept either a bare list or {"suppliers": [...]}
    if isinstance(data, dict):
        data = data.get("suppliers", [])
    return SupplierPool([Supplier.from_dict(d) for d in data])
