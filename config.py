"""guac configuration — read from env, minimal by design."""
import json
import os
import threading
from pathlib import Path
BASE = Path(os.path.dirname(os.path.abspath(__file__)))

# Guards the runtime JSON/ledger writes. The gateway runs async handlers, so
# concurrent requests can otherwise race on the state + ledger files.
_LOCK = threading.RLock()

# Upstream real inference provider (OpenAI-compatible). Swap these to go live.
UPSTREAM_BASE = os.environ.get("ADGATE_UPSTREAM_BASE", "http://127.0.0.1:8001/v1")
UPSTREAM_KEY = os.environ.get("ADGATE_UPSTREAM_KEY", "")

# Where sponsor offers live (JSON list of offer dicts).
ADS_FILE = Path(os.environ.get("ADGATE_ADS_FILE", str(BASE / "ads.json")))

# Supplier pool (JSON list) — cheap inference sources + retail fallback.
SUPPLIERS_FILE = Path(os.environ.get("ADGATE_SUPPLIERS_FILE", str(BASE / "suppliers.json")))

# Persisted per-supplier quality state (survives restarts).
SUPPLIER_STATE_FILE = Path(os.environ.get("ADGATE_SUPPLIER_STATE_FILE",
                                          str(BASE / "supplier_state.json")))

# Runtime state file (per-user daily ad count, demand-gated).
STATE_FILE = Path(os.environ.get("ADGATE_STATE_FILE", str(BASE / "state.json")))

# Max sponsored offers a user sees per day (flat cap). Demand-gated: ads only
# show when a funded offer exists, up to this ceiling.
ADS_PER_DAY = int(os.environ.get("ADGATE_ADS_PER_DAY", "3"))

# Supplier quality scoring: latency below GRACE costs nothing (cheap inference
# is naturally 1-3s even when reliable); above it score decays to zero at HARD.
LATENCY_GRACE_MS = float(os.environ.get("ADGATE_LATENCY_GRACE_MS", "4000"))
LATENCY_HARD_MS = float(os.environ.get("ADGATE_LATENCY_HARD_MS", "15000"))

# The discount: users pay below market rate, on every request — sponsored or
# not. Advertiser revenue funds the gap. Discounts are PER MODEL (see
# MODEL_DISCOUNTS + supplier-level "discount" in suppliers.json). 0.30 = 30% off.
DISCOUNT_RATE = float(os.environ.get("ADGATE_DISCOUNT_RATE", "0.30"))

# Per-impression advertiser billing: each delivered "brought to you by" costs
# one impression; the advertiser's budget is the max impressions they fund.
# An offer auto-pauses when its budget is spent. Ad revenue is what keeps the
# user-facing discount funded.
IMPRESSION_COST = float(os.environ.get("ADGATE_IMPRESSION_COST", "0.05"))

# Flat blended wholesale $/M used when a passthrough model's real cost is not
# reported by the supplier (OpenRouter responses carry usage.cost when they
# have it; this is the honest fallback).
PASSTHROUGH_WHOLESALE_PER_M = float(
    os.environ.get("ADGATE_PASSTHROUGH_PER_M", "0.50"))

# Market reference rates ($/M prompt, completion) per pinned supplier — what
# the user would pay going direct. The user's rate is this minus the discount.
REFERENCE_PRICING = {
    "chutes-sn64": (0.60, 2.20),     # GLM-5.2 class, market reference
    "engy-sn53": (0.60, 2.20),
    "openrouter-paid": (0.25, 1.00),  # deepseek-chat-v3-0324 on OpenRouter
    "openrouter-free": (0.0, 0.0),
}

# Per-model discount overrides (model slug -> fraction off, 0.0-0.95).
# Resolution order for each request: explicit model entry here > the serving
# supplier's "discount" field > DISCOUNT_RATE. Frontier pass-through models
# default to NO discount (supplier discount 0.0): guac pays full market for
# them, so only models listed here get subsidized pricing.
MODEL_DISCOUNTS = {
    # "moonshotai/kimi-k2": 0.20,
}

# Serve the static ads.json demo inventory only when explicitly enabled.
# OFF by default: production must never show unfunded, unaffiliated offers.
ALLOW_DEMO_ADS = os.environ.get("ADGATE_ALLOW_DEMO_ADS", "0") == "1"

# Magic-link auth for the portal. Short-lived signed tokens, no passwords.
MAGIC_SECRET = os.environ.get("ADGATE_MAGIC_SECRET", "dev-magic-secret")
MAGIC_TTL_S = int(os.environ.get("ADGATE_MAGIC_TTL_S", "900"))
# Track used magic-link nonces so a link is one-time-use (can't be replayed).
MAGIC_USED_FILE = Path(os.environ.get("ADGATE_MAGIC_USED_FILE",
                                       str(BASE / "magic_used.json")))
