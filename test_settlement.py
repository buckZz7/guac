#!/usr/bin/env python3
"""Test guac settlement (paid-with-discount). Verifies:
  - ad_revenue = real impression debits from the payments ledger
  - guac_fee = ad_revenue * GUAC_AD_FEE_FRACTION; sponsor_credits = the rest
  - user_paid + subsidy_used come from the payments ledger
  - user_saving == subsidy_used (advertiser money = the token discount)
  - conservation: nothing is created or destroyed"""
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
    """End-to-end: advertiser debited for impressions; user bills draw the
    subsidy bucket first."""
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    write_payments([
        # advertiser: top up $5, debited 2 impressions @ $0.05
        {"ts": now, "advertiser": "adv@x.com", "delta": 5.0, "kind": "credit", "source": "topup_mock", "entity_kind": "advertiser"},
        {"ts": now, "advertiser": "adv@x.com", "delta": -0.05, "kind": "debit", "source": "impression"},
        {"ts": now, "advertiser": "adv@x.com", "delta": -0.05, "kind": "debit", "source": "impression"},
        # user: top up $2; two requests: one subsidized (subsidy $0.04 covers),
        # one paid from own money
        {"ts": now, "advertiser": "alice", "delta": 2.0, "kind": "credit", "source": "topup_mock", "entity_kind": "user"},
        {"ts": now, "advertiser": "alice", "delta": 0.04, "kind": "credit", "source": "sponsor_pass_through"},
        {"ts": now, "advertiser": "alice", "delta": -0.04, "kind": "debit", "source": "subsidy_used"},
        {"ts": now, "advertiser": "alice", "delta": -0.03, "kind": "debit", "source": "inference"},
    ])
    rows = [
        {"ts": now, "user": "alice", "sponsored": True, "sponsor": "adv@x.com",
         "impression_cost": 0.05, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": 0.04, "user_paid": 0.0, "subsidy_used": 0.04}},
        {"ts": now, "user": "alice", "sponsored": False, "sponsor": None,
         "impression_cost": 0.0, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": 0.03, "user_paid": 0.03, "subsidy_used": 0.0}},
    ]
    s = settlement.settle(rows)

    assert approx(s["ad_revenue"], 0.10), s["ad_revenue"]
    assert approx(s["guac_fee"], 0.02), s["guac_fee"]          # 20% of 0.10
    assert approx(s["sponsor_credits"], 0.08), s["sponsor_credits"]
    assert approx(s["user_topups"], 2.0), s["user_topups"]
    assert approx(s["user_paid"], 0.03), s["user_paid"]
    assert approx(s["subsidy_used"], 0.04), s["subsidy_used"]
    assert approx(s["user_saving"], 0.04), s["user_saving"]    # saving == advertiser money
    assert approx(s["total_inference_billed"], 0.07), s["total_inference_billed"]
    # conservation: user_paid + subsidy_used == billed
    assert approx(s["user_paid"] + s["subsidy_used"], s["total_inference_billed"])
    # advertiser money: fee + credits == ad_revenue
    assert approx(s["guac_fee"] + s["sponsor_credits"], s["ad_revenue"])
    assert s["requests"] == 2 and s["ads_delivered"] == 1
    assert s["tokens_total"] == 2 * (PT + CT)
    print("full flow (impression debits, subsidy-first billing):", "PASS")


def test_no_payments_ledger_fallback():
    """Without payments data, settlement reconstructs from ledger bill rows
    and per-row impression_cost — never invents money."""
    if os.path.exists(config.PAYMENTS_LEDGER):
        os.remove(config.PAYMENTS_LEDGER)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    rows = [
        {"ts": now, "user": "bob", "sponsored": True, "sponsor": "Acme",
         "impression_cost": 0.05, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": 0.02, "user_paid": 0.01, "subsidy_used": 0.01}},
        {"ts": now, "user": "bob", "sponsored": False, "sponsor": None,
         "impression_cost": 0.0, "prompt_tokens": PT, "completion_tokens": CT,
         "bill": {"cost": 0.01, "user_paid": 0.01, "subsidy_used": 0.0}},
    ]
    s = settlement.settle(rows)
    assert approx(s["ad_revenue"], 0.05), s["ad_revenue"]
    assert approx(s["user_paid"], 0.02), s["user_paid"]
    assert approx(s["subsidy_used"], 0.01), s["subsidy_used"]
    assert s["period"] == "lifetime"
    print("fallback reconstruction + lifetime label:", "PASS")


if __name__ == "__main__":
    test_full_flow()
    test_no_payments_ledger_fallback()
    print("\nSETTLEMENT (PAID-WITH-DISCOUNT) TESTS PASSED")
