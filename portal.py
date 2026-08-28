"""guac portal — self-serve sign-up for users and advertisers.

Users get one choice (ads/day) and an API key; advertisers get an account,
an ad manager, and per-impression billing. All auth is magic-link (no
passwords). Dev-mode returns the magic link in the response instead of
emailing it.
"""
import datetime as _dt
import hashlib
import hmac
import json
import secrets

import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Users (API keys)
# ---------------------------------------------------------------------------

def _users():
    return _read_json(config.USERS_FILE, {})


def _save_users(users):
    _write_json(config.USERS_FILE, users)


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
        "created": _now().isoformat(),
        "active": True,
    }
    _save_users(users)
    return users[email], None


def get_user_by_key(api_key):
    for u in _users().values():
        if u.get("api_key") == api_key:
            return u
    return None


def get_user_by_email(email):
    return _users().get(email)


def update_user(email, **fields):
    users = _users()
    if email not in users:
        return None
    users[email].update(fields)
    _save_users(users)
    return users[email]


def verify_gateway_key(api_key):
    """Accept either a user API key, the master gateway key, or an
    advertiser's token."""
    if api_key == config.GATEWAY_KEY:
        return "master"
    u = get_user_by_key(api_key)
    if u:
        return u.get("email")
    a = get_advertiser_by_token(api_key)
    if a:
        return f"advertiser:{a['email']}"
    return None


def user_base_url():
    """The base_url a user points their agent at. Set by the operator."""
    host = config.PUBLIC_HOST or "http://127.0.0.1:8000"
    return f"{host.rstrip('/')}/v1"


# ---------------------------------------------------------------------------
# Advertisers
# ---------------------------------------------------------------------------

def _advertisers():
    return _read_json(config.ADVERTISERS_FILE, {})


def _save_advertisers(ads):
    _write_json(config.ADVERTISERS_FILE, ads)


def create_advertiser(email):
    """Create an advertiser account, return it (with a fresh token)."""
    ads = _advertisers()
    email = email.strip().lower()
    if email in ads:
        return None, "email already registered"
    token = "adv_" + secrets.token_hex(16)
    ads[email] = {
        "email": email,
        "token": token,
        "created": _now().isoformat(),
        "active": True,
    }
    _save_advertisers(ads)
    return ads[email], None


def get_advertiser(email):
    return _advertisers().get(email.strip().lower())


def get_advertiser_by_token(token):
    for a in _advertisers().values():
        if a.get("token") == token:
            return a
    return None


# ---------------------------------------------------------------------------
# Magic-link auth (signed, short-lived, one-time-use, no passwords)
# ---------------------------------------------------------------------------

def _sign(msg):
    return hmac.new(config.MAGIC_SECRET.encode(), msg.encode(),
                    hashlib.sha256).hexdigest()


def _used_nonces():
    return _read_json(config.MAGIC_USED_FILE, [])


def _save_used_nonces(nonces):
    _write_json(config.MAGIC_USED_FILE, nonces)


def make_magic_token(role, email, ttl=None):
    """Role + email + nonce + expiry, signed. Nonce makes it one-time-use."""
    nonce = secrets.token_hex(16)
    exp = int(_now().timestamp()) + (ttl or config.MAGIC_TTL_S)
    payload = f"{role}|{email}|{nonce}|{exp}"
    sig = _sign(payload)
    return f"{payload}|{sig}"


def verify_magic_token(token):
    """Return (role, email) if valid, unexpired, and not already used."""
    try:
        role, email, nonce, exp, sig = token.split("|")
        # Reject already-used links (one-time use) before anything else.
        used = _used_nonces()
        if nonce in used:
            return None
        if not hmac.compare_digest(_sign(f"{role}|{email}|{nonce}|{exp}"), sig):
            return None
        if int(exp) <= int(_now().timestamp()):
            return None
        # Mark used so a leaked/replayed link can't log in again.
        used.append(nonce)
        _save_used_nonces(used)
        return role, email
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Offers / per-impression billing
# ---------------------------------------------------------------------------

def _offers():
    return _read_json(config.OFFERS_FILE, [])


def _save_offers(offers):
    _write_json(config.OFFERS_FILE, offers)


def create_offer(advertiser_email, headline, body, claim, budget, offer_type="discount"):
    """Create an advertiser offer. budget = max impressions (per-impression)."""
    offers = _offers()
    oid = "sponsor-" + secrets.token_hex(4)
    offer = {
        "id": oid,
        "advertiser": advertiser_email,
        "headline": headline,
        "body": body,
        "claim": claim,
        "offer_type": offer_type,
        "budget": float(budget),
        "impressions": 0,          # delivered "brought to you by" count
        "spent": 0.0,
        "active": True,
        "paused": False,
        "created": _now().isoformat(),
    }
    offers.append(offer)
    _save_offers(offers)
    return offer


def get_offer(offer_id):
    for o in _offers():
        if o["id"] == offer_id:
            return o
    return None


def set_offer_paused(offer_id, paused):
    offers = _offers()
    for o in offers:
        if o["id"] == offer_id:
            o["paused"] = bool(paused)
            _save_offers(offers)
            return o
    return None


def charge_impression(offer_id):
    """Record one delivered impression. Returns the offer if still active,
    else None. Auto-pauses when the budget is spent."""
    offers = _offers()
    for o in offers:
        if o["id"] == offer_id:
            o["impressions"] += 1
            o["spent"] = o["impressions"] * config.IMPRESSION_COST
            if o["spent"] >= o["budget"]:
                o["active"] = False
                o["paused"] = True
            _save_offers(offers)
            return o
    return None


def offers_for_advertiser(email):
    return [o for o in _offers() if o.get("advertiser") == email]


def offer_stats_for(email):
    return [{
        "id": o["id"],
        "advertiser": o.get("advertiser"),
        "headline": o["headline"],
        "offer_type": o["offer_type"],
        "budget": o["budget"],
        "spent": o["spent"],
        "impressions": o["impressions"],
        "active": o["active"],
        "paused": o["paused"],
    } for o in offers_for_advertiser(email)]


def offer_stats():
    """All offers (operator view)."""
    return [{
        "id": o["id"],
        "advertiser": o["advertiser"],
        "headline": o["headline"],
        "budget": o["budget"],
        "spent": o["spent"],
        "impressions": o["impressions"],
        "active": o["active"],
    } for o in _offers()]
