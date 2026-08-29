#!/usr/bin/env python3
"""Test OAuth: CSRF state generation/verification, signed session cookies, and
the auth routes (with a mocked exchange function)."""
import json
import os
import sys
import tempfile

import httpx

# temp state files before importing config
td = tempfile.mkdtemp()
os.environ["ADGATE_USERS_FILE"] = os.path.join(td, "users.json")
os.environ["ADGATE_ADVERTISERS_FILE"] = os.path.join(td, "advertisers.json")
os.environ["ADGATE_PAYMENTS_LEDGER"] = os.path.join(td, "payments.jsonl")
os.environ["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
os.environ["ADGATE_ADS_FILE"] = "/dev/null"
os.environ["ADGATE_MAGIC_SECRET"] = "test-oauth-secret"
os.environ["ADGATE_PUBLIC_HOST"] = "http://guac.local"
# configure providers so the routes are active
os.environ["ADGATE_GITHUB_CLIENT_ID"] = "gh_test"
os.environ["ADGATE_GITHUB_CLIENT_SECRET"] = "gh_secret"
os.environ["ADGATE_GOOGLE_CLIENT_ID"] = "go_test"
os.environ["ADGATE_GOOGLE_CLIENT_SECRET"] = "go_secret"

sys.path.insert(0, "/opt/data/guac")
import oauth
import portal

from fastapi.testclient import TestClient
import gateway


def main():
    # 1) providers_configured
    assert set(oauth.providers_configured()) == {"github", "google"}, oauth.providers_configured()
    print("PASS  providers_configured -> github + google")

    # 2) state gen/verify
    s = oauth.new_state("user", "github")
    assert oauth.verify_state(s, "user", "github")
    assert not oauth.verify_state(s, "user", "google")  # wrong provider
    assert not oauth.verify_state(s, "advertiser", "github")  # wrong role
    print("PASS  state binding to role+provider (CSRF)")

    # 3) session cookie sign/verify
    c = oauth.make_session_cookie("advertiser", "a@b.com")
    role, email = oauth.verify_session_cookie(c)
    assert (role, email) == ("advertiser", "a@b.com")
    # tamper -> invalid
    assert oauth.verify_session_cookie(c[:-1] + ("0" if c[-1] != "0" else "1")) == (None, None)
    print("PASS  signed session cookie + tamper rejection")

    # 4) auth_start redirects to provider with a state cookie
    c = TestClient(gateway.app, follow_redirects=False)
    r = c.get("/auth/start/github?role=user")
    assert r.status_code == 302, r.status_code
    assert "github.com/login/oauth/authorize" in r.headers["location"]
    assert "oauth_state" in r.cookies
    print("PASS  /auth/start/github redirects with state cookie")

    # 5) callback with a valid (unsigned-but-verifiable) flow — mock exchange.
    # Simulate: start sets state cookie; we craft a callback with that state.
    # We monkeypatch oauth.exchange to return a fixed identity.
    original = oauth.exchange
    async def fake_exchange(provider, code):
        return {"email": "dev@github.com", "name": "Dev"}
    oauth.exchange = fake_exchange
    try:
        # Re-issue a start to get the state cookie value
        r = c.get("/auth/start/google?role=advertiser")
        state = r.cookies.get("oauth_state")
        assert state, "state cookie missing"
        # craft callback with the same state (TestClient keeps cookies)
        cb = c.get("/auth/callback?code=abc123")
        assert cb.status_code == 302, cb.status_code
        assert cb.headers["location"] == "/portal/advertiser/dash"
        assert "guac_session" in c.cookies
        # advertiser account was created
        assert portal.get_advertiser("dev@github.com") is not None
        print("PASS  OAuth callback mints session + creates account")
    finally:
        oauth.exchange = original

    # 6) role dashboard authorized by session cookie
    r = c.get("/portal/advertiser/dash")
    assert r.status_code == 200, r.status_code
    assert "Ad manager" in r.text
    print("PASS  session-authed advertiser dashboard renders")

    # 7) logout clears session
    r = c.post("/portal/logout")
    assert r.status_code == 302
    assert "guac_session" not in c.cookies  # deleted from the jar
    r = c.get("/portal/advertiser/dash")
    assert r.status_code == 302, r.status_code  # redirected to /portal
    print("PASS  logout clears session; dash requires auth")

    print("\nOAUTH TESTS PASSED")


if __name__ == "__main__":
    main()