# Dev mode: display the magic link on-screen instead of emailing it. MUST be
# off in production, or anyone who submits an email can log in as that user.
DEV_MODE = os.environ.get("ADGATE_DEV_MODE", "1") == "1"

# OAuth (GitHub / Google). When a provider's client id+secret are set, the
# portal offers that sign-in button. Otherwise it falls back to magic-link.
# Session cookie: signed with MAGIC_SECRET, short TTL.
GITHUB_CLIENT_ID = os.environ.get("ADGATE_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("ADGATE_GITHUB_CLIENT_SECRET", "")
GOOGLE_CLIENT_ID = os.environ.get("ADGATE_GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("ADGATE_GOOGLE_CLIENT_SECRET", "")
# Public base for building OAuth redirect URLs (must match provider settings).
OAUTH_BASE = os.environ.get("ADGATE_OAUTH_BASE", "")
SESSION_TTL_S = int(os.environ.get("ADGATE_SESSION_TTL_S", str(30 * 24 * 3600)))

# Email delivery for magic links (required when DEV_MODE is off). SMTP config.
# If SMTP_HOST is unset, login links are NOT delivered and the portal is
# effectively closed — set these before going live.
SMTP_HOST = os.environ.get("ADGATE_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("ADGATE_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("ADGATE_SMTP_USER", "")
SMTP_PASS = os.environ.get("ADGATE_SMTP_PASS", "")
EMAIL_FROM = os.environ.get("ADGATE_EMAIL_FROM", "")

# Ledger of metered usage (tokens + settlement). Plain JSON lines.
LEDGER_FILE = Path(os.environ.get("ADGATE_LEDGER_FILE", str(BASE / "ledger.jsonl")))

# Attribution ("click") log — agent reports when an offer was actually acted on.
ATTRIBUTION_FILE = Path(os.environ.get("ADGATE_ATTRIBUTION_FILE",
                                       str(BASE / "attribution.jsonl")))

# Auth token for the gateway itself (the key the agent sends us).
GATEWAY_KEY = os.environ.get("ADGATE_GATEWAY_KEY", "dev-gateway-key")

# Public base URL for the hosted service (used in sign-up responses).
PUBLIC_HOST = os.environ.get("ADGATE_PUBLIC_HOST", "")

# Portal storage — users (API keys) and advertiser offers/budgets.
USERS_FILE = Path(os.environ.get("ADGATE_USERS_FILE", str(BASE / "users.json")))
OFFERS_FILE = Path(os.environ.get("ADGATE_OFFERS_FILE", str(BASE / "offers.json")))
ADVERTISERS_FILE = Path(os.environ.get("ADGATE_ADVERTISERS_FILE",
                                        str(BASE / "advertisers.json")))

# How to identify a user. Default header the agent/gateway should send.
USER_ID_HEADER = "x-user-id"

# Abuse / quota limits (per-process counters; reset on restart).
SIGNUP_PER_IP_PER_HOUR = int(os.environ.get("ADGATE_SIGNUP_PER_IP_PER_HOUR", "10"))
# Max tokens a single user key may consume per day (0 = unlimited). Guards
# against a leaked/abused key burning unbounded upstream spend.
DAILY_TOKEN_CAP = int(os.environ.get("ADGATE_DAILY_TOKEN_CAP", "0"))

# Payments. Backend is "mock" (dev, no real money, no deps) or "stripe" (real
# money; requires STRIPE_* keys + a public webhook endpoint).
PAYMENTS_BACKEND = os.environ.get("ADGATE_PAYMENTS_BACKEND", "mock")
STRIPE_SECRET_KEY = os.environ.get("ADGATE_STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("ADGATE_STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("ADGATE_STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_CENTS = int(os.environ.get("ADGATE_STRIPE_PRICE_CENTS", "1000"))  # default top-up unit ($10)
# Advertiser money + user billing ledger (top-ups, impression charges,
# inference bills, sponsor credits). Plain JSON lines.
PAYMENTS_LEDGER = Path(os.environ.get("ADGATE_PAYMENTS_LEDGER",
                                      str(BASE / "payments.jsonl")))


def load_ads():
    if not ADS_FILE.exists():
        return []
    try:
        with open(ADS_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write under the lock: crash mid-write can't leave a truncated file.
    with _LOCK:
        tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)


def log_ledger(entry):
    log_ledger_row(LEDGER_FILE, entry)


def log_ledger_row(path, entry):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Serialize appends so concurrent requests write whole, non-interleaved lines.
    with _LOCK:
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
