#!/usr/bin/env python3
"""Test the guac portal: user sign-up issues an API key, that key authenticates
inference, advertiser offer submission works, and stats return. Uses the stub
upstream + temp storage files."""
import json
import os
import subprocess
import tempfile
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "..", ".venv", "bin", "python")
GW = "http://127.0.0.1:9100"
STUB = "http://127.0.0.1:9101"


def wait(url, n=40):
    for _ in range(n):
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def main():
    td = tempfile.mkdtemp()
    sup = {"suppliers": [
        {"name": "primary", "base_url": STUB + "/v1", "bid": 1.0,
         "min_score": 0.4, "warmup_successes": 1},
    ]}
    sup_file = os.path.join(td, "suppliers.json")
    with open(sup_file, "w") as f:
        json.dump(sup, f)

    stub = subprocess.Popen([PY, "stub.py", "--port", "9101"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = dict(os.environ)
    env["ADGATE_SUPPLIERS_FILE"] = sup_file
    env["ADGATE_USERS_FILE"] = os.path.join(td, "users.json")
    env["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
    env["ADGATE_ADVERTISERS_FILE"] = os.path.join(td, "advertisers.json")
    env["ADGATE_LEDGER_FILE"] = os.path.join(td, "ledger.jsonl")
    env["ADGATE_ATTRIBUTION_FILE"] = os.path.join(td, "attribution.jsonl")
    env["ADGATE_STATE_FILE"] = os.path.join(td, "state.json")
    env["ADGATE_GATEWAY_KEY"] = "master-key"
    env["ADGATE_PUBLIC_HOST"] = GW
    env["ADGATE_MAGIC_SECRET"] = "test-secret"
    # Make the test process itself use the same temp paths as the gateway.
    os.environ["ADGATE_USERS_FILE"] = env["ADGATE_USERS_FILE"]
    os.environ["ADGATE_OFFERS_FILE"] = env["ADGATE_OFFERS_FILE"]
    os.environ["ADGATE_ADVERTISERS_FILE"] = env["ADGATE_ADVERTISERS_FILE"]
    gw = subprocess.Popen([PY, "gateway.py", "--port", "9100"], cwd=ROOT,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait(STUB + "/health"), "stub"
        assert wait(GW + "/health"), "gateway"

        c = httpx.Client(base_url=GW)

        # 1) sign up a user
        r = c.post("/signup", json={"email": "alice@example.com", "ads_per_day": 1})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["api_key"].startswith("guac_"), d
        assert d["base_url"].endswith("/v1"), d
        alice_key = d["api_key"]
        print("signup ok:", alice_key[:10] + "...", "| base_url:", d["base_url"])

        # 2) duplicate email rejected
        r2 = c.post("/signup", json={"email": "alice@example.com"})
        assert r2.status_code == 409, r2.status_code
        print("dup email rejected: ✓")

        # 3) user key authenticates inference (paid-with-discount: top up first)
        auth = {"authorization": f"Bearer {alice_key}"}
        tp = c.post("/user/topup", json={"amount_cents": 500}, headers=auth)
        assert tp.status_code == 200 and tp.json()["credited"] is True, tp.text
        # empty-balance gate: a fresh unfunded user gets 402, not inference
        import portal as _portal
        u2, _ = _portal.create_user("bob@example.com")
        r402 = c.post("/v1/chat/completions", json={
            "model": "stub", "messages": [{"role": "user", "content": "hi"}]},
            headers={"authorization": f"Bearer {u2['api_key']}"})
        assert r402.status_code == 402, (r402.status_code, r402.text)
        print("unfunded user gets 402 insufficient_balance: ✓")
        rr = c.post("/v1/chat/completions", json={
            "model": "stub",
            "messages": [{"role": "user", "content": "hi"}],
        }, headers=auth)
        assert rr.status_code == 200, rr.text
        print("user key authenticates inference: ✓")

        # 4) bad key rejected
        bad = c.post("/v1/chat/completions", json={"model": "stub", "messages": [
            {"role": "user", "content": "hi"}]},
            headers={"authorization": "Bearer guac_bogus"})
        assert bad.status_code == 401, bad.status_code
        print("bad key rejected: ✓")

        # 5) advertiser submits an offer (via their own token)
        #    get a token through the magic-link flow
        login = c.post("/portal/advertiser/login", data={"email": "acme@example.com"})
        assert login.status_code == 200
        import re
        m = re.search(r'href="([^"]*portal/advertiser/auth[^"]*)"', login.text)
        assert m, "no magic link"
        link = m.group(1)
        # The link host is PUBLIC_HOST (= the gateway). Use it as-is.
        dash = c.get(link)
        assert dash.status_code == 200 and "Ad manager" in dash.text
        adv_token = re.search(r"adv_[a-f0-9]+", dash.text).group(0)
        print("advertiser token via magic link:", adv_token[:8] + "...")

        off = c.post("/advertiser/offer", json={
            "headline": "50% off", "body": "details", "claim": "code",
            "budget": 100.0, "offer_type": "discount"},
            headers={"authorization": f"Bearer {adv_token}"})
        assert off.status_code == 200, off.text
        oid = off.json()["offer_id"]
        print("advertiser offer created:", oid)

        # 6) offer requires auth
        noauth = c.post("/advertiser/offer", json={"headline": "Y", "budget": 1})
        assert noauth.status_code == 401, noauth.status_code
        print("offer requires auth: ✓")

        # 7) advertiser stats (scoped to their own offers)
        st = c.get("/advertiser/stats", headers={"authorization": f"Bearer {adv_token}"})
        assert st.status_code == 200
        offers = st.json()["offers"]
        assert len(offers) == 1 and offers[0]["id"] == oid
        assert offers[0]["advertiser"] == "acme@example.com"
        print("advertiser stats:", "✓")

        # 8) another advertiser sees no offers (isolation)
        c.post("/portal/advertiser/login", data={"email": "other@example.com"})
        login2 = c.post("/portal/advertiser/login", data={"email": "other@example.com"})
        m2 = re.search(r'href="([^"]*portal/advertiser/auth[^"]*)"', login2.text)
        link2 = m2.group(1)
        dash2 = c.get(link2)
        adv2_token = re.search(r"adv_[a-f0-9]+", dash2.text).group(0)
        st2 = c.get("/advertiser/stats",
                    headers={"authorization": f"Bearer {adv2_token}"}).json()
        assert st2["offers"] == []
        print("advertiser isolation:", "✓")

        print("\nPORTAL TESTS PASSED (signup + key auth + advertiser flow)")
    finally:
        gw.kill(); stub.kill()


if __name__ == "__main__":
    main()
