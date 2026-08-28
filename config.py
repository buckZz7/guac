"""guac configuration — read from env, minimal by design."""
import json
import os
from pathlib import Path

BASE = Path(os.path.dirname(os.path.abspath(__file__)))

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

# Runtime state: per-user "today's ad count". Persisted so restarts don't spam.
STATE_FILE = Path(os.environ.get("ADGATE_STATE_FILE", str(BASE / "state.json")))

# How many ads a user sees per day (user chose this). Start at 1.
ADS_PER_DAY = int(os.environ.get("ADGATE_ADS_PER_DAY", "1"))

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

# Magic-link auth for the portal. Short-lived signed tokens, no passwords.
MAGIC_SECRET = os.environ.get("ADGATE_MAGIC_SECRET", "dev-magic-secret")
MAGIC_TTL_S = int(os.environ.get("ADGATE_MAGIC_TTL_S", "900"))

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
    with open(ADS_FILE) as f:
        return json.load(f)


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
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def log_ledger(entry):
    log_ledger_row(LEDGER_FILE, entry)


def log_ledger_row(path, entry):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
