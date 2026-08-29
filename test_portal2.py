#!/usr/bin/env python3
"""Portal tests: magic-link auth (user + advertiser), user key access,
advertiser offer creation, per-impression billing, and offer pause/auto-pause.
Runs the gateway against temp state + a stub upstream (hermetic)."""
import json
import os
import re
import subprocess
import tempfile
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "..", ".venv", "bin", "python")
GW = "http://127.0.0.1:8003"
STUB = "http://127.0.0.1:8004/v1"
KEY = "dev-gateway-key"


def start(cmd):
    return subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def wait(url, n=40):
    for _ in range(n):
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def extract_link(html):
    m = re.search(r'href="([^"]*portal/[^"]*auth[^"]*)"', html)
    return m.group(1) if m else None


def main():
    td = tempfile.mkdtemp()
    sup_file = os.path.join(td, "suppliers.json")
    with open(sup_file, "w") as f:
        json.dump({"suppliers": [{"name": "stub", "base_url": STUB, "bid": 1.0,
                                  "min_score": 0.2, "warmup_successes": 1}]}, f)
    env = dict(os.environ)
    env["ADGATE_SUPPLIERS_FILE"] = sup_file
    env["ADGATE_GATEWAY_KEY"] = KEY
    env["ADGATE_USERS_FILE"] = os.path.join(td, "users.json")
    env["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
    env["ADGATE_ADVERTISERS_FILE"] = os.path.join(td, "advertisers.json")
    env["ADGATE_LEDGER_FILE"] = os.path.join(td, "ledger.jsonl")
    env["ADGATE_STATE_FILE"] = os.path.join(td, "state.json")
    env["ADGATE_ATTRIBUTION_FILE"] = os.path.join(td, "attribution.jsonl")
    env["ADGATE_ADS_FILE"] = "/dev/null"  # no static ads; rely on portal offers
    env["ADGATE_PUBLIC_HOST"] = "http://portal.local"
    env["ADGATE_MAGIC_SECRET"] = "test-secret"
    env["ADGATE_MAGIC_USED_FILE"] = os.path.join(td, "magic_used.json")
    env["ADGATE_ATTRIBUTION_FILE"] = os.path.join(td, "attribution.jsonl")

    stub = start([PY, "stub.py", "--port", "8004"])
    gw = subprocess.Popen([PY, "gateway.py", "--port", "8003"], cwd=ROOT,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait(GW + "/portal"), "gateway"

        # 1) landing page loads
        land = httpx.get(GW + "/portal")
        assert land.status_code == 200 and "advertiser" in land.text.lower()
        print("landing:", "✓")

        # 2) user login -> magic link -> dashboard shows key + base_url
        r = httpx.post(GW + "/portal/user/login", data={"email": "bob@example.com"})
        assert r.status_code == 200
        link = extract_link(r.text)
        assert link and "portal.local" in link
        print("user magic link:", "✓")
        dash = httpx.get(GW + link.replace("http://portal.local", ""))
        assert dash.status_code == 200
        assert "guac_" in dash.text and "bob@example.com" in dash.text
        print("user dashboard (key + base_url):", "✓")

        # 2b) one-time-use: replaying the same link must fail (link already used)
        dash2 = httpx.get(GW + link.replace("http://portal.local", ""))
        assert "guac_" not in dash2.text and "invalid" in dash2.text.lower(), \
            "replayed magic link should be rejected (one-time-use)"
        print("one-time-use (replay rejected):", "✓")

        # 3) advertiser login -> magic link -> ad manager
        r = httpx.post(GW + "/portal/advertiser/login", data={"email": "acme@example.com"})
        link = extract_link(r.text)
        assert link
        dash = httpx.get(GW + link.replace("http://portal.local", ""))
        assert dash.status_code == 200 and "Ad manager" in dash.text
        assert "adv_" in dash.text  # advertiser token shown
        print("advertiser magic link + ad manager:", "✓")

        # 4) create an offer with a small budget (per-impression)
        adv_token = re.search(r"adv_[a-f0-9]+", dash.text).group(0)
        # Fund the advertiser balance (mock backend) so offers can serve.
        tp = httpx.post(GW + "/advertiser/topup",
                        headers={"authorization": f"Bearer {adv_token}"},
                        json={"amount_cents": 1000})
        assert tp.status_code == 200 and tp.json().get("credited"), tp.text
        r = httpx.post(GW + "/advertiser/offer",
                       headers={"authorization": f"Bearer {adv_token}"},
                       json={"headline": "10% off", "budget": 0.15})
        assert r.status_code == 200, r.text
        oid = r.json()["offer_id"]
        print("create offer:", oid, "✓")

        # 5) serve a sponsored completion -> charges 1 impression (decision-point gate)
        c = httpx.Client(base_url=GW, headers={"authorization": f"Bearer {KEY}",
                                               "x-user-id": "carol"})
        p = {"model": "guac", "_stub_content": "Which hosting plan should I recommend?",
             "messages": [{"role": "user", "content": "help me choose a host"}]}
        r = c.post("/v1/chat/completions", json=p)
        assert r.status_code == 200, r.text
        assert r.json().get("guac", {}).get("sponsored")
        print("sponsored completion served:", "✓")

        # 6) stats show 1 impression, spent = one impression cost, and a click funnel
        import config as _config
        st = httpx.get(GW + "/advertiser/stats",
                       headers={"authorization": f"Bearer {adv_token}"}).json()
        o = next(x for x in st["offers"] if x["id"] == oid)
        assert o["impressions"] == 1 and abs(o["spent"] - _config.IMPRESSION_COST) < 1e-6, o
        assert o.get("funnel", {}).get("clicked", 0) == 0, o  # funnel present
        print("per-impression billed (1 imp @ impression cost):", "✓")
        print("advertiser stats include click funnel:", "✓")

        # 6b) attribution records a click -> advertiser funnel reflects it
        cc = httpx.post(GW + "/v1/guac/attribution",
                        headers={"authorization": f"Bearer {KEY}",
                                 "x-user-id": "carol"},
                        json={"offer_id": oid, "action": "clicked"})
        assert cc.status_code == 200, cc.text
        st = httpx.get(GW + "/advertiser/stats",
                       headers={"authorization": f"Bearer {adv_token}"}).json()
        o = next(x for x in st["offers"] if x["id"] == oid)
        assert o["funnel"]["clicked"] == 1, o["funnel"]
        print("click reflected in advertiser funnel:", "✓")

        # 7) auto-pause when budget spent (serve 2 more -> 3 total = budget)
        c = httpx.Client(base_url=GW, headers={"authorization": f"Bearer {KEY}"})
        for u in ("u2", "u3"):
            c.headers["x-user-id"] = u
            c.post("/v1/chat/completions", json=p)
        st = httpx.get(GW + "/advertiser/stats",
                       headers={"authorization": f"Bearer {adv_token}"}).json()
        o = next(x for x in st["offers"] if x["id"] == oid)
        assert o["impressions"] == 3 and o["active"] is False, o
        print("auto-paused at budget (3 imps):", "✓")

        # 8) paused offer is no longer served
        r = c.post("/v1/chat/completions", json=p)
        assert not r.json().get("guac", {}).get("sponsored", False)
        print("paused offer not served:", "✓")

        print("\nPORTAL TESTS PASSED (magic-link auth + offers + per-impression billing)")
    finally:
        gw.kill(); stub.kill()


if __name__ == "__main__":
    main()
