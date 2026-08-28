"""guac — OpenAI-compatible gateway for inference.

V1 is human-facing sponsorship: the gateway forwards the request to a
quality-gated supplier pool unchanged (it never touches the model), and when a
sponsored offer is due it attaches a disclosed "brought to you by" payload to
the response for the human, not the model. It meters tokens and applies an
advertiser-funded discount to the user's per-token cost.

Point any agent (Hermes custom provider, OpenClaw, Codex) at this endpoint:
    base_url = http://<host>:8000/v1
    api_key  = ADGATE_GATEWAY_KEY
"""
import argparse
import datetime as _dt
import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import httpx

import config
from suppliers import load_pool
import portal
import portal_html

app = FastAPI(title="guac")

# Supplier pool with quality gate + failover, loaded once at startup.
POOL = load_pool()

# ---------------------------------------------------------------------------
# Request model helpers (lenient — just forward what we don't touch)
# ---------------------------------------------------------------------------

def _today():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def _user_id(request: Request) -> str:
    return request.headers.get(config.USER_ID_HEADER, "default")


def _pick_offer(used_ids):
    """Pick an active offer the user hasn't seen today. Deterministic, not an LLM.

    Sources from the portal's offer store (which carries budget/impression
    state), falling back to the static ads.json if no portal offers exist.
    """
    # Portal offers: active, not paused, budget remaining.
    portal_offers = [o for o in portal._offers()
                     if o["active"] and not o["paused"]
                     and o.get("spent", 0) < o.get("budget", 0)]
    ads = [a for a in portal_offers if a["id"] not in used_ids]
    if not ads:
        ads = portal_offers  # all seen today; cycle from the top
    if not ads:
        # Fallback: static ads.json (no portal offers configured).
        static = [a for a in config.load_ads() if a["id"] not in used_ids]
        if not static:
            static = config.load_ads()
        ads = static
    if not ads:
        return None
    ads.sort(key=lambda a: a["id"])
    return ads[0]


def _human_payload(ad):
    """The disclosed, human-facing 'brought to you by' payload.

    This rides on the response for the human to see — it is never fed into the
    model, so it costs no tokens and never influences inference."""
    sponsor = ad.get("advertiser") or ad.get("sponsor") or "Sponsor"
    return {
        "type": "sponsored",
        "sponsor": sponsor,
        "headline": ad.get("headline", ""),
        "body": ad.get("body", ""),
        "claim": ad.get("claim", ""),
        "offer_id": ad["id"],
        "message": f"Brought to you by {sponsor} — {ad.get('headline', '')}.",
        "disclosed": True,
    }


