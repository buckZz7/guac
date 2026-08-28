# guac

OpenAI-compatible gateway that sits between an agent and its inference provider.
V1 is human-facing sponsorship: when a sponsored offer is due, guac attaches a
disclosed **"brought to you by"** payload to the response — for the human to see,
never fed into the model. It routes through a quality-gated pool of cheap
suppliers (with failover), meters the exact tokens, and applies a transparent,
advertiser-funded discount to the user's per-token cost.

The user's discount is a lower price, not a credit. No wallets, no balances.

```
[agent] --base_url=guac--> [gateway] --quality-gated pool--> [suppliers]
   (Hermes/OpenClaw/Codex)     /|\                           (SN64/SN53/SN28/retail)
        user pays discounted rate <---|  advertiser money lowers it
   human sees "Brought to you by <sponsor>" on the response (never the model)
```

## v1 design choice

The v1 sponsorship is **human-facing**, not agent-native. The gateway never
injects anything into the model's context (costs no tokens, never influences
inference). The disclosed sponsorship rides on the response for the human.
The later agent-native "hard buyer" version can be layered on without changing
the economics.

## Model

The settlement is fully transparent — the split is always public:

```
retail_cost     = tokens × retail $/M
wholesale_cost  = tokens × wholesale $/M      (what guac pays the source)
ad_revenue      = offers × $/offer             (what sponsors paid)
guac_fee        = offers × fee                 (guac's whole margin)

user_paid   = max(0, wholesale_cost − (ad_revenue − guac_fee))
user_saving = retail_cost − user_paid          (cheap-supply + ad money)
guac_margin = guac_fee                          (thin, honest, by design)
```

Guac keeps only its fee. The cheap-supply savings and the ad money both go to the
user. Full rationale in [DESIGN.md](DESIGN.md).

## Components

| File | Purpose |
|------|---------|
| `gateway.py` | OpenAI-compatible proxy: sponsorship, metering, routing, dashboard, attribution, portal routes |
| `suppliers.py` | Quality-gated supplier pool with deterministic scoring + failover + recovery |
| `settlement.py` | Monthly statement from the ledger (Model B economics) |
| `portal.py` | Self-serve sign-up (users) + advertiser accounts/offers + per-impression billing + magic-link auth |
| `portal_html.py` | Server-rendered HTML UI for the portal (user + advertiser consoles) |
| `daily.py` | Emits the daily "brought to you by" sponsorship (companion delivery) |
| `config.py` | Env-driven configuration |
| `ads.json` | Sponsor offers (fallback) |
| `suppliers.json` | Inference sources (Chutes SN64 + OpenRouter; keys via env) |
| `stub.py` | OpenAI-compatible stub upstream for tests |
| `test_*.py` | Test suites |

## Portal (self-serve, live at /portal)

**Users sign up** — get an API key + base_url:
```
POST /signup    {"email": "...", "ads_per_day": 1}
                -> {"api_key": "guac_...", "base_url": "https://<host>/v1"}
```
Or use the web UI (`/portal`) — magic-link login, re-view your key, adjust ads/day.

