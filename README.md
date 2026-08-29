# guac

OpenAI-compatible inference gateway with a **flat, per-model discount funded
by disclosed advertising**.

Users prepay a balance and pay **below market rate on every request** — the
discount is set per model (quality-gated open pools carry the biggest cuts;
frontier pass-through rides at market until ad revenue covers it). A few
answers a day carry a disclosed `Sponsor:` footer below them; that advertiser
revenue is what funds the gap. The model output itself is never touched.

```
[user agent] --base_url=guac--> [gateway] --quality-gated pool--> [suppliers]
   any OpenAI client              |   |                           (Chutes/Engy/OpenRouter)
   pays discounted rate <---------+   |
                                      +--> disclosed "Sponsor:" footer below
                                           a few final answers (never in-model)
```

## The model, in one line

**Advertiser money lowers the user's token price — baked into the rate, not
credited back.** No rebates, no coupons, no credit mechanics to understand.

- Every request bills `market price × (1 − model discount)` against the
  user's prepaid balance.
- Discount resolution: `config.MODEL_DISCOUNTS[model]` > supplier `discount`
  field (suppliers.json) > global `ADGATE_DISCOUNT_RATE` (default 0.30).
- Empty balance → HTTP 402 `insufficient_balance`.
- Ads are demand-gated: a footer appears only on final answers
  (`finish_reason == "stop"`), under a daily cap, when a funded offer exists.
  No funded advertiser → no ads at all.

## What's here

- `gateway.py` — FastAPI app: routing, billing, sponsorship, portal routes
- `payments.py` — money ledger (user top-ups, advertiser balances, billing)
- `settlement.py` — ledger-driven lifetime statement (`/settle`, master key)
- `suppliers.py` — quality-gated supplier pool with failover + recovery
- `portal.py` / `portal_html.py` — accounts, ad manager, dark-themed site
- `oauth.py` — GitHub + Google sign-in (magic-link fallback)
- `config.py` — all knobs, env-driven (`ADGATE_*`)
- `docs/` — DESIGN, DEPLOY, advertiser pitch, positioning, agent tier, ToS, privacy

## Quick start (dev)

```bash
python gateway.py --port 8000          # stub-friendly defaults, dev mode
for t in test_*.py; do python $t; done # 16 suites, all hermetic
```

## Production

Live at `https://addguac.fly.dev` (Fly.io, single VM + `/data` volume).
See [`DEPLOY.md`](DEPLOY.md) for the full runbook and
[`DESIGN.md`](DESIGN.md) for the money model.

## The honest tension

On passthrough frontier models guac pays the provider market price while the
user pays the discounted price — the gap is only covered by ad revenue (or
supplier spread on the quality-gated pools). The business is therefore an
ad-funded volume play: distribution (agents routing through guac) and
inventory (funded advertisers) are the moat, not token margin.
