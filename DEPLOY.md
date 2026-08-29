# Deploying guac to Fly.io

Live instance: `addguac` at `https://addguac.fly.dev`, single VM in `sjc`,
1GB volume `guac_data` mounted at `/data`. This box (`/opt/data/guac`) has
flyctl auth and git creds — deploy with:

```bash
cd /opt/data/guac
PATH="$HOME/.fly/bin:$PATH" flyctl deploy --detach
git add -A && git commit -m "..." && git push
```

Always run the suites first: `for t in test_*.py; do python $t; done`
(16 suites, all hermetic).

## Architecture on Fly

- **Volume `/data`** holds ALL persistent state: `users.json`,
  `advertisers.json`, `offers.json`, `state.json`, `ledger.jsonl`,
  `payments.jsonl`, `attribution.jsonl`, `supplier_state.json`,
  `magic_used.json`. Flat JSON/JSONL, append-only ledgers. Single-VM
  assumption — if you ever run >1 machine, move to SQLite/Postgres.
- **Dockerfile** ships runtime files only (no tests), plus `docs/`
  (served at `/pitch`, `/terms`, `/privacy`).
- `fly.toml`: auto-stop/start when idle (idle cost ≈ $0), internal port 8080.

## Secrets currently set (prod)

`ADGATE_GATEWAY_KEY`, `ADGATE_MAGIC_SECRET`, `ADGATE_PUBLIC_HOST`,
`OPENROUTER_API_KEY`, `ADGATE_DEV_MODE=0`, `ADGATE_SESSION_TTL_S=2592000`,
`ADGATE_DAILY_TOKEN_CAP=2000000`, `ADGATE_DISCOUNT_RATE=0.30`.

## Secrets NOT set yet (go-live checklist)

1. **OAuth** — `ADGATE_GITHUB_CLIENT_ID/_SECRET` (+ Google equivalents).
   Redirect: `https://addguac.fly.dev/auth/callback`. Until set, the portal
   login only works via magic link, which needs SMTP — so the portal is
   effectively closed. This is the #1 blocker for real users.
2. **Stripe** — `ADGATE_STRIPE_SECRET_KEY/_PUBLISHABLE/_WEBHOOK_SECRET`,
   `ADGATE_PAYMENTS_BACKEND=stripe`, `pip install stripe` (add to
   requirements.txt). Webhook: `/stripe/webhook`. Until set, top-ups run on
   the **mock backend** (credits instantly, no real money).
3. **SMTP** (only if keeping magic links) — `ADGATE_SMTP_HOST/_PORT/_USER/
   _PASS`, `ADGATE_EMAIL_FROM`.
4. **Supplier keys** — `CHUTES_API_KEY`, `ENGY_API_KEY` (OpenRouter is set).
   Without them those pool entries are skipped by the quality gate; traffic
   routes to OpenRouter.

## Money-model knobs

- `ADGATE_DISCOUNT_RATE` — global default discount (0.30).
- Per-model: `config.MODEL_DISCOUNTS` dict (code) — edit + deploy.
- Per-supplier: `discount` field in `suppliers.json` — edit + deploy.
- `ADGATE_IMPRESSION_COST` — advertiser charge per delivered footer (0.05).
- `ADGATE_ADS_PER_DAY` — user-facing cap (3).
- `ADGATE_ALLOW_DEMO_ADS` — must stay unset/0 in prod (fake inventory gate).

## Operator endpoints (master key: `Authorization: Bearer $ADGATE_GATEWAY_KEY`)

- `GET /dashboard` — operator stats (requests, impressions, funnel, pool)
- `GET /settle` — ledger-driven settlement statement (`?html=1` to render)
- `GET /backup` — full state bundle (all JSON files)
- `GET /_pool` — supplier quality state
- `GET /healthz` — deep health (suppliers + volume writable); alert on non-200

## Known limitations (by design, v1 scale)

- `payments.balance_for()` re-reads the ledger per call — fine at dozens of
  users, cache/DB at thousands.
- Flat files + single volume = one machine. Don't scale out without moving
  the money ledger to a real DB first.
- At most one request can ride past a zero balance before the 402 gate fires
  (billing happens after serving; the gate pre-flights the next request).