**Advertisers** — magic-link login, no passwords:
- **Ad manager UI** (`/portal`): create offers, set budgets, pause/resume, see live impressions/spend
- **Per-impression billing**: each delivered "brought to you by" costs one impression; an offer auto-pauses when its budget is spent
- **API** (advertiser's own token, not the master key):
```
POST /advertiser/offer   {"headline","body","claim","budget","offer_type"}
GET  /advertiser/stats   -> offers scoped to that advertiser
```

## Daily delivery

`daily.py` emits the day's human-facing sponsorship:
```
.venv/bin/python daily.py
# -> ✨ Brought to you by <sponsor> — <headline>. / Redeem: ...
```
Run it once a day (a cron job) and deliver the output — e.g. a no_agent Hermes
cron to Telegram. Zero LLM tokens by design.

## Deploy (hosted service)

guac is built to run as a hosted service. The Dockerfile + fly.toml deploy it to
[Fly.io](https://fly.io) — a cheap, per-second-billed Linux VM that gives a
public HTTPS URL. Idle cost ≈ $0. **You can do the whole deploy in the browser
— no local machine needed** (see [DEPLOY.md](DEPLOY.md) for the exact click-path).

```bash
# one-time
curl -L https://fly.io/install.sh | sh
fly auth login

# from the repo root
fly launch --name guac
fly secrets set ADGATE_GATEWAY_KEY="<your-key>"
fly deploy

# you get: https://guac.fly.dev/v1
# users point their agent at it: base_url = https://guac.fly.dev/v1
```

State (ledger, cadence, supplier quality) persists on a Fly volume mounted at
`/data` (see `fly.toml`).

## Run (local dev)

```bash
# 1. Configure real upstream(s) in suppliers.json (or set ADGATE_SUPPLIERS_FILE).
# 2. Run the gateway
.venv/bin/python gateway.py --port 8000

# 3. Point any OpenAI-compatible agent at it:
#    base_url = http://<host>:8000/v1
#    api_key  = ADGATE_GATEWAY_KEY
```

Hermes (custom provider):

```bash
hermes config set model.provider custom
hermes config set model.base_url http://<host>:8000/v1
hermes config set model.api_key dev-gateway-key
```

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/chat/completions` | OpenAI-compatible inference (ad-aware) |
| `POST /v1/guac/attribution` | Agent reports it acted on an offer (the "click") |
| `GET /dashboard` | Impressions + clicks + supplier quality |
| `GET /_pool` | Supplier pool quality state (debug) |

## Config (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `ADGATE_SUPPLIERS_FILE` | `suppliers.json` | inference source pool |
| `CHUTES_API_KEY` | (empty) | key for Chutes SN64 supplier (starts `cpk_`) |
| `OPENROUTER_API_KEY` | (empty) | key for OpenRouter supplier |
| `ADGATE_ADS_FILE` | `ads.json` | sponsor offers |
| `ADGATE_ADS_PER_DAY` | `1` | ads a user sees per day |
| `ADGATE_DISCOUNT_RATE` | `0.20` | advertiser-funded % off |
| `ADGATE_IMPRESSION_COST` | `0.01` | per-impression advertiser cost (budget ÷ cost = max impressions) |
| `ADGATE_MAGIC_SECRET` | `dev-magic-secret` | signs portal magic-link tokens (set a real secret in prod) |
| `ADGATE_MAGIC_TTL_S` | `900` | magic-link expiry (seconds) |
| `ADGATE_GATEWAY_KEY` | `dev-gateway-key` | key the agent sends |
| `ADGATE_STATE_FILE` | `state.json` | per-user ad cadence |
| `ADGATE_LEDGER_FILE` | `ledger.jsonl` | metered usage + settlement |
| `ADGATE_ATTRIBUTION_FILE` | `attribution.jsonl` | click log |
| `ADGATE_SUPPLIER_STATE_FILE` | `supplier_state.json` | measured quality |

## Test

```bash
.venv/bin/python test_gateway.py        # injection + metering + discount
.venv/bin/python test_settlement.py     # money flow + transparent split
.venv/bin/python test_integration.py    # failover + attribution + dashboard
```

## Roadmap

- Settlement module (done, Model B)
- Supplier quality gate + failover + recovery (done)
- Attribution callback (done)
- Dashboard (done)
- Portal: user sign-up + advertiser offers/stats (done)
- Portal: magic-link auth + advertiser ad manager + per-impression billing (done)
- Daily sponsorship delivery (done)
- Real suppliers wired (Chutes SN64 + OpenRouter, keys via env) (done)
- Live hosted deploy at addguac.fly.dev (done)
- Wire more Bittensor subnets (SN53/SN28) into the quality pool as they come online
- Real email delivery for magic links (currently dev-mode: link returned in response)
