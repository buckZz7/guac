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
import os
import secrets
import threading

import config

# Guards all read-modify-write on the flat-JSON store. uvicorn runs async
# handlers; without a lock, two concurrent requests can read-modify-write the
# same file and lose an update (e.g. two impressions charged but one counted).
# All portal mutations go through this lock.
_LOCK = threading.RLock()


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
    # Atomic write: write to a temp file in the same dir, then rename over the
    # target. A crash mid-write can't leave a truncated/corrupt store.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _mutate(load, save, fn):
    """Run a read-modify-write under the lock: load, apply fn, save."""
    with _LOCK:
        data = load()
        result = fn(data)
        save(data)
        return result


# ---------------------------------------------------------------------------
# Users (API keys)
# ---------------------------------------------------------------------------

def _users():
    return _read_json(config.USERS_FILE, {})


def _save_users(users):
    _write_json(config.USERS_FILE, users)


def create_user(email, ads_per_day=1):
    """Create a user, return their record (with a fresh API key)."""
    def _apply(users):
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
        return users[email], None
    return _mutate(_users, _save_users, _apply)


def get_user_by_key(api_key):
    for u in _users().values():
        if u.get("api_key") == api_key:
            return u
    return None


def get_user_by_email(email):
    return _users().get(email)


def update_user(email, **fields):
    def _apply(users):
        if email not in users:
            return None
        users[email].update(fields)
        return users[email]
    return _mutate(_users, _save_users, _apply)


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
    email = email.strip().lower()
    def _apply(ads):
        if email in ads:
            return None, "email already registered"
        token = "adv_" + secrets.token_hex(16)
        ads[email] = {
            "email": email,
            "token": token,
            "created": _now().isoformat(),
            "active": True,
        }
        return ads[email], None
    return _mutate(_advertisers, _save_advertisers, _apply)


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


def create_offer(advertiser_email, headline, body, claim, budget, offer_type="discount",
                 intents=None, image_url="", link=""):
    """Create an advertiser offer. budget = max impressions (per-impression).
    intents: list of topic keywords that gate when the offer can appear
    (decision-point matching). image_url/link: creative for the footer."""
    def _apply(offers):
        oid = "sponsor-" + secrets.token_hex(4)
        offer = {
            "id": oid,
            "advertiser": advertiser_email,
            "headline": headline,
            "body": body,
            "claim": claim,
            "offer_type": offer_type,
            "intents": [str(k).strip() for k in (intents or []) if str(k).strip()],
            "image_url": image_url,
            "link": link,
            "budget": float(budget),
            "impressions": 0,          # delivered sponsorships count
            "spent": 0.0,
            "active": True,
            "paused": False,
            "created": _now().isoformat(),
        }
        offers.append(offer)
        return offer
    return _mutate(_offers, _save_offers, _apply)


def get_offer(offer_id):
    for o in _offers():
        if o["id"] == offer_id:
            return o
    return None


def set_offer_paused(offer_id, paused):
    def _apply(offers):
        for o in offers:
            if o["id"] == offer_id:
                o["paused"] = bool(paused)
                return o
        return None
    return _mutate(_offers, _save_offers, _apply)


def charge_impression(offer_id):
    """Record one delivered impression. Returns (offer, cost) if the offer
    exists, else (None, 0.0). Auto-pauses when the budget is spent.
    Thread-safe: the read-modify-write is atomic under the portal lock, so two
    concurrent requests can't lose an impression count."""
    def _apply(offers):
        for o in offers:
            if o.get("id") == offer_id:
                # Defensive: offers loaded from static ads.json (or other
                # sources) may not carry portal bookkeeping fields.
                o["impressions"] = o.get("impressions", 0) + 1
                o["spent"] = o.get("spent", 0.0) + config.IMPRESSION_COST
                if o["spent"] >= o.get("budget", 0):
                    o["active"] = False
                    o["paused"] = True
                return o, config.IMPRESSION_COST
        return None, 0.0
    return _mutate(_offers, _save_offers, _apply)


def offers_for_advertiser(email):
    return [o for o in _offers() if o.get("advertiser") == email]


def _attribution_funnel():
    """offer_id -> {"viewed","clicked","redeemed"} from the attribution log."""
    funnel = {}
    if config.ATTRIBUTION_FILE.exists():
        try:
            for line in config.ATTRIBUTION_FILE.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                a = json.loads(line)
                oid = a.get("offer_id")
                act = a.get("action")
                if oid and act in ("viewed", "clicked", "redeemed"):
                    funnel.setdefault(oid, {"viewed": 0, "clicked": 0, "redeemed": 0})
                    funnel[oid][act] += 1
        except Exception:
            pass
    return funnel


def offer_stats_for(email):
    funnel = _attribution_funnel()
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
        "funnel": funnel.get(o["id"], {"viewed": 0, "clicked": 0, "redeemed": 0}),
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
