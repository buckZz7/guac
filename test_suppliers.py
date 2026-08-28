#!/usr/bin/env python3
"""Unit test: supplier recovery via cooldown.

A supplier that goes proven_bad (enough failures, score below gate) must NOT
be dropped forever — after the recovery cooldown elapses it becomes
retry-eligible so the router can probe it again. This guards against a
transient failure (dead model slug, brief outage) permanently removing a
supplier.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import suppliers


def main():
    # Build a supplier that will go proven_bad fast: warmup=1, realistic gate.
    sup = suppliers.Supplier("t", "http://127.0.0.1:9999/v1", bid=1.0,
                             min_score=0.4, warmup_successes=1)
    # Fresh supplier: unproven -> healthy (tried optimistically).
    assert sup.healthy(), "unproven supplier should be healthy"
    assert sup.attempts == 0 and sup.score() == -1.0

    # Fail it enough to go proven_bad.
    sup.record(False, 10)
    assert sup.attempts >= sup.warmup_successes
    assert sup.proven_bad(), "should be proven_bad after a failure with warmup=1"
    assert not sup.healthy(), "proven_bad supplier must not be healthy"

    # Immediately after: not yet retry-eligible (cooldown hasn't elapsed).
    assert not sup.retry_eligible(), "should not retry before cooldown"

    # Simulate cooldown elapsing.
    sup.last_attempt_ts = time.time() - suppliers.RECOVERY_COOLDOWN_S - 1.0
    assert sup.retry_eligible(), "should be retry-eligible after cooldown"
    assert sup.healthy(), "retry-eligible supplier is routable again"

    # It gets probed and succeeds -> re-earns health (score above gate).
    sup.record(True, 50)
    assert not sup.proven_bad(), "success should clear proven_bad"
    assert sup.healthy(), "supplier healthy again after successful recovery"

    print("recovery (proven_bad -> cooldown -> retry -> healthy): ✓")
    print("UNPROVEN OPTIMISTIC TRIAL + COOLDOWN RECOVERY TESTS PASSED")


if __name__ == "__main__":
    main()
