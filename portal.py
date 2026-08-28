"""guac portal — self-serve sign-up for users and advertisers.

Dead simple by design:
  - A user signs up, gets an API key + a base_url. That's the whole onboarding.
  - An advertiser submits an offer + budget, and sees impressions/clicks.

Storage is flat JSON files (good enough for a v1 hosted service). In production
this would move to a real DB, but the shapes stay the same.
"""
import datetime as _dt
import json
import secrets

import config


# ---------------------------------------------------------------------------
# Users (API keys)
# ---------------------------------------------------------------------------

def _users():
    if not config.USERS_FILE.exists():
        return {}
    try:
        return json.loads(config.USERS_FILE.read_text())
    except Exception:
        return {}


def _save_users(users):
    config.USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.USERS_FILE.write_text(json.dumps(users, indent=2))


def create_user(email, ads_per_day=1):
    """Create a user, return their record (with a fresh API key)."""
    users = _users()
    if email in users:
        return None, "email already registered"
    api_key = "guac_" + secrets.token_hex(16)
    users[email] = {
        "email": email,
        "api_key": api_key,
        "ads_per_day": ads_per_day,
        "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "active": True,
    }
    _save_users(users)
    return users[email], None


def get_user_by_key(api_key):
    for u in _users().values():
        if u.get("api_key") == api_key:
            return u
    return None


def verify_gateway_key(api_key):
    """Accept either a user API key or the master gateway key."""
    if api_key == config.GATEWAY_KEY:
        return "master"
    u = get_user_by_key(api_key)
    return u.get("email") if u else None


def user_base_url():
    """The base_url a user points their agent at. Set by the operator."""
    host = config.PUBLIC_HOST or "http://127.0.0.1:8000"
    return f"{host.rstrip('/')}/v1"


# ---------------------------------------------------------------------------
# Advertisers / offers
# ---------------------------------------------------------------------------

def _offers():
    if not config.OFFERS_FILE.exists():
        return []
    try:
        data = json.loads(config.OFFERS_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_offers(offers):
    config.OFFERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.OFFERS_FILE.write_text(json.dumps(offers, indent=2))


def create_offer(advertiser, headline, body, claim, budget, offer_type="discount"):
    """Create an advertiser offer, return it (id assigned) or None on dup."""
    offers = _offers()
    oid = "sponsor-" + secrets.token_hex(4)
    offer = {
        "id": oid,
        "advertiser": advertiser,
        "headline": headline,
        "body": body,
        "claim": claim,
        "offer_type": offer_type,
        "budget": float(budget),
        "spent": 0.0,
        "active": True,
        "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    offers.append(offer)
    _save_offers(offers)
    return offer


def offer_stats():
    """Per-offer spend + delivery from the ledger + attribution."""
    offers = _offers()
    out = []
    for o in offers:
        out.append({
            "id": o["id"],
            "advertiser": o["advertiser"],
            "headline": o["headline"],
            "budget": o["budget"],
            "spent": o["spent"],
            "active": o["active"],
        })
    return out
