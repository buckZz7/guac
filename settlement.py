"""guac settlement — turns the ledgers into the real money story.

Paid-with-discount model:

    Users prepay credits. Advertisers prepay credits. Every served request
    bills the user at wholesale cost, drawing their sponsor subsidy bucket
    FIRST. When an answer carries a sponsor, the advertiser is charged one
    impression; guac keeps GUAC_AD_FEE_FRACTION of it and the rest is
    credited to that user's subsidy bucket — so advertiser money is
    literally what discounts the user's tokens.

Everything here is read from the ledgers (no estimates):
    payments.jsonl  credits: topup_mock/stripe (own) + sponsor_pass_through
                    debits:  subsidy_used + inference
    ledger.jsonl    per-request metering (tokens, supplier, bill breakdown)

Conservation (always holds, row-for-row):
    user's own spend + subsidy used == total inference billed
    advertiser debits == guac fee + sponsor credits + (unspent: balance)
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

    ad_revenue      : everything advertisers were debited for impressions
    guac_fee        : ad_revenue * GUAC_AD_FEE_FRACTION (kept by guac)
    sponsor_credits : ad_revenue - guac_fee (credited into user subsidies)
    user_topups     : everything users paid in
    user_paid       : what users' own money actually covered
    subsidy_used    : advertiser money that covered user inference
    user_saving     : subsidy_used — the literal token discount
    """
    total_tk = sum(_tokens(r) for r in rows)
    sponsored = [r for r in rows if r.get("sponsored")]
    n_ads = len(sponsored)
    n_requests = len(rows)

    # --- advertiser side: real debits from the payments ledger -------------
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
    guac_fee = ad_revenue * config.GUAC_AD_FEE_FRACTION
    sponsor_credits = ad_revenue - guac_fee

    # --- user side: real billing from the payments ledger ------------------
    # "User top-ups" are top-ups tagged entity_kind=user (or untagged rows
    # credited by source naming only when no kind was recorded by an
    # advertiser). Advertiser top-ups fund ad spend, not inference.
    user_topups = sum(row.get("delta", 0.0) for row in pay_rows
                      if row.get("kind") == "credit"
                      and row.get("source", "").startswith("topup")
                      and row.get("entity_kind", "user") == "user")
    user_paid = sum(-row.get("delta", 0.0) for row in pay_rows
                    if row.get("source") == "inference")
    subsidy_used = sum(-row.get("delta", 0.0) for row in pay_rows
                       if row.get("source") == "subsidy_used")
    if user_paid == 0 and subsidy_used == 0:
        # No payments data: reconstruct billing from the ledger's bill rows.
        for r in rows:
            bill = r.get("bill") or {}
            user_paid += bill.get("user_paid", 0.0)
            subsidy_used += bill.get("subsidy_used", 0.0)

    user_saving = subsidy_used  # advertiser money that covered the user's tokens
    total_billed = user_paid + subsidy_used

    return {
        "period": "lifetime",
        "requests": n_requests,
        "tokens_total": total_tk,
        "ads_delivered": n_ads,
        # advertiser side
        "ad_revenue": round(ad_revenue, 4),
        "guac_fee": round(guac_fee, 4),
        "sponsor_credits": round(sponsor_credits, 4),
        # user side
        "user_topups": round(user_topups, 4),
        "user_paid": round(user_paid, 4),
        "subsidy_used": round(subsidy_used, 4),
        "user_saving": round(user_saving, 4),
        "total_inference_billed": round(total_billed, 4),
        "guac_margin": round(guac_fee, 4),
        "split": {
            "sponsor_paid": round(ad_revenue, 4),
            "guac_kept": round(guac_fee, 4),
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
        "",
        "ADVERTISER MONEY",
        f"  sponsor paid       ${s['ad_revenue']:.2f}",
        f"  guac kept (fee)    ${s['guac_fee']:.2f}",
        f"  to user subsidies  ${s['sponsor_credits']:.2f}",
        "",
        "USER BILLING",
        f"  user top-ups       ${s['user_topups']:.2f}",
        f"  paid own money     ${s['user_paid']:.2f}",
        f"  covered by ads     ${s['subsidy_used']:.2f}",
        "",
        "USER SAVINGS",
        f"  tokens discounted  ${s['user_saving']:.2f}   (advertiser money)",
        "",
        "GUAC ECONOMICS",
        f"  margin (fee)       ${s['guac_margin']:.2f}",
        "",
        "Users pay wholesale cost for inference; sponsor money is drawn",
        "from their balance first. guac keeps only its fee.",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="guac settlement (paid-with-discount)")
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
