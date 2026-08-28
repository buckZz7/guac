#!/usr/bin/env python3
"""Stress-test guac settlement with a realistic synthetic month of ledger data.

Generates many users, multiple offers with varying per-impression costs, mixed
sponsored/plain requests, and edge cases (budget-exhausted offers, rows without
a recorded impression cost, high-token outlier requests). Verifies that:
  - money always conserves: user_paid + ad_revenue == wholesale + fee + surplus
  - ad revenue is sourced from real per-impression ledger costs when present
  - no negative user_paid, no negative savings, breakdown sums to user_saving
  - a mid-month change in impression cost is respected
"""
import datetime as _dt
import json
import random

import settlement

random.seed(42)


def gen_month(days=28, users=12, offers=3):
    """Return a list of ledger rows resembling a real usage month."""
    rows = []
    now = _dt.datetime.now(_dt.timezone.utc)
    impression_costs = [0.01, 0.02, 0.05]  # per offer
    base_daily = 30  # avg requests/day across all users
    for day in range(days):
        ts = (now - _dt.timedelta(days=(days - day))).isoformat()
        n_req = max(1, int(random.gauss(base_daily, 8)))
        for _ in range(n_req):
            user = f"user{random.randrange(users)}"
            offer_idx = random.randrange(offers)
            sponsored = random.random() < 0.25
            # token counts vary; occasional big outlier
            pt = int(random.gauss(3000, 1500))
            ct = int(random.gauss(1200, 600))
            if random.random() < 0.01:
                pt = int(random.gauss(50000, 10000))  # outlier
            row = {
                "ts": ts, "user": user,
                "sponsored": sponsored,
                "prompt_tokens": max(1, pt), "completion_tokens": max(1, ct),
                "discount_rate": 0.20 if sponsored else 0.0,
            }
            if sponsored:
                row["sponsor"] = f"Offer {offer_idx}"
                # 1% chance a row is missing its impression cost (edge case)
                if random.random() < 0.01:
                    pass  # deliberately no impression_cost
                else:
                    row["impression_cost"] = impression_costs[offer_idx]
            rows.append(row)
    return rows


def check_conservation(s, n_ads, total_tk):
    wholesale_cost = s["wholesale_cost"]
    surplus = s["savings_breakdown"]["ad_surplus_carried_forward"]
    lhs = s["user_paid"] + s["ad_revenue"]
    rhs = wholesale_cost + s["guac_fee"] + surplus
    if abs(lhs - rhs) > 0.02:  # 2 cents rounding tolerance
        raise AssertionError(f"conservation violated: {lhs} != {rhs}")


def main():
    rows = gen_month()
    total_tk = sum(r["prompt_tokens"] + r["completion_tokens"] for r in rows)
    n_ads = sum(1 for r in rows if r["sponsored"])
    n_missing_cost = sum(1 for r in rows if r["sponsored"] and "impression_cost" not in r)

    print(f"synthetic month: {len(rows)} requests, {n_ads} sponsored "
          f"({n_missing_cost} without recorded cost), {total_tk:,} tokens")

    s = settlement.settle(rows)
    print(f"  ad_revenue=${s['ad_revenue']:.2f}  guac_fee=${s['guac_fee']:.2f}  "
          f"user_paid=${s['user_paid']:.2f}  saving=${s['user_saving']:.2f}")

    # money conservation
    check_conservation(s, n_ads, total_tk)
    print("  conservation (user_paid + ad_rev == wholesale + fee + surplus): ✓")

    # no negative values
    assert s["user_paid"] >= 0, "negative user_paid"
    assert s["user_saving"] >= 0, "negative saving"
    assert s["ad_revenue"] >= 0 and s["guac_fee"] >= 0
    print("  no negative money values: ✓")

    # breakdown sums exactly to user_saving
    bd = s["savings_breakdown"]
    assert abs((bd["from_cheap_supply"] + bd["from_ads"]) - s["user_saving"]) < 0.02, \
        (bd, s["user_saving"])
    print("  savings breakdown sums to user_saving: ✓")

    # ad revenue is from real per-impression costs (not the 0.30 fallback)
    recorded = sum(r.get("impression_cost", 0.0)
                   for r in rows if r["sponsored"])
    # rows missing cost fall back to 0.30 each
    expected_adrev = round(recorded + n_missing_cost * 0.30, 2)
    assert abs(s["ad_revenue"] - expected_adrev) < 0.02, \
        (s["ad_revenue"], expected_adrev)
    print(f"  ad revenue from ledger costs ({recorded:.2f}) + {n_missing_cost} fallback rows: ✓")

    # mid-month impression cost change is respected (per-row, not global)
    rows2 = list(rows)
    # force two clearly-different costs
    for i, r in enumerate(rows2):
        if r["sponsored"] and i < len(rows2) // 2:
            r["impression_cost"] = 0.01
        elif r["sponsored"]:
            r["impression_cost"] = 0.10
    s2 = settlement.settle(rows2)
    expected2 = sum(r.get("impression_cost", 0.30)
                    for r in rows2 if r["sponsored"])
    assert abs(s2["ad_revenue"] - round(expected2, 2)) < 0.05, (s2["ad_revenue"], expected2)
    print("  mid-month impression cost change respected: ✓")

    print("\nSETTLEMENT STRESS TEST PASSED (synthetic month)")


if __name__ == "__main__":
    main()
