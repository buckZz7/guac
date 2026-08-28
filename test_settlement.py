#!/usr/bin/env python3
"""Test guac settlement Model B: wholesale savings flow to the user, guac
keeps only its fee. Verifies:
  - user_saving == (retail − wholesale) + (ad money − fee)
  - conservation: user_paid + ad_revenue == wholesale_cost + guac_fee
  - guac margin == guac fee (thin, honest)
  - user pays strictly less than retail (discount is material)"""
import datetime as _dt
import json

import settlement

PT, CT = 50000, 20000   # realistic agentic request tokens


def make_rows(n_ads, n_plain, impression_cost=None):
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    rows = []
    for i in range(n_ads):
        r = {"ts": now, "user": "alice", "sponsored": True,
             "sponsor": "Acme Cloud Hosting",
             "prompt_tokens": PT, "completion_tokens": CT,
             "discount_rate": 0.20}
        if impression_cost is not None:
            r["impression_cost"] = impression_cost
        rows.append(r)
    for i in range(n_plain):
        rows.append({"ts": now, "user": "alice", "sponsored": False,
                     "sponsor": None,
                     "prompt_tokens": PT, "completion_tokens": CT,
                     "discount_rate": 0.0})
    return rows


def approx(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_real_per_impression():
    """The production path: the ledger records each sponsored row's actual
    per-impression cost. Settlement must use THAT, not a hardcoded estimate.
    guac's fee is capped at ad revenue (can't earn more than advertisers paid)."""
    rows = make_rows(10, 0, impression_cost=0.01)
    s = settlement.settle(rows)  # no ad_money override; must read ledger
    assert abs(s["ad_revenue"] - 0.10) < 1e-6, s["ad_revenue"]
    # fee = min(10 x $0.10 default, $0.10 ad revenue) = $0.10
    assert abs(s["guac_fee"] - 0.10) < 1e-6, s["guac_fee"]
    print("real per-impression ad revenue ($0.10 for 10 imps @ $0.01):", "✓")


def test_fallback_when_no_cost():
    """Rows without impression_cost fall back to the per-offer estimate."""
    rows = make_rows(5, 0)  # no impression_cost
    s = settlement.settle(rows, ad_money_per_offer=0.30)
    assert abs(s["ad_revenue"] - 1.50) < 1e-6, s["ad_revenue"]
    print("fallback to per-offer estimate when no cost recorded:", "✓")


def main():
    n_ads, n_plain = 10, 40
    rows = make_rows(n_ads, n_plain)
    A, F, R, W = 0.30, 0.10, 1.50, None   # W defaults to 0.35*R
    s = settlement.settle(rows, A, F, R, W)
    W = round(R * 0.35, 4)

    per_req = PT + CT
    total_tk = (n_ads + n_plain) * per_req
    retail_cost = round(total_tk * R / 1e6, 2)
    wholesale_cost = round(total_tk * W / 1e6, 2)
    ad_revenue = round(n_ads * A, 2)
    guac_fee = round(n_ads * F, 2)
    ad_pass_through = round(ad_revenue - guac_fee, 2)

    assert s["ads_delivered"] == n_ads
    assert s["tokens_total"] == total_tk

    # user pays wholesale minus ad pass-through (capped at 0)
    exp_user_paid = round(max(0.0, wholesale_cost - ad_pass_through), 2)
    assert approx(s["user_paid"], exp_user_paid), (s["user_paid"], exp_user_paid)

    # user saving == (retail − wholesale) + ad pass-through, capped at retail
    # (user can't save more than 100%). Breakdown must sum exactly to it.
    assert approx(s["savings_breakdown"]["from_cheap_supply"],
                  round(retail_cost - wholesale_cost, 2))
    assert approx(s["savings_breakdown"]["from_ads"],
                  round(min(ad_pass_through, wholesale_cost), 2))
    assert approx(s["savings_breakdown"]["from_cheap_supply"]
                  + s["savings_breakdown"]["from_ads"],
                  s["user_saving"]), "breakdown must sum to user_saving"

    # conservation: user_paid + ad_revenue == wholesale_cost + guac_fee + surplus
    surplus = max(0.0, ad_pass_through - wholesale_cost)
    assert approx(s["user_paid"] + ad_revenue,
                  wholesale_cost + guac_fee + surplus), \
        "money conservation violated"

    # guac margin == fee (thin, honest)
    assert approx(s["guac_margin"], guac_fee)

    # discount is material: user paid far below retail
    assert s["user_paid"] < s["retail_cost"]
    assert s["user_saving"] > s["retail_cost"] * 0.3, "saving too small"

    print(settlement.render_statement(s))
    print("\nSETTLEMENT (MODEL B) TESTS PASSED")
    json.dumps(s)


if __name__ == "__main__":
    test_real_per_impression()
    test_fallback_when_no_cost()
    main()