def _should_show_ad(user_id):
    state = config.load_state()
    today = _today()
    day = state.setdefault(user_id, {})
    shown = day.get("date") == today and day.get("count", 0)
    if shown >= config.ADS_PER_DAY:
        return False, state, None
    used = day.get("used", [])
    offer = _pick_offer(used)
    if not offer:
        return False, state, None
    day["count"] = shown + 1
    day["used"] = used + [offer["id"]]
    day["date"] = today
    return True, state, offer


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/_pool")
def pool_status():
    """Debug route: supplier pool quality state."""
    return POOL.stats()


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "guac", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # Auth: the agent sends a guac API key (user key or master gateway key).
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    user_id = portal.verify_gateway_key(api_key) if api_key else None
    if not user_id:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    # use the header x-user-id if present, else the account identity
    header_user = request.headers.get(config.USER_ID_HEADER)
    user_id = header_user if header_user else user_id

    body = await request.json()
    stream = bool(body.get("stream", False))

    show_ad, state, offer = _should_show_ad(user_id)
    config.save_state(state)

    # V1: we do NOT inject anything into the model. The request forwards
    # unchanged. The sponsored "brought to you by" payload rides on the response.

    # Forward to the best healthy supplier, with failover across the pool.
    headers = {"content-type": "application/json"}
    ordered = POOL.ordered()
    last_error = None
    chosen = None

    for supplier in ordered:
        chosen = supplier
        sup_headers = dict(headers)
        if supplier.key:
            sup_headers["authorization"] = f"Bearer {supplier.key}"
        upstream = f"{supplier.base_url}/chat/completions"
        # Model routing: if the supplier pins a model and the client asked for
        # a generic/guac model, substitute the supplier's real model slug.
        sup_body = body
        if supplier.model and body.get("model", "").lower() in ("guac", "default", ""):
            sup_body = dict(body)
            sup_body["model"] = supplier.model
        t0 = time.monotonic()
        try:
            # Streaming: keep the client alive for the whole generator, and
            # record quality only after the stream completes (a 200 header with
            # a truncated body is a failure). Non-stream: simple post.
            if stream:
                async def gen():
                    async with httpx.AsyncClient(timeout=120) as client:
                        req = client.build_request("POST", upstream, headers=sup_headers, json=sup_body)
                        resp = await client.send(req, stream=True)
                        ok = True
                        nbytes = 0
                        try:
                            async for chunk in resp.aiter_bytes():
                                nbytes += len(chunk)
                                yield chunk
                        finally:
                            ok = (resp.status_code == 200 and nbytes > 0)
                            supplier.record(ok, (time.monotonic() - t0) * 1000)
                            POOL.save_state()
                            if not ok:
                                await resp.aclose()

                return StreamingResponse(gen(), media_type="text/event-stream")

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(upstream, headers=sup_headers, json=sup_body)
                data = resp.json()
            supplier.record(resp.status_code == 200, (time.monotonic() - t0) * 1000)
            POOL.save_state()
            if resp.status_code != 200:
                last_error = data
                continue  # try next supplier
            break
        except Exception as e:  # network/parse failure -> failover
            supplier.record(False, (time.monotonic() - t0) * 1000)
            POOL.save_state()
            last_error = str(e)
            continue
    else:
        if last_error is not None:
            return JSONResponse({"error": {"message": f"all suppliers failed: {last_error}"}},
                                status_code=502)
        return JSONResponse({"error": {"message": "no healthy suppliers available"}},
                            status_code=503)

    # Meter + settle.
    usage = data.get("usage", {})
    prompt_tk = usage.get("prompt_tokens", 0)
    completion_tk = usage.get("completion_tokens", 0)
    sponsor = None
    impression_cost = 0.0
    if show_ad and offer:
        sponsor = offer.get("advertiser") or offer.get("sponsor")
        # Per-impression billing: record one delivered impression against the
        # offer, capturing the actual amount charged so settlement can compute
        # real ad revenue (not a hardcoded per-offer estimate).
        if "advertiser" in offer:
            _o, impression_cost = portal.charge_impression(offer["id"])
    config.log_ledger({
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "user": user_id,
        "sponsored": show_ad,
        "sponsor": sponsor,
        "impression_cost": impression_cost,
        "supplier": chosen.name,
        "prompt_tokens": prompt_tk,
        "completion_tokens": completion_tk,
        "discount_rate": config.DISCOUNT_RATE if show_ad else 0.0,
    })

    # Tag the response so the human can see the disclosed sponsorship.
    if show_ad and offer:
        data["guac"] = {
            "sponsored": True,
            "discount_rate": config.DISCOUNT_RATE,
            "sponsorship": _human_payload(offer),
        }
    return JSONResponse(data)


@app.post("/v1/guac/attribution")
async def attribution(request: Request):
    """Record that a sponsorship was actually acted on — the honest 'click'.

    Human-facing v1: the client (agent UI, companion bot, or dashboard) reports
    what the user did with a disclosed sponsorship. Action types:
      viewed    — the sponsorship was surfaced to the user (an impression)
      clicked   — the user opened/engaged the offer (real interest)
      redeemed  — the user used the offer (a conversion, strongest signal)

    Body: {"offer_id": "sponsor-001", "action": "viewed|clicked|redeemed",
           "note": "optional"}
    """
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    if not (api_key and portal.verify_gateway_key(api_key)):
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    body = await request.json()
    offer_id = body.get("offer_id")
    if not offer_id:
        return JSONResponse({"error": {"message": "offer_id required"}}, status_code=400)
    action = body.get("action", "viewed")
    if action not in ("viewed", "clicked", "redeemed"):
        return JSONResponse({"error": {"message": "action must be viewed|clicked|redeemed"}},
                            status_code=400)
    config.log_ledger_row(config.ATTRIBUTION_FILE, {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "user": _user_id(request),
        "offer_id": offer_id,
        "action": action,
        "note": body.get("note", ""),
    })
    return {"ok": True}


