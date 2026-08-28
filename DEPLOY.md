# Deploying guac to Fly.io (browser-only — no local machine needed)

guac ships with a `Dockerfile` and `fly.toml` ready to deploy. You can do the
whole thing in the Fly web dashboard — no CLI, no local machine required.

## Prereq

One free Fly.io account. You can sign up with email or GitHub — no credit card
to start. → https://fly.io

## Steps (browser only)

1. **Sign up / log in** at https://fly.io

2. **Import the repo.** In the Fly dashboard:
   - Go to **Apps → Launch** (or "Create app").
   - Choose **"Import from GitHub"** / connect the `buckZz7/guac` repo
     (authorize Fly to read your GitHub repos).
   - Fly will detect the `fly.toml` + `Dockerfile` and prefill the config.

3. **Name the app** — e.g. `guac` (gives `https://guac.fly.dev`).

4. **Set the gateway key as a secret.** In the app's **Secrets** tab, add:
   - `ADGATE_GATEWAY_KEY` = a long random string (this is the key your agents
     and the portal use). Generate one, e.g. `openssl rand -hex 24`.

5. **Set the public host** (so sign-up returns the right `base_url`):
   - `ADGATE_PUBLIC_HOST` = `https://guac.fly.dev`

6. **Deploy.** Hit **Deploy**. Fly builds the Dockerfile and gives you a public
   HTTPS URL in ~2 minutes.

7. **Wire real inference suppliers.** The repo's `suppliers.json` points at real
   OpenAI-compatible endpoints (Chutes SN64 + OpenRouter), but their API keys come
   from env. In the app's **Secrets** tab add at least one:
   - `CHUTES_API_KEY` = a key from https://chutes.ai (cheap, SN64) — key starts `cpk_`
   - `OPENROUTER_API_KEY` = a key from https://openrouter.ai (fallback / many models)
   With no key set, the gateway has no healthy supplier and returns 503 for
   real requests. With one set, requests return real model answers.

8. **Verify:**
   - `https://guac.fly.dev/health` → `{"status":"ok"}`
   - `https://guac.fly.dev/dashboard` → the stats dashboard
   - `https://guac.fly.dev/v1/models` → OpenAI-compatible model list
   - `curl -X POST https://guac.fly.dev/v1/chat/completions -H "Authorization: Bearer <gateway-key>" -H "Content-Type: application/json" -d '{"model":"default","messages":[{"role":"user","content":"Say hi"}]}'`
     → a real model reply (proves suppliers are live)

## Using it

**Users sign up** (self-serve):
```
POST https://guac.fly.dev/signup
{"email": "you@example.com", "ads_per_day": 1}
```
→ returns `{ "api_key": "guac_...", "base_url": "https://guac.fly.dev/v1" }`

Then point an agent at it (Hermes):
```bash
hermes config set model.provider custom
hermes config set model.base_url https://guac.fly.dev/v1
hermes config set model.api_key <your-guac-api-key>
```

**Advertisers submit offers** (with the gateway key):
```
POST https://guac.fly.dev/advertiser/offer
{"advertiser": "Acme", "headline": "50% off hosting", "budget": 100.0}
```
Stats: `GET https://guac.fly.dev/advertiser/stats`

**Daily sponsorship delivery** — run `daily.py` once a day (e.g. a cron job) to
emit the "brought to you by" message for a user, and deliver it to their Telegram.

## Notes / gotchas

- **Supplier keys are secrets, never committed.** `suppliers.json` names the
  endpoints and the env var for each key (`key_env`), but the keys themselves are
  loaded from environment / Fly secrets at runtime. Set `CHUTES_API_KEY` and/or
  `OPENROUTER_API_KEY` before expecting real answers.
- **Model routing:** when a client sends `model: "default"` (or `guac`/blank),
  guac substitutes the supplier's pinned model (see `suppliers.json`). A concrete
  model slug passes through unchanged.
- **State persists** on a Fly volume mounted at `/data` (see `fly.toml`). Ledger,
  user accounts, offers, and supplier quality survive restarts.
- **Idle cost ≈ $0** — the VM auto-stops when unused and starts on demand
  (`fly.toml` auto_stop/auto_start). You pay only for what runs.
- If Fly asks you to add a volume during launch, accept it (that's the `/data`
  mount for durable state).
