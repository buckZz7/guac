#!/usr/bin/env python3
"""Stress test: settlement on a synthetic month of billing rows.

Invariants that MUST hold for any generated data (no payments ledger, so
settlement reconstructs from ledger bill rows + impression costs):
  - ad_revenue == sum of recorded impression costs
  - user_paid == sum(bill.cost) over rows that have bills
  - market_value == sum(bill.cost / (1 - discount_rate))
  - user_saving == market_value - user_paid (the discount itself)
  - nothing negative
"""
import datetime as _dt
import json
import os
import random
import tempfile

os.environ["ADGATE_PAYMENTS_LEDGER"] = os.path.join(tempfile.mkdtemp(), "payments.jsonl")

import config
import settlement

random.seed(42)


def gen_month(days=28, users=12, offers=3):
    """Return ledger rows resembling a real usage month, WITH real bills."""
    rows = []
    now = _dt.datetime.now(_dt.timezone.utc)
    impression_costs = [0.01, 0.02, 0.05]  # per offer
    keep = 1.0 - config.DISCOUNT_RATE
    base_daily = 30
    for day in range(days):
        ts = (now - _dt.timedelta(days=(days - day))).isoformat()
        n_req = max(1, int(random.gauss(base_daily, 8)))
        for _ in range(n_req):
            user = f"user{random.randrange(users)}"
            offer_idx = random.randrange(offers)
            sponsored = random.random() < 0.25
            pt = int(random.gauss(3000, 1500))
            ct = int(random.gauss(1200, 600))
            if random.random() < 0.01:
                pt = int(random.gauss(50000, 10000))  # outlier
            pt, ct = max(1, pt), max(1, ct)
            # Real bill: market cost for these tokens, discounted.
            market = (pt + ct) * config.PASSTHROUGH_WHOLESALE_PER_M / 1e6
            cost = round(market * keep, 8)
            row = {
                "ts": ts, "user": user,
                "sponsored": sponsored,
                "prompt_tokens": pt, "completion_tokens": ct,
                "bill": {"cost": cost, "discount_rate": config.DISCOUNT_RATE,
                         "unpaid": False},
            }
            if sponsored:
                row["sponsor"] = f"Offer {offer_idx}"
                # 1% chance a row is missing its impression cost (edge case)
                if random.random() >= 0.01:
                    row["impression_cost"] = impression_costs[offer_idx]
            rows.append(row)
    return rows


def main():
    rows = gen_month()
    total_tk = sum(r["prompt_tokens"] + r["completion_tokens"] for r in rows)
    n_ads = sum(1 for r in rows if r["sponsored"])
    n_missing = sum(1 for r in rows if r["sponsored"] and "impression_cost" not in r)
    exp_ad_rev = sum(r.get("impression_cost", 0.0) for r in rows if r["sponsored"])
    exp_billed = sum(r["bill"]["cost"] for r in rows)
    exp_market = sum(r["bill"]["cost"] / (1 - config.DISCOUNT_RATE) for r in rows)

    print(f"synthetic month: {len(rows)} requests, {n_ads} sponsored "
          f"({n_missing} without recorded cost), {total_tk:,} tokens")

    s = settlement.settle(rows)
    print(f"  ad_revenue=${s['ad_revenue']:.4f}  user_paid=${s['user_paid']:.4f}  "
          f"market=${s['market_value']:.4f}  saved=${s['user_saving']:.4f}")

    assert abs(s["ad_revenue"] - exp_ad_rev) < 1e-6, (s["ad_revenue"], exp_ad_rev)
    assert abs(s["user_paid"] - exp_billed) < 1e-4, (s["user_paid"], exp_billed)
    assert abs(s["market_value"] - exp_market) < 1e-3, (s["market_value"], exp_market)
    assert abs(s["user_saving"] - (s["market_value"] - s["user_paid"])) < 1e-6
    print("billing conservation (paid + saved == market value): PASS")

    # the discount applies to EVERY row, sponsored or not
    assert abs(s["user_saving"] - exp_billed * (config.DISCOUNT_RATE / (1 - config.DISCOUNT_RATE))) < 1e-3
    print("flat discount on all requests: PASS")

    for k, v in s.items():
        if isinstance(v, (int, float)):
            assert v >= 0, (k, v)
    assert s["requests"] == len(rows) and s["ads_delivered"] == n_ads
    assert s["tokens_total"] == total_tk
    assert s["period"] == "lifetime"
    print("non-negativity + counts: PASS")

    print("\nSETTLEMENT STRESS TESTS PASSED")


if __name__ == "__main__":
    main()
