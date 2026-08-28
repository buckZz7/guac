"""guac settlement — turns the request ledger into real money.

Model B (wholesale savings flow to the user):

    guac sources cheap inference wholesale. The user pays near-cost, and
    advertiser money (beyond guac's fee) lowers their bill further. guac's
    whole margin is a small flat fee per sponsored offer.

    user_paid   = max(0, wholesale_cost − ad_pass_through)
    ad_pass_through = sponsor money − guac fee
    user_saving = retail_cost − user_paid      (captures cheap-supply + ads)
    guac_margin = guac fee                     (thin, honest, by design)

Conservation (always reconciles, incl. the cap):
    user_paid + ad_revenue == wholesale_cost + guac_fee + ad_surplus
    where ad_surplus = sponsor money that exceeded the user's full bill,
    carried forward as credit, never pocketed by guac.

The split is always public: sponsor → user, minus guac's fee. No hidden markup.
"""
import argparse
import datetime as _dt
import json

import config


def _today():
    return _dt.date.today().isoformat()


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


def _tokens(r):
    return r.get("prompt_tokens", 0) + r.get("completion_tokens", 0)


def settle(rows, ad_money_per_offer=None, fee_per_offer=0.10,
           retail_per_m=1.50, wholesale_per_m=None):
    """Option B settlement.

    ad_revenue comes from the LEDGER: each sponsored row carries its actual
    per-impression cost (`impression_cost`). This is the real money the
    advertiser was charged, not an estimate. `ad_money_per_offer` is kept as an
    optional override/fallback for rows without a recorded cost.

    fee_per_offer      : guac's flat fee per sponsored offer (F)
    retail_per_m       : market retail $/M tokens (R)
    wholesale_per_m    : what guac pays the source (W). Defaults to 35% of retail.
    """
    if wholesale_per_m is None:
        wholesale_per_m = retail_per_m * 0.35

    total_tk = sum(_tokens(r) for r in rows)
    sponsored = [r for r in rows if r.get("sponsored")]
    n_ads = len(sponsored)
    n_requests = len(rows)

    retail_cost = total_tk * retail_per_m / 1_000_000
    wholesale_cost = total_tk * wholesale_per_m / 1_000_000

    # Real ad revenue: sum each sponsored row's cost. Prefer the recorded
    # per-impression cost; if a row is missing it (legacy/edge), fall back to
    # the per-offer estimate so a sponsored impression is never worth $0.
    per_offer = ad_money_per_offer if ad_money_per_offer is not None else 0.30
    ad_revenue = 0.0
    for r in sponsored:
        c = r.get("impression_cost")
        ad_revenue += c if (c is not None and c > 0) else per_offer

    guac_fee = n_ads * fee_per_offer
    # Ad money passed through to the user. guac's fee comes out of the sponsor
    # money — it must never push the user's bill above wholesale. So clamp the
    # pass-through to [0, ad_revenue]: if the fee exceeds ad revenue, the
    # shortfall comes out of guac's margin, not the user's savings.
    ad_pass_through = max(0.0, ad_revenue - guac_fee)

    # User pays wholesale cost, minus the ad money passed through. Capped at 0.
    user_paid = wholesale_cost - ad_pass_through
    if user_paid < 0:
        user_paid = 0.0

    user_saving = retail_cost - user_paid
    wholesale_savings = retail_cost - wholesale_cost
    # Ads can cover at most the wholesale cost (beyond that the user is already
    # at $0); the two sources must always sum exactly to user_saving.
    ad_savings = min(ad_pass_through, wholesale_cost)
    # Sponsor money that went past covering the user's bill entirely — carried
    # forward as surplus (e.g. credit on the next statement), never pocketed.
    ad_surplus = max(0.0, ad_pass_through - wholesale_cost)

    guac_margin = guac_fee     # thin fee only; user keeps the cheap supply
    guac_fee = min(guac_fee, ad_revenue)  # guac can't earn more than advertisers paid

    return {
        "period": _today(),
        "requests": n_requests,
        "tokens_total": total_tk,
        "ads_delivered": n_ads,
        "ad_revenue": round(ad_revenue, 2),
        "guac_fee": round(guac_fee, 2),
        "wholesale_cost": round(wholesale_cost, 2),
        "retail_cost": round(retail_cost, 2),
        "user_paid": round(user_paid, 2),
        "user_saving": round(user_saving, 2),
        "savings_breakdown": {
            "from_cheap_supply": round(wholesale_savings, 2),
            "from_ads": round(ad_savings, 2),
            "ad_surplus_carried_forward": round(ad_surplus, 2),
        },
        "guac_margin": round(guac_margin, 2),
        "effective_user_rate_per_m": _rate(total_tk, user_paid),
        "retail_rate_per_m": retail_per_m,
        "wholesale_rate_per_m": round(wholesale_per_m, 4),
        "split": {
            "sponsor_paid": round(ad_revenue, 2),
            "guac_kept": round(guac_fee, 2),
            "user_saved": round(user_saving, 2),
        },
    }


def _rate(tokens, usd):
    per_m = (usd / tokens) * 1_000_000 if tokens else 0.0
    return round(per_m, 4)


def render_statement(s):
    d = s["savings_breakdown"]
    surplus_line = (
        f"    ads cover wholesale   ${d['from_ads']:.2f}"
        + (f"   (+ ${d['ad_surplus_carried_forward']:.2f} surplus → next bill)"
           if d["ad_surplus_carried_forward"] > 0 else "")
    )
    lines = [
        f"guac statement — {s['period']}",
        "─" * 48,
        f"requests             {s['requests']}",
        f"tokens               {s['tokens_total']:,}",
        f"ads delivered        {s['ads_delivered']}",
        "",
        "MONEY FLOW",
        f"  sponsor paid       ${s['ad_revenue']:.2f}   (for {s['ads_delivered']} offers)",
        f"  guac kept          ${s['guac_fee']:.2f}   (our fee)",
        "",
        "YOUR COST",
        f"  retail price       ${s['retail_cost']:.2f}   (at {s['retail_rate_per_m']}/M)",
        f"  wholesale cost     ${s['wholesale_cost']:.2f}   (at {s['wholesale_rate_per_m']}/M)",
        f"  you paid           ${s['user_paid']:.2f}",
        f"  effective rate     ${s['effective_user_rate_per_m']:.2f}/M",
        "",
        "YOU SAVED",
        f"  total              ${s['user_saving']:.2f}",
        f"    from cheap supply  ${d['from_cheap_supply']:.2f}",
        surplus_line,
        "",
        "GUAC ECONOMICS",
        f"  margin (fee)       ${s['guac_margin']:.2f}",
        "",
        "Guac keeps only its fee. The cheap-supply savings and the ad money "
        "both go to you.",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="guac settlement (Model B)")
    ap.add_argument("--ad-money-per-offer", type=float, default=0.30)
    ap.add_argument("--fee-per-offer", type=float, default=0.10)
    ap.add_argument("--retail-per-m", type=float, default=1.50)
    ap.add_argument("--wholesale-per-m", type=float, default=None)
    args = ap.parse_args()

    rows = _load_ledger_rows()
    if not rows:
        print("No ledger rows found. Run the gateway and make a request first.")
        return
    s = settle(rows, args.ad_money_per_offer, args.fee_per_offer,
               args.retail_per_m, args.wholesale_per_m)
    print(render_statement(s))
    print()
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
