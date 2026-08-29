# guac

OpenAI-compatible gateway that sits between an agent and its inference provider.
V1 is **decision-point sponsorship**: when the agent's answer is a final turn
that hands off to the user AND an offer's intent matches the topic, guac appends
a disclosed **`Sponsor:` footer** below the answer — for the human to see, never
fed into the model. It routes through a quality-gated pool of cheap suppliers
(with failover), meters the exact tokens, and applies a transparent,
advertiser-funded discount to the user's per-token cost.

There is no frequency knob — an ad is shown only when it's earned, at a genuine
decision point. Plain answers and mid-loop tool narration never qualify.

The user's discount is a lower price, not a credit. No wallets, no balances.

```
[agent] --base_url=guac--> [gateway] --quality-gated pool--> [suppliers]
   (Hermes/OpenClaw/Codex)     /|\                           (SN64/SN53/SN28/retail)
        user pays discounted rate <---|  advertiser money lowers it
   human sees "Sponsor: <sponsor>" below the answer, after a --- line (never the model)
```

## v1 design choice

The v1 sponsorship is **human-facing**, not agent-native. The gateway never
injects anything into the model's context (costs no tokens, never influences
inference). The disclosed footer is appended BELOW the answer, delimited by
`---`, so everything above the line is byte-identical to the model output.

The ad fires only when **all three** hold, deterministically:
1. **Final answer** — `finish_reason == "stop"` (mid-loop `tool_calls` turns never qualify)
2. **Handoff** — the answer poses a real decision to the user (ends in `?` or a handoff phrase)
3. **Topic match** — an offer's `intent` tag appears in the decision text; highest match wins

The later agent-native "hard buyer" version (the agent flagging real decision
points back to guac) can be layered on without changing the economics.

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
| `daily.py` | Retired — the old timer-based companion (wrong slot; superseded by decision-point footers) |
| `config.py` | Env-driven configuration |
| `ads.json` | Sponsor offers (fallback) |
| `suppliers.json` | Inference sources (Chutes SN64, engy SN53, OpenRouter; keys via env) |
| `stub.py` | OpenAI-compatible stub upstream for tests |
| `test_*.py` | Test suites |

## Portal (self-serve, live at /portal)

**Users sign up** — get an API key + base_url:
```
POST /signup    {"email": "..."}
                -> {"api_key": "guac_...", "base_url": "https://<host>/v1"}
```
Or use the web UI (`/portal`) — magic-link login, re-view your key.

**Advertisers** — magic-link login, no passwords:
- **Ad manager UI** (`/portal`): create offers, set budgets, pause/resume, see live impressions/spend
- **Per-impression billing**: each delivered sponsorship costs one impression; an offer auto-pauses when its budget is spent
- **API** (advertiser's own token, not the master key):
```
POST /advertiser/offer   {"headline","body","claim","budget","offer_type",
                          "intents":["hosting"],"image_url":"...","link":"..."}
GET  /advertiser/stats   -> offers scoped to that advertiser
```
`intents` (topic keywords) gate when the offer can appear at a decision point;
`image_url`/`link` render in the footer.

## Daily delivery (retired)

`daily.py` was the old timer-based companion — it fired once a day on a schedule,
which is the wrong slot. It's superseded by the decision-point footer: an ad now
appears only at a real decision moment, delivered inline with the answer it
belongs to. `daily.py` is kept for reference but is no longer the recommended
surface (and fires no cron).

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
| `GET /healthz` | Deep health check (app + supplier pool + state volume); 200 ok, 503 degraded |
| `GET /settle` | Operator settlement statement from the live ledger (master key) |
| `GET /backup` | Operator state backup — all persistent state as one JSON bundle (master key) |
| `GET /_pool` | Supplier pool quality state (debug) |

## Config (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `ADGATE_SUPPLIERS_FILE` | `suppliers.json` | inference source pool |
| `CHUTES_API_KEY` | (empty) | key for Chutes SN64 supplier (starts `cpk_`) |
| `ENGY_API_KEY` | (empty) | key for engy SN53 supplier (api.engy.ai) |
| `OPENROUTER_API_KEY` | (empty) | key for OpenRouter supplier |
| `ADGATE_ADS_FILE` | `ads.json` | sponsor offers |
| `ADGATE_DISCOUNT_RATE` | `0.20` | advertiser-funded % off on sponsored requests |
| `ADGATE_IMPRESSION_COST` | `0.01` | per-impression advertiser cost (budget ÷ cost = max impressions) |
| `ADGATE_MAGIC_SECRET` | `dev-magic-secret` | signs portal magic-link tokens (set a real secret in prod) |
| `ADGATE_MAGIC_TTL_S` | `900` | magic-link expiry (seconds) |
| `ADGATE_GATEWAY_KEY` | `dev-gateway-key` | key the agent sends |
| `ADGATE_STATE_FILE` | `state.json` | retained for backward compat (unused in V1) |
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
- Real suppliers wired (Chutes SN64, engy SN53, OpenRouter, keys via env) (done)
- Live hosted deploy at addguac.fly.dev (done)
- Add gm SN28 (saygm) as a supplier once invite access is granted (currently invite-gated waitlist)
- Real email delivery for magic links (currently dev-mode: link returned in response)
