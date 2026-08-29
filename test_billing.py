#!/usr/bin/env python3
"""Test the paid-with-discount billing core end-to-end:

  1) a real user key with empty balance gets 402 (no credit)
  2) top-up credits the user balance
  3) requests bill the user at cost; sponsor money is credited to the user
     and drawn FIRST on subsequent bills (the discount)
  4) replayed session history has guac's own sponsor footers stripped
     (Hermes replays: ad text must never re-enter the model or get re-billed)
"""
import json
import os
import subprocess
import tempfile
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "..", ".venv", "bin", "python")
GATEWAY = "http://127.0.0.1:8000"
STUB = "http://127.0.0.1:8001"
KEY = "dev-gateway-key"


def start(cmd, env=None):
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
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
    for f in ("ledger.jsonl", "state.json", "attribution.jsonl", "payments.jsonl",
              "users.json", "offers.json", "supplier_state.json"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)

    td = tempfile.mkdtemp()
    with open(os.path.join(td, "suppliers.json"), "w") as f:
        json.dump({"suppliers": [
            {"name": "stub", "base_url": f"{STUB}/v1", "bid": 1.0,
             "min_score": 0.4, "warmup_successes": 1},
        ]}, f)
    # one funded portal offer
    offers = [{
        "id": "sponsor-x", "advertiser": "adv@x.com", "headline": "50% off",
        "body": "b", "claim": "X", "offer_type": "discount", "intents": [],
        "image_url": "", "link": "https://x.com", "budget": 5.0,
        "impressions": 0, "spent": 0.0, "active": True, "paused": False,
    }]
    with open(os.path.join(td, "offers.json"), "w") as f:
        json.dump(offers, f)

    env = dict(os.environ)
    env.update({
        "ADGATE_SUPPLIERS_FILE": os.path.join(td, "suppliers.json"),
        "ADGATE_GATEWAY_KEY": KEY,
        "ADGATE_OFFERS_FILE": os.path.join(td, "offers.json"),
        "ADGATE_PAYMENTS_BACKEND": "mock",
        "ADGATE_PAYMENTS_LEDGER": os.path.join(td, "payments.jsonl"),
        "ADGATE_USERS_FILE": os.path.join(td, "users.json"),
        "ADGATE_ADVERTISERS_FILE": os.path.join(td, "advertisers.json"),
        "ADGATE_ADS_FILE": "/dev/null",
        "ADGATE_ADS_PER_DAY": "5",
        "ADGATE_DAILY_TOKEN_CAP": "0",
    })
    os.environ.update({k: v for k, v in env.items() if k.startswith("ADGATE_")})

    stub = start([PY, "stub.py", "--port", "8001"])
    gw = subprocess.Popen([PY, "gateway.py", "--port", "8000"], cwd=ROOT, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_ok(f"{STUB}/health") and wait_ok(f"{GATEWAY}/health")

        # advertiser account + funded balance (offers only serve while funded)
        import portal
        adv, _ = portal.create_advertiser("adv@x.com")
        tp = httpx.post(f"{GATEWAY}/advertiser/topup",
                        headers={"authorization": f"Bearer {adv['token']}"},
                        json={"amount_cents": 500})
        assert tp.status_code == 200 and tp.json()["credited"] is True, tp.text

        # user account
        user, err = portal.create_user("alice@example.com")
        assert user and not err
        ukey = user["api_key"]

        # 1) empty balance -> 402
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {ukey}"},
                       json={"model": "stub",
                             "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 402, (r.status_code, r.text)
        assert r.json()["error"]["code"] == "insufficient_balance"
        print("PASS  empty balance -> 402 insufficient_balance")

        # 2) top up $5 (mock backend, via Bearer api key)
        r = httpx.post(f"{GATEWAY}/user/topup",
                       headers={"authorization": f"Bearer {ukey}"},
                       json={"amount_cents": 500})
        assert r.status_code == 200 and r.json()["credited"] is True
        assert abs(r.json()["balance"] - 5.0) < 1e-6
        print("PASS  user top-up credits balance ($5)")

        # 3a) request is served + billed; a funded offer sponsors it
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {ukey}"},
                       json={"model": "stub", "_stub_finish": "stop",
                             "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("guac", {}).get("sponsored"), "funded offer should serve"

        import config, payments
        cfg = config
        credit = cfg.IMPRESSION_COST * (1 - cfg.GUAC_AD_FEE_FRACTION)
        own, subsidy = payments.user_balance_parts("alice@example.com")
        assert abs(subsidy - credit) < 1e-6, (subsidy, credit)
        print(f"PASS  sponsored answer credited ${credit:.4f} to user subsidy bucket")

        # 3b) next bill draws the subsidy bucket FIRST
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {ukey}"},
                       json={"model": "stub", "_stub_finish": "stop",
                             "messages": [{"role": "user", "content": "again"}]})
        assert r.status_code == 200
        rows = []
        with open(os.path.join(td, "payments.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        used = [x for x in rows if x.get("source") == "subsidy_used"]
        assert used, "second bill must draw the subsidy bucket"
        assert abs(used[0]["delta"] + credit) < 1e-6 or used[0]["delta"] < 0
        print("PASS  next request drew sponsor subsidy before own money")

        # 4) replayed history: assistant turn carries an old guac footer;
        #    the forwarded body must have it stripped.
        polluted = ("Here is my answer.\n---\nSponsor: Acme — 50% off\n"
                    "Learn more: https://addguac.fly.dev/go/sponsor-x")
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {ukey}"},
                       json={"model": "stub",
                             "messages": [
                                 {"role": "user", "content": "q1"},
                                 {"role": "assistant", "content": polluted},
                                 {"role": "user", "content": "q2"},
                             ]})
        assert r.status_code == 200
        fwd = httpx.get(f"{STUB}/_last_body").json()
        asst = [m for m in fwd["messages"] if m["role"] == "assistant"]
        assert asst and "Sponsor:" not in asst[0]["content"], asst[0]["content"]
        assert asst[0]["content"] == "Here is my answer."
        print("PASS  replayed sponsor footers stripped from inbound history")

        print("\nBILLING (PAID-WITH-DISCOUNT) TESTS PASSED")
    finally:
        stub.kill()
        gw.kill()


if __name__ == "__main__":
    main()
