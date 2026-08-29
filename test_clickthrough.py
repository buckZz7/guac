#!/usr/bin/env python3
"""Test the clickthrough redirect funnel: /go/<offer_id> logs a real click and
302s to the offer's link (with tracking params), the footer link routes through
/go, and the click lands in the attribution log.
"""
import json, os, subprocess, sys, tempfile, time
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
    for f in ("ledger.jsonl", "state.json", "attribution.jsonl"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)

    td = tempfile.mkdtemp()
    sup = {"suppliers": [
        {"name": "stub", "base_url": "http://127.0.0.1:8001/v1", "bid": 1.0,
         "min_score": 0.4, "warmup_successes": 1},
    ]}
    sup_file = os.path.join(td, "suppliers.json")
    with open(sup_file, "w") as f:
        json.dump(sup, f)

    stub = start([PY, "stub.py", "--port", "8001"])
    env = dict(os.environ)
    env["ADGATE_SUPPLIERS_FILE"] = sup_file
    env["ADGATE_GATEWAY_KEY"] = KEY
    env["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")  # -> ads.json fallback
    # This test exercises the static demo inventory; production keeps it gated.
    env["ADGATE_ALLOW_DEMO_ADS"] = "1"
    gw = subprocess.Popen([PY, "gateway.py", "--port", "8000"], cwd=ROOT,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_ok("http://127.0.0.1:8001/health"), "stub didn't start"
        assert wait_ok(f"{GATEWAY}/health"), "gateway didn't start"

        c = httpx.Client(base_url=GATEWAY,
                         headers={"authorization": f"Bearer {KEY}",
                                  "x-user-id": "alice"})

        # 1) /go/<id> redirects (302) to the offer link with tracking params
        r = httpx.get(f"{GATEWAY}/go/sponsor-nordvpn", follow_redirects=False)
        assert r.status_code == 302, r.status_code
        loc = r.headers.get("location", "")
        assert loc.startswith("https://nordvpn.com"), loc
        assert "ref=guac" in loc and "utm_source=guac" in loc and "utm_campaign=sponsor-nordvpn" in loc
        print("PASS  /go/<id> 302 -> offer link + tracking params")

        # 2) unknown offer -> 404
        r = httpx.get(f"{GATEWAY}/go/nope", follow_redirects=False)
        assert r.status_code == 404, r.status_code
        print("PASS  /go/<unknown> -> 404")

        # 3) the click was logged in the attribution funnel
        with open(os.path.join(ROOT, "attribution.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        assert len(rows) == 1 and rows[0]["offer_id"] == "sponsor-nordvpn"
        assert rows[0]["action"] == "clicked" and rows[0]["source"] == "redirect"
        print("PASS  click recorded in attribution log")

        # 4) a sponsored response's footer routes the link through /go/<id>
        r = c.post("/v1/chat/completions", json={
            "model": "stub",
            "messages": [{"role": "user", "content": "pick a vpn"}],
            "_stub_content": "Which VPN should I get?",
            "_stub_finish": "stop",
        })
        assert r.status_code == 200, r.text
        content = r.json()["choices"][0]["message"]["content"]
        # The offer rotates deterministically; just assert the footer link routes
        # through /go/<id> for whichever offer was picked.
        assert "/go/sponsor-" in content, f"footer link not routed through /go: {content!r}"
        print("PASS  footer link routes through /go/<id> (click trackable)")

        print("\nCLICKTHROUGH FUNNEL TESTS PASSED")
    finally:
        stub.kill()
        gw.kill()


if __name__ == "__main__":
    main()