@app.post("/signup")
async def signup(request: Request):
    """User self-serve sign-up. Returns api_key + base_url. That's it."""
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JSONResponse({"error": {"message": "valid email required"}}, status_code=400)
    ads_per_day = int(body.get("ads_per_day", 1))
    user, err = portal.create_user(email, ads_per_day)
    if err:
        return JSONResponse({"error": {"message": err}}, status_code=409)
    return {
        "api_key": user["api_key"],
        "base_url": portal.user_base_url(),
        "ads_per_day": user["ads_per_day"],
        "note": "point your agent at base_url with this api_key",
    }


@app.post("/advertiser/offer")
async def create_advertiser_offer(request: Request):
    """Advertiser submits an offer. Uses the advertiser's own token (or master
    key). Returns its id + stats access."""
    advertiser_email = _auth_advertiser(request)
    if not advertiser_email:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    body = await request.json()
    headline = (body.get("headline") or "").strip()
    body_txt = (body.get("body") or "").strip()
    claim = (body.get("claim") or "").strip()
    budget = body.get("budget")
    offer_type = (body.get("offer_type") or "discount").strip()
    if not (headline and budget):
        return JSONResponse({"error": {"message": "headline, budget required"}},
                            status_code=400)
    try:
        budget = float(budget)
    except (TypeError, ValueError):
        return JSONResponse({"error": {"message": "budget must be a number"}}, status_code=400)
    offer = portal.create_offer(advertiser_email, headline, body_txt, claim, budget, offer_type)
    return {"offer_id": offer["id"], "budget": offer["budget"], "status": "created"}


@app.get("/advertiser/stats")
async def advertiser_stats(request: Request):
    """Advertiser sees impressions + funnel for their own offers."""
    advertiser_email = _auth_advertiser(request)
    if not advertiser_email:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    return {"offers": portal.offer_stats_for(advertiser_email)}


