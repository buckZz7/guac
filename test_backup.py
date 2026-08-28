#!/usr/bin/env python3
"""Backup test: build_bundle captures all state, restore_bundle round-trips it
back, and the checksum validates integrity. Uses temp state files."""
import hashlib
import json
import os
import sys
import tempfile

# Set temp paths before importing config/backup so they read the temp files.
td = tempfile.mkdtemp()
os.environ["ADGATE_STATE_FILE"] = os.path.join(td, "state.json")
os.environ["ADGATE_USERS_FILE"] = os.path.join(td, "users.json")
os.environ["ADGATE_ADVERTISERS_FILE"] = os.path.join(td, "advertisers.json")
os.environ["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
os.environ["ADGATE_MAGIC_USED_FILE"] = os.path.join(td, "magic_used.json")
os.environ["ADGATE_SUPPLIER_STATE_FILE"] = os.path.join(td, "supplier_state.json")
os.environ["ADGATE_LEDGER_FILE"] = os.path.join(td, "ledger.jsonl")
os.environ["ADGATE_ATTRIBUTION_FILE"] = os.path.join(td, "attribution.jsonl")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
import backup
import portal


def main():
    # seed some state
    portal.create_user("a@b.com", 2)
    portal.create_advertiser("adv@b.com")
    offer = portal.create_offer("adv@b.com", "head", "body", "claim", 5.0)
    portal.charge_impression(offer["id"])
    # seed a ledger row directly
    config.log_ledger({"user": "a@b.com", "sponsored": True, "tokens": 10})

    bundle = backup.build_bundle()
    assert bundle["users"] and bundle["advertisers"] and bundle["offers"]
    assert len(bundle["ledger"]) == 1
    assert bundle["checksum"], "missing checksum"

    # checksum is over the bundle (minus the checksum field itself)
    body = json.dumps({k: v for k, v in bundle.items() if k != "checksum"},
                      sort_keys=True)
    assert hashlib.sha256(body.encode()).hexdigest() == bundle["checksum"], \
        "checksum mismatch"
    print("bundle captures all state + checksum valid:", "✓")

    # round-trip: wipe, restore, verify
    for f in os.listdir(td):
        if f.endswith((".json", ".jsonl")):
            os.remove(os.path.join(td, f))
    results = backup.restore_bundle(bundle)
    restored_names = {name for name, _ in results}
    # the files that had data must restore; None-valued ones are skipped
    for expect in ("users.json", "advertisers.json", "offers.json",
                   "ledger.jsonl", "attribution.jsonl"):
        assert expect in restored_names, (expect, results)
    print("restore round-trips populated state:", "✓")
    # re-read restored state
    assert portal.get_user_by_email("a@b.com") is not None
    restored_offer = portal.get_offer(offer["id"])
    assert restored_offer["impressions"] == 1, restored_offer
    assert len(backup.build_bundle()["ledger"]) == 1
    print("restore round-trips all state:", "✓")

    print("\nBACKUP TESTS PASSED (bundle + checksum + round-trip)")


if __name__ == "__main__":
    main()
