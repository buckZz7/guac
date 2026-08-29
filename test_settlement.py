#!/usr/bin/env python3
"""Test guac settlement (flat-discount model). Verifies:
  - ad_revenue = real impression debits from the payments ledger
  - user_paid = real inference debits (discounted rate)
  - user_saving = market value minus what the user paid (discount inverted)
  - nothing is created or destroyed"""
import datetime as _dt
import json
import os
import tempfile

td = tempfile.mkdtemp()
os.environ["ADGATE_PAYMENTS_LEDGER"] = os.path.join(td, "payments.jsonl")

import config
import settlement

PT, CT = 5000, 1000


def write_payments(rows):
    with open(config.PAYMENTS_LEDGER, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def approx(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_full_flow():
    """Advertiser debited for impressions; user bills arrive already discounted."""
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    keep = 1.0 - config.DISCOUNT_RATE
    # A request that would cost $0.10 at market is billed at market*keep.
    cost1 = round(0.10 * keep, 8)
    cost2 = round(0.03 * keep, 8)
    write_payments([
        {"ts": now, "advertiser": "adv@x.com", "delta": 5.0, "kind": "credit", "source": "topup_mock", "entity_kind": "advertiser"},
        {"ts": now, "advertiser": "adv@x.com", "delta": -0.05, "kind": "debit", "source": "impression"},
        {"ts": now, "advertiser": "adv@x.com", "delta": -0.05, "kind": "debit", "source": "impression"},
        {"ts": now, "advertiser": "alice", "delta": 2.0, "kind": "credit", "source": "topup_mock", "entity_kind": "user"},
        {"ts": now, "advertiser": "alice", "delta": -cost1, "kind": "debit", "source": "inference"},
        {"ts": now, "advertiser": "alice", "delta": -cost2, "kind": "debit", "source": "inference"},
    ])
    rows = [
        {"ts": now, "user": "alice", "sponsored": True, "sponsor": "adv@x.com",
         "impression_cost": 0.05, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": cost1, "discount_rate": config.DISCOUNT_RATE}},
        {"ts": now, "user": "alice", "sponsored": False, "sponsor": None,
         "impression_cost": 0.0, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": cost2, "discount_rate": config.DISCOUNT_RATE}},
    ]
    s = settlement.settle(rows)

    assert approx(s["ad_revenue"], 0.10), s["ad_revenue"]
    assert approx(s["user_topups"], 2.0), s["user_topups"]
    assert approx(s["user_paid"], cost1 + cost2), s["user_paid"]
    # market value inverts the discount: 0.10 + 0.03
    assert approx(s["market_value"], 0.13, tol=1e-6), s["market_value"]
    # saving = the discount itself
    assert approx(s["user_saving"], 0.13 - (cost1 + cost2), tol=1e-6), s["user_saving"]
    assert s["requests"] == 2 and s["ads_delivered"] == 1
    assert s["tokens_total"] == 2 * (PT + CT)
    assert s["discount_rate"] == config.DISCOUNT_RATE
    print("full flow (impression debits, flat-discount billing): PASS")


def test_no_payments_ledger_fallback():
    """Without payments data, settlement reconstructs from ledger bill rows
    and per-row impression_cost — never invents money."""
    if os.path.exists(config.PAYMENTS_LEDGER):
        os.remove(config.PAYMENTS_LEDGER)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    rows = [
        {"ts": now, "user": "bob", "sponsored": True, "sponsor": "Acme",
         "impression_cost": 0.05, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": 0.02, "discount_rate": config.DISCOUNT_RATE}},
        {"ts": now, "user": "bob", "sponsored": False, "sponsor": None,
         "impression_cost": 0.0, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": 0.01, "discount_rate": config.DISCOUNT_RATE}},
    ]
    s = settlement.settle(rows)
    assert approx(s["ad_revenue"], 0.05), s["ad_revenue"]
    assert approx(s["user_paid"], 0.03), s["user_paid"]
    assert approx(s["market_value"], 0.03 / (1 - config.DISCOUNT_RATE), tol=1e-3)
    assert s["period"] == "lifetime"
    print("fallback reconstruction + lifetime label: PASS")


if __name__ == "__main__":
    test_full_flow()
    test_no_payments_ledger_fallback()
    print("\nSETTLEMENT (FLAT-DISCOUNT) TESTS PASSED")
