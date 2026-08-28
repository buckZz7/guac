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
| `gateway.py` | OpenAI-compatible proxy: human-facing sponsorship, metering, routing, dashboard, attribution |
| `suppliers.py` | Quality-gated supplier pool with deterministic scoring + failover |
| `settlement.py` | Monthly statement from the ledger (Model B economics) |
| `config.py` | Env-driven configuration |
| `ads.json` | Sponsor offers |
| `suppliers.json` | Inference sources (SN64/SN53/SN28 + retail fallback) |
| `stub.py` | OpenAI-compatible stub upstream for tests |
| `test_*.py` | Test suites |

## Run

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
| `ADGATE_ADS_FILE` | `ads.json` | sponsor offers |
| `ADGATE_ADS_PER_DAY` | `1` | ads a user sees per day |
| `ADGATE_DISCOUNT_RATE` | `0.20` | advertiser-funded % off |
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
- Supplier quality gate + failover (done)
- Attribution callback (done)
- Dashboard (done)
- Point at real Bittensor suppliers (SN64/SN53/SN28) behind the quality gate