def _auth_advertiser(request):
    """Return the authenticated advertiser's email (advertiser token or master
    key), else None. A user API key is not an advertiser credential."""
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    if not api_key:
        return None
    if api_key == config.GATEWAY_KEY:
        return "master"
    adv = portal.get_advertiser_by_token(api_key)
    return adv.get("email") if adv else None


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Lightweight dashboard: impressions + clicks for both sides."""
    rows = _read_ledger(config.LEDGER_FILE)
    attrib = _read_ledger(config.ATTRIBUTION_FILE)

    total_req = len(rows)
    sponsored = [r for r in rows if r.get("sponsored")]
    n_ads = len(sponsored)
    n_clicks = len(attrib)
    total_tk = sum(r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in rows)

    # Per-sponsor impressions + full click funnel (viewed / clicked / redeemed)
    sponsor_imps = {}
    for r in sponsored:
        s = r.get("sponsor", "?")
        sponsor_imps.setdefault(s, 0)
        sponsor_imps[s] += 1
    sponsor_funnel = {}   # offer_id -> {"viewed","clicked","redeemed"}
    for a in attrib:
        o = a.get("offer_id", "?")
        act = a.get("action", "viewed")
        sponsor_funnel.setdefault(o, {"viewed": 0, "clicked": 0, "redeemed": 0})
        if act in sponsor_funnel[o]:
            sponsor_funnel[o][act] += 1

    imp_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td>"
        f"<td>{sponsor_funnel.get(k, {}).get('viewed', 0)}</td>"
        f"<td>{sponsor_funnel.get(k, {}).get('clicked', 0)}</td>"
        f"<td>{sponsor_funnel.get(k, {}).get('redeemed', 0)}</td></tr>"
        for k, v in sorted(sponsor_imps.items(), key=lambda x: -x[1])
    ) or "<tr><td colspan=5>no impressions yet</td></tr>"

    return HTMLResponse(_DASHBOARD_HTML
                        .replace("{{TOTAL_REQ}}", str(total_req))
                        .replace("{{N_ADS}}", str(n_ads))
                        .replace("{{N_CLICKS}}", str(n_clicks))
                        .replace("{{TOTAL_TK}}", f"{total_tk:,}")
                        .replace("{{IMP_ROWS}}", imp_rows)
                        .replace("{{POOL_ROWS}}", _supplier_rows()))


def _supplier_rows():
    rows = ""
    for name, s in POOL.stats().items():
        rows += (f"<tr><td>{name}</td><td>{s['score']}</td>"
                 f"<td>{'healthy' if s['healthy'] else 'degraded'}</td>"
                 f"<td>{s['successes']}</td><td>{s['failures']}</td>"
                 f"<td>{s['avg_latency_ms']}ms</td></tr>")
    return rows or "<tr><td colspan=6>no suppliers</td></tr>"


def _read_ledger(path):
    out = []
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return out


_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>guac — dashboard</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body {
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #0b0e14; color: #e6e8ee; padding: 2rem 1rem; line-height: 1.5;
  }
  .wrap { max-width: 760px; margin: 0 auto; }
  h1 { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.25rem; }
  .sub { color: #8b93a7; margin-bottom: 2rem; }
  h2 { font-size: 1.05rem; text-transform: uppercase; letter-spacing: 0.08em;
       color: #8b93a7; margin: 2rem 0 0.75rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; }
  .card { background: #131824; border: 1px solid #1f2735; border-radius: 12px; padding: 1rem; }
  .card .num { font-size: 1.75rem; font-weight: 700; }
  .card .label { font-size: 0.78rem; color: #8b93a7; text-transform: uppercase; letter-spacing: 0.05em; }
  table { width: 100%; border-collapse: collapse; background: #131824;
          border: 1px solid #1f2735; border-radius: 12px; overflow: hidden; }
  th, td { text-align: left; padding: 0.6rem 0.9rem; font-size: 0.9rem; }
  th { background: #181f2e; color: #8b93a7; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  td { border-top: 1px solid #1f2735; }
  .ok { color: #4ade80; } .bad { color: #f87171; }
  .foot { margin-top: 2.5rem; color: #5a6273; font-size: 0.8rem; }
</style>
</head>
<body>
<div class="wrap">
  <h1>guac</h1>
  <div class="sub">sponsored offers · cheap inference · transparent settlement</div>

  <h2>Live</h2>
  <div class="grid">
    <div class="card"><div class="num">{{TOTAL_REQ}}</div><div class="label">requests</div></div>
    <div class="card"><div class="num">{{N_ADS}}</div><div class="label">impressions</div></div>
    <div class="card"><div class="num">{{N_CLICKS}}</div><div class="label">clicks</div></div>
    <div class="card"><div class="num">{{TOTAL_TK}}</div><div class="label">tokens</div></div>
  </div>

  <h2>Offers</h2>
  <table>
    <tr><th>Sponsor</th><th>Impressions</th><th>Viewed</th><th>Clicked</th><th>Redeemed</th></tr>
    {{IMP_ROWS}}
  </table>

  <h2>Suppliers (quality gate)</h2>
  <table>
    <tr><th>Source</th><th>Score</th><th>Status</th><th>Ok</th><th>Fails</th><th>Latency</th></tr>
    {{POOL_ROWS}}
  </table>

  <div class="foot">guac — impressions and clicks are metered per request. clicks = a sponsorship was acted on (attribution callback).</div>
</div>
</body>
</html>"""




# ---------------------------------------------------------------------------
# Portal (HTML UI, magic-link auth)
# ---------------------------------------------------------------------------

