"""OpenAI-compatible stub upstream — stands in for the real inference provider
so we can prove guac's injection + metering + discount end-to-end without a
live key. Echoes a canned completion and fake token usage."""
import argparse
import json

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

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


@app.get("/_last_body")
async def last_body():
    """Test hook: the exact body the gateway forwarded on the last request."""
    return getattr(app.state, "last_body", None) or {}


@app.post("/v1/chat/completions")
async def completions(request: Request):
    if getattr(app.state, "failing", False):
        return Response(json.dumps({"error": {"message": "stub failing"}}),
                        status_code=503, media_type="application/json")
    body = await request.json()
    app.state.last_body = body  # test hook: inspect what the gateway forwarded
    messages = body.get("messages", [])
    sys = [m.get("content", "") for m in messages if m.get("role") == "system"]
    last_user = [m.get("content", "") for m in messages if m.get("role") == "user"]
    last_user = last_user[-1] if last_user else ""
    injected = "Sponsored offer" in (sys[0] if sys else "")
    # Test hooks: the gateway forwards the body unchanged, so tests can pin the
    # stub's output via private fields to exercise the decision-point gate.
    content = body.get("_stub_content") or ("(stub) " + last_user[:40])
    finish = body.get("_stub_finish", "stop")
    # Count tokens crudely for the meter.
    prompt = sum(len(s.split()) for s in sys) + len(last_user.split())

    # SSE streaming mode (used by the streaming regression test).
    if body.get("stream"):
        if not injected:
            content = content  # echo as-is
        else:
            content = content + " | ad-injected"
        import time as _t
        async def sse():
            for tok in content.split(" "):
                chunk = {"id": "cmpl-stub", "object": "chat.completion.chunk",
                         "created": 0, "model": body.get("model", "stub"),
                         "choices": [{"index": 0, "delta": {"content": tok + " "},
                                      "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
            done = {"id": "cmpl-stub", "object": "chat.completion.chunk",
                    "created": 0, "model": body.get("model", "stub"),
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
            yield f"data: {json.dumps(done)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(sse(), media_type="text/event-stream")

    return {
        "id": "cmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": body.get("model", "stub"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content + (" | ad-injected" if injected else ""),
            },
            "finish_reason": finish,
        }],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": len(content.split()),
            "total_tokens": prompt + len(content.split()),
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
