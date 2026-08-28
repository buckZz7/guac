#!/usr/bin/env python3
"""Concurrency test: many concurrent charge_impression calls must not lose
updates. Without the portal lock, concurrent read-modify-write on offers.json
would drop counts; this proves the lock makes billing exact under contention."""
import os
import tempfile
import threading
import sys

# Set env BEFORE importing config/portal so their file paths point at temp files.
td = tempfile.mkdtemp()
os.environ["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
import portal


def main():
    # create an offer with a large budget
    offer = portal.create_offer("ad@ex.com", "t", "", "", 100.0)
    oid = offer["id"]

    N = 200
    errors = []
    def worker():
        try:
            portal.charge_impression(oid)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"thread errors: {errors[:3]}"
    o = portal.get_offer(oid)
    assert o["impressions"] == N, f"lost updates: got {o['impressions']}, want {N}"
    assert abs(o["spent"] - (N * config.IMPRESSION_COST)) < 1e-9, o["spent"]
    print(f"{N} concurrent impressions -> exact count {o['impressions']}: ✓")
    print(f"spent ${o['spent']:.2f} == {N} x ${config.IMPRESSION_COST:.2f}: ✓")
    print("\nCONCURRENCY TEST PASSED (no lost updates under contention)")


if __name__ == "__main__":
    main()