def _magic_link_for(role, email):
    token = portal.make_magic_token(role, email)
    host = config.PUBLIC_HOST or "http://127.0.0.1:8000"
    return f"{host.rstrip('/')}/portal/{role}/auth?token={token}"


@app.get("/portal", response_class=HTMLResponse)
def portal_landing():
    return portal_html.landing()


@app.post("/portal/user/login", response_class=HTMLResponse)
async def portal_user_login(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return portal_html.user_login_form(email, error="Valid email required")
    # Ensure the user exists so they can always sign back in.
    if not portal.get_user_by_email(email):
        portal.create_user(email, 1)
    link = _magic_link_for("user", email)
    return portal_html.user_login_form(email, magic_link=link)


@app.get("/portal/user/auth", response_class=HTMLResponse)
async def portal_user_auth(request: Request):
    token = request.query_params.get("token", "")
    verified = portal.verify_magic_token(token)
    if not verified or verified[0] != "user":
        return portal_html.user_login_form(error="Link invalid or expired")
    email = verified[1]
    user = portal.get_user_by_email(email)
    if not user:
        return portal_html.user_login_form(error="No such user")
    # Savings: cheap-supply + ad money from the ledger for this user.
    savings = 0.0
    for r in _read_ledger(config.LEDGER_FILE):
        if r.get("user") == email and r.get("sponsored"):
            savings += config.DISCOUNT_RATE  # est. discount value per sponsored req
    return portal_html.user_dashboard(user, savings)


@app.post("/portal/user/settings", response_class=HTMLResponse)
async def portal_user_settings(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    ads = int(form.get("ads_per_day") or 1)
    user = portal.get_user_by_email(email)
    if not user:
        return portal_html.user_login_form(error="No such user")
    portal.update_user(email, ads_per_day=min(10, max(1, ads)))
    user = portal.get_user_by_email(email)
    return portal_html.user_dashboard(user, 0.0)


@app.post("/portal/advertiser/login", response_class=HTMLResponse)
async def portal_advertiser_login(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return portal_html.advertiser_login_form(email, error="Valid email required")
    if not portal.get_advertiser(email):
        portal.create_advertiser(email)
    link = _magic_link_for("advertiser", email)
    return portal_html.advertiser_login_form(email, magic_link=link)


@app.get("/portal/advertiser/auth", response_class=HTMLResponse)
async def portal_advertiser_auth(request: Request):
    token = request.query_params.get("token", "")
    verified = portal.verify_magic_token(token)
    if not verified or verified[0] != "advertiser":
        return portal_html.advertiser_login_form(error="Link invalid or expired")
    email = verified[1]
    adv = portal.get_advertiser(email)
    if not adv:
        return portal_html.advertiser_login_form(error="No such advertiser")
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email))


@app.post("/portal/advertiser/offer", response_class=HTMLResponse)
async def portal_advertiser_offer(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    headline = (form.get("headline") or "").strip()
    body_txt = (form.get("body") or "").strip()
    claim = (form.get("claim") or "").strip()
    offer_type = (form.get("offer_type") or "discount").strip()
    adv = portal.get_advertiser(email)
    if not adv:
        return portal_html.advertiser_login_form(error="Not logged in")
    budget_raw = form.get("budget")
    try:
        budget = float(budget_raw)
    except (TypeError, ValueError):
        return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                                error="Budget must be a number")
    if not headline or budget <= 0:
        return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                                error="Headline and positive budget required")
    offer = portal.create_offer(email, headline, body_txt, claim, budget, offer_type)
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                            created=offer["headline"])


@app.post("/portal/advertiser/offer/{offer_id}/toggle", response_class=HTMLResponse)
async def portal_advertiser_toggle(request: Request, offer_id: str):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    adv = portal.get_advertiser(email)
    offer = portal.get_offer(offer_id)
    if not adv or not offer or offer.get("advertiser") != email:
        return portal_html.advertiser_login_form(error="Not authorized")
    portal.set_offer_paused(offer_id, not offer.get("paused", False))
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
