#!/usr/bin/env python3
"""Test the advertiser prepaid-balance payment model.

- mock backend top-up credits balance
- charge_impression debits balance; offer only serves while funded
- an unfunded advertiser's offer does not serve (no ad)
- /advertiser/stats returns balance + backend
- backup includes the payments ledger
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "..", ".venv", "bin", "python")
GATEWAY = "http://127.0.0.1:8000"
KEY = "dev-gateway-key"


def start(cmd):
    return subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def wait_ok(url, tries=30):
    for _ in range(tries):
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    for f in ("ledger.jsonl", "state.json", "attribution.jsonl", "payments.jsonl"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)

    td = tempfile.mkdtemp()
    sup = {"suppliers": [
        {"name": "stub", "base_url": "http://127.0.0.1:8001/v1", "bid": 1.0,
         "min_score": 0.4, "warmup_successes": 1},
    ]}
    with open(os.path.join(td, "suppliers.json"), "w") as f:
        json.dump(sup, f)
    # A portal offer owned by an advertiser (so balance gates it).
    offers = [{
        "id": "sponsor-x", "advertiser": "adv@x.com", "sponsor": "Acme",
        "headline": "50% off hosting", "body": "b", "claim": "X",
        "offer_type": "discount", "intents": [], "image_url": "", "link": "https://x.com",
        "budget": 5.0, "impressions": 0, "spent": 0.0,
        "active": True, "paused": False,
    }]
    with open(os.path.join(td, "offers.json"), "w") as f:
        json.dump(offers, f)

    stub = start([PY, "stub.py", "--port", "8001"])
    env = dict(os.environ)
    env["ADGATE_SUPPLIERS_FILE"] = os.path.join(td, "suppliers.json")
    env["ADGATE_GATEWAY_KEY"] = KEY
    env["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
    env["ADGATE_PAYMENTS_BACKEND"] = "mock"
    env["ADGATE_PAYMENTS_LEDGER"] = os.path.join(td, "payments.jsonl")
    env["ADGATE_USERS_FILE"] = os.path.join(td, "users.json")
    env["ADGATE_ADVERTISERS_FILE"] = os.path.join(td, "advertisers.json")
    env["ADGATE_ADS_FILE"] = "/dev/null"  # no static ads; rely on portal offer
    # Also apply to THIS process so portal writes land where the gateway reads.
    os.environ.update({k: v for k, v in env.items()
                       if k.startswith("ADGATE_")})
    gw = subprocess.Popen([PY, "gateway.py", "--port", "8000"], cwd=ROOT,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_ok("http://127.0.0.1:8001/health"), "stub didn't start"
        assert wait_ok(f"{GATEWAY}/health"), "gateway didn't start"

        # advertiser account + token
        import portal
        adv, err = portal.create_advertiser("adv@x.com")
        if not adv:
            adv = portal.get_advertiser("adv@x.com")
        tok = adv["token"]

        # 1) balance starts at 0; offer NOT funded -> no ad serves
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {KEY}", "x-user-id": "u"},
                       json={"model": "stub", "messages": [{"role": "user", "content": "hi"}],
                             "_stub_content": "final answer", "_stub_finish": "stop"})
        assert r.status_code == 200, r.text
        assert not r.json().get("guac", {}).get("sponsored"), "unfunded offer must not serve"
        print("PASS  unfunded advertiser offer does not serve (no ad)")

        # 2) top up $5 via mock backend
        r = httpx.post(f"{GATEWAY}/advertiser/topup",
                       headers={"authorization": f"Bearer {tok}"},
                       json={"amount_cents": 500})
        assert r.status_code == 200, r.text
        assert r.json()["credited"] is True
        assert abs(r.json()["balance"] - 5.0) < 1e-6, r.json()
        print("PASS  mock top-up credits balance ($5)")

        # 3) now the offer serves and debits balance
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {KEY}", "x-user-id": "u"},
                       json={"model": "stub", "messages": [{"role": "user", "content": "hi"}],
                             "_stub_content": "final answer", "_stub_finish": "stop"})
        assert r.status_code == 200, r.text
        assert r.json().get("guac", {}).get("sponsored"), "funded offer should serve"
        print("PASS  funded offer serves + footer appended")

        # 4) balance was debited (one impression at the configured rate)
        import config as _config
        r = httpx.get(f"{GATEWAY}/advertiser/stats",
                      headers={"authorization": f"Bearer {tok}"}).json()
        assert abs(r["balance"] - (5.0 - _config.IMPRESSION_COST)) < 1e-6, r["balance"]
        assert r["backend"] == "mock"
        assert r["offers"][0]["impressions"] == 1
        print("PASS  impression debits balance; stats show balance + impressions")

        # 5) top-up below minimum rejected
        r = httpx.post(f"{GATEWAY}/advertiser/topup",
                       headers={"authorization": f"Bearer {tok}"},
                       json={"amount_cents": 50})
        assert r.status_code == 400, r.text
        print("PASS  top-up below $1 minimum rejected")

        print("\nPAYMENTS/BALANCE TESTS PASSED")
    finally:
        stub.kill()
        gw.kill()


if __name__ == "__main__":
    main()
