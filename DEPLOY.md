# Deploying guac to Fly.io (browser-only — no local machine needed)

guac ships with a `Dockerfile` and `fly.toml` ready to deploy. You can do the
whole thing in the Fly web dashboard — no CLI, no local machine required.

> **Why dashboard, not CLI:** the `flyctl` CLI login requires an API token.
> If your Fly org uses **Single Sign-On (SSO)**, personal access tokens are
> blocked (Fly returns *"Access Tokens cannot be created ... an organization
> you are a member of requires SSO"*). The web dashboard rides your already
> logged-in browser session, so it works normally with SSO. Use this path.

## Prereq

One free Fly.io account, signed in at https://fly.io.

## Steps (browser only)

1. **Sign up / log in** at https://fly.io.

2. **Import the repo.** In the Fly dashboard:
   - Go to **Apps → Launch** (or **Create app**).
   - Choose **"Import from GitHub"** / connect the `buckZz7/guac` repo
     (authorize Fly to read your GitHub repos).
   - Fly detects the `fly.toml` + `Dockerfile` and prefills the config.

3. **Name the app** — e.g. `guac` (gives `https://guac.fly.dev`).
   - If that name is taken, pick another (e.g. `guac-gateway`) and then update
     `ADGATE_PUBLIC_HOST` to match (step 5).

4. **Accept the volume.** Fly will ask to create the volume for `/data`
   (`guac_data`, in `fly.toml`). Accept it — that's where ledger, accounts,
   offers, and supplier quality persist.

5. **Set the public host.** In the app's **Secrets** tab, add:
   - `ADGATE_PUBLIC_HOST` = `https://<your-app-name>.fly.dev`
     (so sign-up returns the correct `base_url`)

6. **Set a real gateway key.** Also in **Secrets**:
   - `ADGATE_GATEWAY_KEY` = a long random string. This is the key your agents
     and the portal use. Generate one, e.g. `openssl rand -hex 24`.
   - Do NOT leave it unset in production — without it the gateway falls back
     to the public `dev-gateway-key`.

7. **Set real supplier keys (for actual inference).** In **Secrets**:
   - `CHUTES_API_KEY` = your Chutes SN64 key (starts `cpk_`)
   - `OPENROUTER_API_KEY` = your OpenRouter key (optional retail fallback)
   - Without at least one supplier key, `/v1/chat/completions` returns
     `502 all suppliers failed` — the quality gate correctly rejects empty-key
     suppliers. `/health`, `/v1/models`, `/signup`, `/dashboard`, and `/portal`
     all still work regardless.

8. **Set the portal magic-link secret.** In **Secrets**:
   - `ADGATE_MAGIC_SECRET` = a long random string. This signs portal login
     links. Generate one, e.g. `openssl rand -hex 32`. Without it, the dev
     default is used, which anyone could forge.

9. **Deploy.** Hit **Deploy**. Fly builds the Dockerfile and gives you a public
   HTTPS URL in ~2 minutes.

10. **Verify:**
    - `https://<app>.fly.dev/health` → `{"status":"ok"}`
    - `https://<app>.fly.dev/dashboard` → the stats dashboard
    - `https://<app>.fly.dev/v1/models` → OpenAI-compatible model list
    - `https://<app>.fly.dev/portal` → the self-serve portal

## Using it

**Portal (recommended)** — self-serve web UI at `https://<app>.fly.dev/portal`:
- Users: magic-link login, view/re-copy API key + base_url, adjust ads/day
- Advertisers: magic-link login, ad manager (create/pause/toggle offers), per-impression billing

**Users sign up** (API):
```
POST https://<app>.fly.dev/signup
{"email": "you@example.com", "ads_per_day": 1}
```
→ returns `{ "api_key": "guac_...", "base_url": "https://<app>.fly.dev/v1" }`

Then point an agent at it (Hermes):
```bash
hermes config set model.provider custom
hermes config set model.base_url https://<app>.fly.dev/v1
hermes config set model.api_key <your-guac-api-key>
```

**Advertisers** (API, their own token):
```
POST https://<app>.fly.dev/advertiser/offer
{"headline": "50% off hosting", "budget": 100.0}
```
Stats: `GET https://<app>.fly.dev/advertiser/stats`

**Daily sponsorship delivery** — run `daily.py` once a day (e.g. a cron job) to
emit the "brought to you by" message for a user, and deliver it to their Telegram.

## Gotchas

- **Supplier keys are required for live inference.** Completions route through
  the quality-gated pool in `suppliers.json`. Empty keys → `502 all suppliers
  failed`. Add real keys as secrets (step 7) to serve actual model requests.
- **The gateway key is a secret, not env.** `fly.toml` intentionally does not
  set `ADGATE_GATEWAY_KEY` (it's committed to a public repo). Set it as a
  secret; Fly secrets override env.
- **State persists** on a Fly volume mounted at `/data` (see `fly.toml`).
  Ledger, user accounts, offers, and supplier quality survive restarts.
- **Idle cost ≈ $0** — the VM auto-stops when unused and starts on demand
  (`fly.toml` auto_stop/auto_start). You pay only for what runs.
- **SSO note:** if `flyctl` ever says you need a token, create a per-org token
  with `flyctl tokens org <org-name>` from a machine you've done `flyctl auth
  login` on — but the dashboard import above avoids all of that.
