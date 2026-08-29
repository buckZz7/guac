#!/usr/bin/env python3
"""Agnostic-client test: proves guac works as a drop-in OpenAI-compatible
endpoint for ANY harness, not just Hermes.

The client here is deliberately 'dumb' — it sends only the standard
`Authorization: Bearer <key>` header + a JSON body, with NO Hermes-specific
headers (no x-user-id). It drives non-streaming AND streaming exactly like a
bare OpenAI SDK / curl / OpenClaw / Codex / Aider client would, and asserts it
gets back a well-formed chat.completion with the disclosed footer appended
below the model answer (never injected into it).

If this passes, "agnostic from the start" is a tested invariant, not a claim.
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
KEY = "dev-gateway-key"   # any accepted guac key; no user headers sent


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


def sse_parts(body: bytes):
    """Yield (delta_content, finish_reason) from an SSE stream in order."""
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
        ch = (evt.get("choices") or [{}])[0]
        yield ch.get("delta", {}).get("content", ""), ch.get("finish_reason")


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
         "active": True, "paused": False, "budget": 5.0, "spent": 0.0},
        {"id": "sponsor-db", "sponsor": "Nimbus Data",
         "headline": "vector database trial", "body": "b", "claim": "",
         "intents": ["vector", "database", "db"], "link": "https://nimbus.example",
         "active": True, "paused": False, "budget": 5.0, "spent": 0.0},
    ]
    with open(os.path.join(td, "offers.json"), "w") as f:
        json.dump(offers, f)

    stub = start([PY, "stub.py", "--port", "8001"])
    env = dict(os.environ)
    env["ADGATE_SUPPLIERS_FILE"] = sup_file
    env["ADGATE_GATEWAY_KEY"] = KEY
    env["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")  # -> ads.json fallback
    gw = subprocess.Popen([PY, "gateway.py", "--port", "8000"], cwd=ROOT,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_ok("http://127.0.0.1:8001/health"), "stub didn't start"
        assert wait_ok(f"{GATEWAY}/health"), "gateway didn't start"

        # A strict OpenAI SDK client sends only auth + JSON body. We use a
        # bare httpx client with ONLY the authorization header — exactly what a
        # non-Hermes harness produces.
        client = httpx.Client(base_url=GATEWAY,
                              headers={"authorization": f"Bearer {KEY}"})
        assert "x-user-id" not in client.headers, "test must not send Hermes headers"

        # 1) NON-STREAM: well-formed completion + footer below ---, model untouched
        r = client.post("/v1/chat/completions", json={
            "model": "stub",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "help me choose a host"},
            ],
            "_stub_content": "Which hosting plan should I pick?",
            "_stub_finish": "stop",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        # standard OpenAI response shape
        assert d["object"] == "chat.completion"
        assert "choices" in d and "usage" in d
        ch = d["choices"][0]
        assert ch["finish_reason"] == "stop"
        full = ch["message"]["content"]
        model_part, _, footer = full.partition("\n---\n")
        assert model_part == "Which hosting plan should I pick?", model_part
        assert "Sponsor:" in footer
        assert d["guac"]["sponsorship"]["disclosed"] is True
        assert d["guac"]["sponsored"] is True
        print("AGNOSTIC non-stream: 200, well-formed completion, footer below ---, model untouched ✓")

        # 2) STREAM: SSE chunks end with the footer delta then [DONE]
        with client.stream("POST", "/v1/chat/completions",
                           json={"model": "stub",
                                 "messages": [{"role": "user", "content": "vector db choice"}],
                                 "stream": True,
                                 "_stub_content": "Which vector database fits?",
                                 "_stub_finish": "stop"}) as rs:
            assert rs.status_code == 200, rs.status_code
            body = b"".join(rs.iter_bytes())
        parts = [c for c, _ in sse_parts(body)]
        joined = "".join(parts)
        assert "Which vector database fits?" in joined
        assert "Sponsor:" in joined, "footer must appear in stream"
        assert "data: [DONE]" in body.decode(), "stream must terminate with [DONE]"
        # footer must come as the LAST content delta (right before the done marker)
        last_content = parts[-1]
        assert "Sponsor:" in last_content, f"footer should be the final delta, got {last_content!r}"
        print("AGNOSTIC stream: SSE ends with footer delta then [DONE] ✓")

        # 3) ledger records the user as 'master' (the key identity), no header needed
        with open(os.path.join(ROOT, "ledger.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        assert len(rows) == 2, rows
        assert all(r["user"] in ("master", "default") for r in rows), rows
        assert all(r["sponsored"] for r in rows), rows
        print("AGNOSTIC ledger: 2 sponsored rows, identity from key alone ✓")

        print("\nAGNOSTIC-CLIENT TESTS PASSED — drop-in OpenAI-compatible for any harness")
    finally:
        stub.kill()
        gw.kill()


if __name__ == "__main__":
    main()
