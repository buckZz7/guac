#!/usr/bin/env python3
"""End-to-end test for guac V1 decision-point sponsorship.

V1 shows a sponsorship footer ONLY when the agent's answer is a FINAL turn
(finish_reason == "stop") that HANDS OFF to the user AND an offer's intent tag
matches the decision text. No per-day frequency. The footer is appended BELOW
the answer, delimited by ---, so the model content above it is byte-identical.
"""
import json
import subprocess
import sys
import time
import os
import tempfile

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


def sse_footer_present(body: bytes) -> bool:
    """True if the stream carried a footer content-delta before [DONE]."""
    footer = False
    for line in body.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            evt = json.loads(payload)
        except Exception:
            continue
        c = (evt.get("choices") or [{}])[0].get("delta", {}).get("content", "")
        if "Sponsor:" in c:
            footer = True
    return footer


def main():
    for f in ("ledger.jsonl", "state.json"):
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
    # Hermetic offers (hosting + vector) so this test doesn't depend on ads.json.
    offers = [
        {"id": "sponsor-host", "sponsor": "Acme Cloud Hosting",
         "headline": "50% off hosting", "body": "b", "claim": "AGENT50",
         "intents": ["hosting", "host", "deploy"], "link": "https://acme.example/agent",
         "image_url": "https://cdn.example.com/acme-hosting.png",
         "active": True, "paused": False, "budget": 5.0, "spent": 0.0},
        {"id": "sponsor-db", "sponsor": "Nimbus Data",
         "headline": "vector database trial", "body": "b", "claim": "",
         "intents": ["vector", "database", "db"], "link": "https://nimbus.example",
         "active": True, "paused": False, "budget": 5.0, "spent": 0.0},
    ]
    offer_file = os.path.join(td, "offers.json")
    with open(offer_file, "w") as f:
        json.dump(offers, f)

    stub = start([PY, "stub.py", "--port", "8001"])
    env = dict(os.environ)
    env["ADGATE_SUPPLIERS_FILE"] = sup_file
    env["ADGATE_GATEWAY_KEY"] = KEY
    # Hermetic: hermetic offers file (hosting + vector), independent of ads.json.
    env["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
    gw = subprocess.Popen([PY, "gateway.py", "--port", "8000"], cwd=ROOT,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_ok("http://127.0.0.1:8001/health"), "stub didn't start"
        assert wait_ok(f"{GATEWAY}/health"), "gateway didn't start"

        client = httpx.Client(base_url=GATEWAY,
                              headers={"authorization": f"Bearer {KEY}",
                                       "x-user-id": "alice"})

        def post(body):
            return client.post("/v1/chat/completions", json={**base, **body})

        base = {"model": "stub", "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Help me choose."},
        ]}

        # 1) FINAL + handoff + hosting topic -> sponsored footer
        r = post({"_stub_content": "Which hosting plan should I recommend for you?"})
        assert r.status_code == 200, r.text
        d = r.json()
        full = d["choices"][0]["message"]["content"]
        model_part, _, footer = full.partition("\n---\n")
        assert d["guac"]["sponsored"] is True
        assert model_part == "Which hosting plan should I recommend for you?", \
            f"model content altered: {model_part!r}"
        assert "Sponsor: Acme Cloud Hosting" in footer
        assert "acme-hosting.png" in footer          # image render
        assert "/go/sponsor-host" in footer          # link routes through clickthrough
        assert d["guac"]["sponsorship"]["disclosed"] is True
        print("REQ1 non-stream sponsored ✓  model content byte-identical above ---")

        # 2) FINAL + no handoff (plain statement) -> NOT sponsored
        r = post({"_stub_content": "Here is the weather forecast for today."})
        d = r.json()
        assert not d.get("guac", {}).get("sponsored"), "statement should not be sponsored"
        assert "Sponsor:" not in d["choices"][0]["message"]["content"]
        print("REQ2 no-handoff statement -> no ad ✓")

        # 3) FINAL + handoff but no topic match -> NOT sponsored
        r = post({"_stub_content": "Would you like me to recommend a recipe?"})
        d = r.json()
        assert not d.get("guac", {}).get("sponsored"), "no intent match should not sponsor"
        assert "Sponsor:" not in d["choices"][0]["message"]["content"]
        print("REQ3 handoff but no topic match -> no ad ✓")

        # 4) STREAM: final + handoff + match -> footer before [DONE]
        with client.stream("POST", "/v1/chat/completions",
                           json={**base, "stream": True,
                                 "_stub_content": "Which vector database fits my project?",
                                 "_stub_finish": "stop"}) as rs:
            assert rs.status_code == 200, rs.status_code
            body = b"".join(rs.iter_bytes())
        assert len(body) > 0, "streaming returned 0 bytes"
        assert sse_footer_present(body), "stream should carry the footer before [DONE]"
        assert b'data: [DONE]' in body
        print("REQ4 stream final+handoff+match -> footer before [DONE] ✓")

        # 5) STREAM: mid-loop (finish_reason=tool_calls) -> NO footer
        with client.stream("POST", "/v1/chat/completions",
                           json={**base, "stream": True,
                                 "_stub_content": "Let me look that up.",
                                 "_stub_finish": "tool_calls"}) as rs:
            body = b"".join(rs.iter_bytes())
        assert not sse_footer_present(body), "mid-loop tool_calls must NOT carry an ad"
        assert b'data: [DONE]' in body
        print("REQ5 stream mid-loop (tool_calls) -> no ad ✓")

        # ledger: REQ1 (non-stream, hosting) + REQ4 (stream, vector) sponsored;
        # REQ2, REQ3, REQ5 non-sponsored. 5 rows total.
        with open(os.path.join(ROOT, "ledger.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        sponsored = [r for r in rows if r["sponsored"]]
        non_sponsored = [r for r in rows if not r["sponsored"]]
        assert len(rows) == 5, f"expected 5 ledger rows, got {len(rows)}"
        assert len(sponsored) == 2, f"expected 2 sponsored rows, got {len(sponsored)}"
        assert len(non_sponsored) == 3, f"expected 3 non-sponsored rows, got {len(non_sponsored)}"
        assert sponsored[0]["sponsor"] == "Acme Cloud Hosting"
        assert sponsored[1]["sponsor"] == "Nimbus Data"
        assert sponsored[0]["discount_rate"] == 0.20
        print(f"LEDGER: {len(sponsored)} sponsored, {len(non_sponsored)} non-sponsored ✓")

        print("\nALL TESTS PASSED")
        print("  - footer appended below '---' only at final+handoff+match")
        print("  - model content above '---' byte-identical (inference untouched)")
        print("  - no ad on plain statements, off-topic handoffs, or mid-loop turns")
        print("  - streamed footer injected before [DONE]")
        print("  - discount + impression still settled on sponsored rows")
    finally:
        stub.kill()
        gw.kill()


if __name__ == "__main__":
    main()
