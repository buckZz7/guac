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

        import config
        cfg = config

        # 3b) FLAT-DISCOUNT billing: the bill is market cost * (1 - discount),
        # debited straight from the balance. No credits, no rebate mechanics.
        with open(os.path.join(td, "payments.jsonl")) as f:
            pay_rows = [json.loads(l) for l in f if l.strip()]
        debits = [x for x in pay_rows if x.get("source") == "inference"]
        assert debits, "request must debit the user balance"
        # stub reports 1 prompt + 2 completion tokens; no supplier pricing for
        # 'stub', so cost = tokens * passthrough rate * (1 - discount)
        exp = 3 * cfg.PASSTHROUGH_WHOLESALE_PER_M / 1e6 * (1 - cfg.DISCOUNT_RATE)
        assert abs(-debits[0]["delta"] - exp) < 1e-9, (debits[0]["delta"], exp)
        # ledger row records the discounted bill
        with open(os.path.join(ROOT, "ledger.jsonl")) as f:
            led = [json.loads(l) for l in f if l.strip()]
        bill = led[-1]["bill"]
        assert abs(bill["cost"] - exp) < 1e-9, bill
        assert bill["discount_rate"] == cfg.DISCOUNT_RATE
        # no credit/rebate rows exist — the discount lives in the rate only
        assert not any(x.get("source") == "sponsor_pass_through" for x in pay_rows)
        print(f"PASS  request billed at flat discounted rate (${exp:.8f}), no credit mechanics")

        # 3c) UNSPONSORED request is ALSO discounted — the rate is always on
        r = httpx.post(f"{GATEWAY}/v1/chat/completions",
                       headers={"authorization": f"Bearer {ukey}"},
                       json={"model": "stub", "_stub_finish": "stop",
                             "_stub_content": "no ad turn",
                             "messages": [{"role": "user", "content": "hello again"}]})
        assert r.status_code == 200
        with open(os.path.join(td, "payments.jsonl")) as f:
            pay_rows = [json.loads(l) for l in f if l.strip()]
        debits = [x for x in pay_rows if x.get("source") == "inference"]
        assert len(debits) == 2
        # "hello again" (2 prompt) + "(stub) hello again" (3 completion) = 5 tokens
        exp2 = 5 * cfg.PASSTHROUGH_WHOLESALE_PER_M / 1e6 * (1 - cfg.DISCOUNT_RATE)
        assert abs(-debits[1]["delta"] - exp2) < 1e-9, debits[1]["delta"]
        print("PASS  unsponsored request billed at the same discounted rate")

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
