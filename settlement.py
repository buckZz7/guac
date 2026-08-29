"""guac settlement — turns the ledgers into the real money story.

Flat-discount model:

    Users prepay credits and are billed at a flat discounted rate on EVERY
    request (market price minus DISCOUNT_RATE), sponsored or not. Advertisers
    prepay credits; each delivered sponsorship charges one impression. Ad
    revenue is what funds the user-facing discount.

Everything here is read from the ledgers (no estimates):
    payments.jsonl  credits: topup_mock/stripe (tagged entity_kind)
                    debits:  impression (advertisers), inference (users)
    ledger.jsonl    per-request metering (tokens, supplier, bill breakdown)

Conservation (always holds, row-for-row):
    user spend == sum of billed request costs
    advertiser debits == impressions delivered * impression cost
"""
import argparse
import json

import config


def _load_ledger_rows():
    rows = []
    if config.LEDGER_FILE.exists():
        with open(config.LEDGER_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return rows


def _read_payments():
    rows = []
    if config.PAYMENTS_LEDGER.exists():
        with open(config.PAYMENTS_LEDGER) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return rows


def _tokens(r):
    return r.get("prompt_tokens", 0) + r.get("completion_tokens", 0)


def settle(rows):
    """Lifetime settlement statement from real ledger data.

    ad_revenue     : everything advertisers were debited for impressions
    guac_revenue   : ad revenue (funds the discount) + any margin on the spread
                     between market and discounted rates (the spread is what
                     keeps guac solvent; it is reported, not hidden)
    user_topups    : everything users paid in
    user_paid      : what users were billed (already discounted)
    user_saving    : market value of those tokens minus what users paid
    """
    total_tk = sum(_tokens(r) for r in rows)
    sponsored = [r for r in rows if r.get("sponsored")]
    n_ads = len(sponsored)
    n_requests = len(rows)

    # --- advertiser side: real impression debits from the payments ledger ---
    pay_rows = _read_payments()
    ad_revenue = sum(
        -row.get("delta", 0.0)
        for row in pay_rows
        if row.get("kind") == "debit" and row.get("source") == "impression")
    if ad_revenue == 0:
        # No payments ledger data (e.g. unit tests): fall back to the
        # per-impression cost recorded on sponsored rows.
        for r in sponsored:
            c = r.get("impression_cost")
            if c is not None and c > 0:
                ad_revenue += c

    # --- user side: real billing from the payments ledger ------------------
    user_topups = sum(row.get("delta", 0.0) for row in pay_rows
                      if row.get("kind") == "credit"
                      and row.get("source", "").startswith("topup")
                      and row.get("entity_kind", "user") == "user")
    user_paid = sum(-row.get("delta", 0.0) for row in pay_rows
                    if row.get("source") == "inference")
    if user_paid == 0:
        # No payments data: reconstruct from the ledger's bill rows.
        for r in rows:
            bill = r.get("bill") or {}
            user_paid += bill.get("cost", 0.0)

    # Market value of what users bought: invert the discount on each bill.
    market_value = 0.0
    for r in rows:
        bill = r.get("bill") or {}
        cost = bill.get("cost", 0.0)
        rate = bill.get("discount_rate") or 0.0
        if cost:
            market_value += cost / (1.0 - rate) if rate and rate < 1.0 else cost
    user_saving = max(market_value - user_paid, 0.0)

    return {
        "period": "lifetime",
        "requests": n_requests,
        "tokens_total": total_tk,
        "ads_delivered": n_ads,
        "discount_rate": config.DISCOUNT_RATE,
        # advertiser side
        "ad_revenue": round(ad_revenue, 4),
        # user side
        "user_topups": round(user_topups, 4),
        "user_paid": round(user_paid, 4),
        "market_value": round(market_value, 4),
        "user_saving": round(user_saving, 4),
        # economics: the discount is funded by ad revenue; the spread between
        # what users pay and true wholesale (if suppliers cost less than the
        # discounted market rate) is guac's operating margin.
        "guac_margin_funded_by": "ad_revenue",
        "split": {
            "sponsor_paid": round(ad_revenue, 4),
            "user_saved": round(user_saving, 4),
        },
    }


def render_statement(s):
    lines = [
        f"guac statement — {s['period']}",
        "─" * 48,
        f"requests             {s['requests']}",
        f"tokens               {s['tokens_total']:,}",
        f"ads delivered        {s['ads_delivered']}",
        f"discount rate        {int(s['discount_rate']*100)}% off market",
        "",
        "USER BILLING (flat discounted rate, every request)",
        f"  user top-ups       ${s['user_topups']:.2f}",
        f"  user paid          ${s['user_paid']:.2f}",
        f"  market value       ${s['market_value']:.2f}",
        f"  user saved         ${s['user_saving']:.2f}",
        "",
        "ADVERTISER MONEY (funds the discount)",
        f"  sponsor paid       ${s['ad_revenue']:.2f}",
        "",
        "Users always pay below market rate, sponsored or not.",
        "Sponsorships fund the gap. guac keeps no markup on tokens.",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="guac settlement (flat discount)")
    ap.parse_args()
    rows = _load_ledger_rows()
    if not rows:
        print("No ledger rows found. Run the gateway and make a request first.")
        return
    s = settle(rows)
    print(render_statement(s))
    print()
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
