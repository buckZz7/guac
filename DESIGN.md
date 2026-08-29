# guac — DESIGN

*Advertiser pays. User saves. Middleman stays small.*

**Version 6 — flat per-model discount, funded by ads.**

guac is an OpenAI-compatible gateway. Users prepay a balance and pay a
**discounted rate on every request** — the discount is set per model and is
funded by advertiser revenue from disclosed sponsorships. There is no free
tier, no rebate, and no credit mechanic: the discount is simply the price.

## The money model

```
user top-up ──> prepaid balance ──(bill every request)──> gone
                                       │
                    bill = market price × (1 − model discount)

advertiser top-up ──> ad budget ──(per delivered impression)──> ad revenue
                                                                │
                                              funds the discount gap
```

- **Discount resolution per request:** `MODEL_DISCOUNTS[model]` →
  supplier `discount` field → global `DISCOUNT_RATE` (default 30%).
- **Frontier pass-through defaults to 0% discount** (guac pays the provider
  full market price for those tokens; only models listed get subsidized
  pricing until ad revenue or a wholesale deal justifies more).
- **Quality-gated pools** (Chutes GLM, Engy) carry the biggest discounts —
  the spread between market reference and actual wholesale partly
  self-funds.
- The bill dict on each ledger row: `{cost, discount_rate, unpaid}`.
  Empty balance → 402; at most one request can ride past the balance before
  the pre-flight gate fires.

## Sponsorship (the ad inventory)

A disclosed `Sponsor:` footer is appended BELOW final answers
(`finish_reason == "stop"`), up to `ADS_PER_DAY` per user, only when a
funded offer exists (advertiser prepaid balance with budget remaining).
Everything above the `---` divider is byte-identical to model output — the
gateway never injects anything into the model.

The demo `ads.json` inventory is gated behind `ADGATE_ALLOW_DEMO_ADS=1`
(off in production) — no unfunded, unaffiliated brand offers ever serve to
real users.

The footer's link is absolute and routed through `/go/<offer_id>` so clicks
are metered before redirect. Inbound assistant history is stripped of guac's
own footers before forwarding, so replayed sessions never re-inject ad text
or re-bill it (matters for Hermes-style agents that replay full history).

## Advertiser side

Prepaid balance is the source of truth. One offer = headline, body, claim,
budget, optional image/link. Each delivered impression debits
`IMPRESSION_COST` ($0.05 default); budget exhausted → auto-pause. Stats and
click funnel (impressions → clicks → redemptions) come straight from the
ledgers. Form endpoints authenticate by advertiser token, never by email.

## The honest tension

On pass-through frontier models, guac pays market price upstream while the
user pays the discounted price — the gap is covered only by ad revenue.
guac is therefore an ad-funded volume business: distribution (agents
routing through guac) and advertiser inventory are the moat, not token
margin. The quality-gated pools improve the math because their actual
wholesale sits below the market reference used for billing.

## Billing identity

The billing identity is the KEY OWNER (user key / master key / advertiser
token). The `x-user-id` header overrides identity only for the master key
(operator/testing) — a user cannot bill onto someone else's balance by
spoofing it.

## Site

Dark design system (near-black, emerald accent, Inter). `/` is 100%
user-facing; advertisers get `/advertisers` and the full pitch at `/pitch`.
A live ledger meter (requests served, sponsorships delivered, discounted
billing) renders on the landing page when data exists.

## Next layer

Agent-native tier (offers delivered to agents that decide/buy, act-based
billing) — see [`docs/AGENT_TIER.md`](AGENT_TIER.md). Not built; the v1
human-facing model exists to prove the economics first.
