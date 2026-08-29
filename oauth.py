"""guac OAuth — GitHub + Google sign-in for the portal.

Production auth path. When a provider's client id+secret are configured, the
portal shows that provider's sign-in button. On success we mint a signed session
cookie (same secret family as magic links) that identifies the logged-in role +
identity, so the stateless gateway can authorize the portal dashboards.

Flow:
  1. /auth/<provider>?role=user|advertiser  -> builds provider auth URL with a
     random `state` (CSRF), stores state in the session cookie, redirects out.
  2. Provider redirects back to /auth/callback?code=..&state=..  -> verifies
     state, exchanges code for an access token, fetches identity (email), and
     sets the signed session cookie, then redirects to the role dashboard.

Uses only httpx (already a dependency) — no extra packages.
"""
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx

import config

# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

def _base_url() -> str:
    return (config.OAUTH_BASE or config.PUBLIC_HOST or "http://127.0.0.1:8000").rstrip("/")


def providers_configured() -> list:
    """Names of configured OAuth providers, in display order."""
    out = []
    if config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET:
        out.append("github")
    if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
        out.append("google")
    return out


def auth_url(provider: str, role: str, state: str) -> str:
    """The URL to send the user to for OAuth authorization."""
    callback = f"{_base_url()}/auth/callback"
    if provider == "github":
        params = {
            "client_id": config.GITHUB_CLIENT_ID,
            "redirect_uri": callback,
            "scope": "user:email",
            "state": state,
            "prompt": "select_account",
        }
        return "https://github.com/login/oauth/authorize?" + urlencode(params)
    # google
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": callback,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


async def exchange(provider: str, code: str) -> dict:
    """Exchange an auth code for identity. Returns {email, name} or raises.
    (GitHub returns an email via the /user/emails endpoint; Google via the
    tokeninfo endpoint.)"""
    callback = f"{_base_url()}/auth/callback"
    async with httpx.AsyncClient(timeout=20) as client:
        if provider == "github":
            r = await client.post("https://github.com/login/oauth/access_token", data={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": callback,
            }, headers={"Accept": "application/json"})
            r.raise_for_status()
            tok = r.json().get("access_token")
            if not tok:
                raise RuntimeError("github: no access_token in response")
            u = await client.get("https://api.github.com/user",
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Accept": "application/vnd.github+json"})
            u.raise_for_status()
            info = u.json()
            email = info.get("email")
            if not email:
                # public email may be null; fetch primary email from /user/emails
                e = await client.get("https://api.github.com/user/emails",
                                     headers={"Authorization": f"Bearer {tok}",
                                              "Accept": "application/vnd.github+json"})
                e.raise_for_status()
                for row in e.json():
                    if row.get("primary"):
                        email = row.get("email")
                        break
            return {"email": (email or "").lower(), "name": info.get("name") or ""}
        # google
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "code": code,
            "redirect_uri": callback,
            "grant_type": "authorization_code",
        })
        r.raise_for_status()
        tok = r.json().get("access_token")
        if not tok:
            raise RuntimeError("google: no access_token in response")
        u = await client.get("https://openidconnect.googleapis.com/v1/userinfo",
                             headers={"Authorization": f"Bearer {tok}"})
        u.raise_for_status()
        info = u.json()
        return {"email": (info.get("email") or "").lower(),
                "name": info.get("name") or ""}


# ---------------------------------------------------------------------------
# OAuth state (CSRF) + signed session cookie
# ---------------------------------------------------------------------------

def _sign_state(role, provider, rand):
    # Signed binding of role+provider+nonce so state can't be forged or swapped.
    return hmac.new(config.MAGIC_SECRET.encode(),
                    f"{role}|{provider}|{rand}".encode(),
                    hashlib.sha256).hexdigest()


def sign(data: str) -> str:
    """Generic HMAC signature (used for session cookies)."""
    return hmac.new(config.MAGIC_SECRET.encode(), data.encode(),
                    hashlib.sha256).hexdigest()


def new_state(role: str, provider: str) -> str:
    """A signed random state for CSRF: role|provider|nonce|sig. The signature
    binds it to this role+provider so it can't be forged or replayed across
    roles/providers."""
    rand = secrets.token_urlsafe(16)
    sig = _sign_state(role, provider, rand)
    return f"{role}|{provider}|{rand}|{sig}"


def verify_state(state: str, role: str, provider: str) -> bool:
    """Verify a state token: correct structure, matches role+provider, and the
    signature validates (proves we minted it)."""
    try:
        s_role, s_prov, rand, sig = state.split("|")
    except ValueError:
        return False
    if s_role != role or s_prov != provider:
        return False
    return hmac.compare_digest(sig, _sign_state(role, provider, rand))


def make_session_cookie(role: str, email: str) -> str:
    """Signed session cookie value: role|email|exp|sig."""
    exp = int(time.time()) + config.SESSION_TTL_S
    payload = f"{role}|{email}|{exp}"
    return f"{payload}|{sign(payload)}"


def verify_session_cookie(value: str):
    """Return (role, email) if the session cookie is valid + unexpired, else
    (None, None)."""
    try:
        role, email, exp, sig = value.split("|")
        if int(exp) <= int(time.time()):
            return None, None
        if not hmac.compare_digest(sign(f"{role}|{email}|{exp}"), sig):
            return None, None
        return role, email
    except (ValueError, TypeError):
        return None, None
