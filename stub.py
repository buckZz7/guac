"""OpenAI-compatible stub upstream — stands in for the real inference provider
so we can prove guac's injection + metering + discount end-to-end without a
live key. Echoes a canned completion and fake token usage."""
import argparse
import json

from fastapi import FastAPI, Request, Response

app = FastAPI(title="FakeUpstream")


@app.get("/health")
def health():
    return {"status": "ok"}


# Optional failure simulation for testing failover.
@app.post("/_fail")
async def fail():
    app.state.failing = True
    return {"ok": True}


@app.post("/_recover")
async def recover():
    app.state.failing = False
    return {"ok": True}


@app.post("/v1/chat/completions")
async def completions(request: Request):
    if getattr(app.state, "failing", False):
        return Response(json.dumps({"error": {"message": "stub failing"}}),
                        status_code=503, media_type="application/json")
    body = await request.json()
    messages = body.get("messages", [])
    sys = [m.get("content", "") for m in messages if m.get("role") == "system"]
    last_user = [m.get("content", "") for m in messages if m.get("role") == "user"]
    last_user = last_user[-1] if last_user else ""
    injected = "Sponsored offer" in (sys[0] if sys else "")
    # Count tokens crudely for the meter.
    prompt = sum(len(s.split()) for s in sys) + len(last_user.split())
    return {
        "id": "cmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": body.get("model", "stub"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ("(stub) " + last_user[:40]
                            + (" | ad-injected" if injected else "")),
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": 5,
            "total_tokens": prompt + 5,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
