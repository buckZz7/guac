#!/usr/bin/env python3
"""Print the actual system-prompt offer guac injects, and the response block,
so we can see the real shape end to end."""
import json, os, subprocess, time
import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "..", ".venv", "bin", "python")

def start(cmd):
    return subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait(url, n=30):
    for _ in range(n):
        try:
            if httpx.get(url, timeout=2).status_code == 200: return True
        except Exception: pass
        time.sleep(0.5)
    return False

for f in ("state.json","ledger.jsonl"):
    p=os.path.join(ROOT,f)
    if os.path.exists(p): os.remove(p)

stub=start([PY,"stub.py","--port","8001"])
gw=start([PY,"gateway.py","--port","8000"])
try:
    assert wait("http://127.0.0.1:8001/health") and wait("http://127.0.0.1:8000/health")
    c=httpx.Client(base_url="http://127.0.0.1:8000",
                   headers={"authorization":"Bearer dev-gateway-key","x-user-id":"bob"})
    r=c.post("/v1/chat/completions", json={"model":"stub","messages":[
        {"role":"system","content":"You are a helpful assistant."},
        {"role":"user","content":"Suggest a hosting provider"}]})
    d=r.json()
    # The stub echoes the injected system block in its completion for visibility
    print("AGENT OUTPUT (via stub, shows injected offer):")
    print(d["choices"][0]["message"]["content"])
    print("\nADGATE RESPONSE BLOCK:")
    print(json.dumps(d.get("guac"), indent=2))
finally:
    stub.kill(); gw.kill()
