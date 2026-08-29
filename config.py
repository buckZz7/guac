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

# Runtime state file (kept for backward compat; no longer used for ad cadence —
# V1 shows ads only at decision points, with no per-day frequency knob).
STATE_FILE = Path(os.environ.get("ADGATE_STATE_FILE", str(BASE / "state.json")))

# Supplier quality scoring: latency below GRACE costs nothing (cheap inference
# is naturally 1-3s even when reliable); above it score decays to zero at HARD.
LATENCY_GRACE_MS = float(os.environ.get("ADGATE_LATENCY_GRACE_MS", "4000"))
LATENCY_HARD_MS = float(os.environ.get("ADGATE_LATENCY_HARD_MS", "15000"))

# Advertiser-funded discount the user gets off their token cost. 0.20 = 20% off.
DISCOUNT_RATE = float(os.environ.get("ADGATE_DISCOUNT_RATE", "0.20"))

# Per-impression advertiser billing: each delivered "brought to you by" costs
# one impression; the advertiser's budget is the max impressions they fund.
# An offer auto-pauses when its budget is spent.
IMPRESSION_COST = float(os.environ.get("ADGATE_IMPRESSION_COST", "0.01"))

# Real per-model wholesale ($/M tokens) that guac pays its suppliers, keyed by
# supplier name (from suppliers.json). Used by settlement so the transparent
# split reflects real inference cost, not a flat 35%-of-retail guess.
# Format: {supplier: (prompt_per_m, completion_per_m)}
MODEL_PRICING = {
    "openrouter": (0.25, 1.00),     # deepseek-chat-v3-0324 on OpenRouter
    "chutes-sn64": (0.05, 0.30),    # approx open-model wholesale on Chutes
    "engy-sn53": (0.20, 0.80),      # approx open-model wholesale on engy
}

# Magic-link auth for the portal. Short-lived signed tokens, no passwords.
MAGIC_SECRET = os.environ.get("ADGATE_MAGIC_SECRET", "dev-magic-secret")
MAGIC_TTL_S = int(os.environ.get("ADGATE_MAGIC_TTL_S", "900"))
# Track used magic-link nonces so a link is one-time-use (can't be replayed).
MAGIC_USED_FILE = Path(os.environ.get("ADGATE_MAGIC_USED_FILE",
                                       str(BASE / "magic_used.json")))

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
