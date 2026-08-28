#!/usr/bin/env python3
"""End-to-end test: guac injects one sponsored offer per user per day,
meters tokens, and applies the discount; second request the same day is NOT
sponsored. Run with both stub and gateway live."""
import json
import subprocess
import sys
import time
import os

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "..", ".venv", "bin", "python")
GATEWAY = "http://127.0.0.1:8000"
KEY = "dev-gateway-key"

def start(cmd):
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    return p

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
    # clean state
    for f in ("state.json", "ledger.jsonl"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)

    stub = start([PY, "stub.py", "--port", "8001"])
    gw = start([PY, "gateway.py", "--port", "8000"])
    try:
        assert wait_ok("http://127.0.0.1:8001/health"), "stub didn't start"
        assert wait_ok(f"{GATEWAY}/health"), "gateway didn't start"

        client = httpx.Client(base_url=GATEWAY,
                              headers={"authorization": f"Bearer {KEY}",
                                       "x-user-id": "alice"})
        payload = {"model": "stub", "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Find me a cheap hosting plan"},
        ]}

        # 1st request today -> sponsored
        r1 = client.post("/v1/chat/completions", json=payload)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        sponsored = d1.get("guac", {}).get("sponsored", False)
        print("REQ1 sponsored:", sponsored)
        if not sponsored:
            print("  content:", d1["choices"][0]["message"]["content"])
        # 2nd request same day -> NOT sponsored
        r2 = client.post("/v1/chat/completions", json=payload)
        d2 = r2.json()
        sponsored2 = d2.get("guac", {}).get("sponsored", False)
        print("REQ2 sponsored:", sponsored2)
        assert sponsored and not sponsored2, "ad cadence wrong"

        # ledger got two rows, one sponsored with discount
        with open(os.path.join(ROOT, "ledger.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        print("LEDGER rows:", len(rows))
        assert len(rows) == 2
        assert rows[0]["sponsored"] is True and rows[0]["discount_rate"] == 0.20
        assert rows[1]["sponsored"] is False and rows[1]["discount_rate"] == 0.0
        assert rows[0]["prompt_tokens"] > 0

        print("\nALL TESTS PASSED")
        print("  - 1 ad injected on request 1, none on request 2 (1/day)")
        print("  - tokens metered, discount 20% applied on sponsored request")
        print("  - offer disclosed in response guac block")
    finally:
        stub.kill(); gw.kill()

if __name__ == "__main__":
    main()
