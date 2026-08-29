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
import re
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
import httpx

import config
import limits
import mailer
import oauth
import payments
from suppliers import load_pool
import portal
import portal_html
import settlement
import backup

app = FastAPI(title="guac")

# Supplier pool with quality gate + failover, loaded once at startup.
POOL = load_pool()

# ---------------------------------------------------------------------------
# Request model helpers (lenient — just forward what we don't touch)
# ---------------------------------------------------------------------------


def _user_id(request: Request) -> str:
    return request.headers.get(config.USER_ID_HEADER, "default")


def _active_offers():
    """Active offers with advertiser demand (budget remaining): from the portal
    store. The static ads.json demo inventory is ONLY served when explicitly
    enabled (ADGATE_ALLOW_DEMO_ADS=1) — production must never show unfunded,
    unaffiliated offers. No active funded offer = no ads."""
    portal_offers = [o for o in portal._offers()
                     if o.get("active") and not o.get("paused")
                     and o.get("spent", 0) < o.get("budget", 0)]
    if portal_offers:
        return portal_offers
    if config.ALLOW_DEMO_ADS:
        return [a for a in config.load_ads()
                if a.get("active", True) and not a.get("paused", False)]
    return []


# --- Demand-gated daily cadence (V1) ---
# An ad is appended after an agent's FINAL answer (finish_reason == "stop"),
# up to a flat daily cap per user, ONLY when there is funded advertiser demand
# (an active offer with budget remaining). No topic matching, no handoff
# heuristic — just: final answer + under cap + demand exists -> append.
# The finish_reason gate is what kills the narration noise: tool_calls turns are
# mid-loop, never final, and so never qualify.

def _daily_state(user_id):
    """Per-user daily ad count + rotation offset, persisted so restarts don't
    reset it. Demand-gated: count only accrues when an ad was actually shown."""
    state = config.load_state()
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    day = state.setdefault(user_id, {})
    if day.get("date") != today:
        day["date"] = today
        day["count"] = 0
    return state, day


def _should_show_ad(user_id):
    """Append an ad iff: funded demand exists AND user under daily cap. Returns
    (show, offer_or_None). Deterministic rotation across offers.

    'Demand' = an active offer whose advertiser has prepaid balance (or a static
    ads.json offer, treated as standing funded inventory). No funded advertiser
    -> no ads -> the system is honest about money."""
    offers = _active_offers()
    if not offers:
        return False, None
    # Demand gate: at least one offer must be fundable. Static offers (no
    # advertiser field) are assumed funded; portal offers require a balance.
    from payments import balance_for

    def funded(o):
        adv = o.get("advertiser")
        if not adv:
            return True  # static standing inventory
        if o.get("spent", 0) >= o.get("budget", 0):
            return False
        return balance_for(adv) >= config.IMPRESSION_COST
    if not any(funded(o) for o in offers):
        return False, None
    state, day = _daily_state(user_id)
    if day.get("count", 0) >= config.ADS_PER_DAY:
        return False, None
    # Deterministic rotation: pick offers by id, cycling from the day's offset.
    offers.sort(key=lambda o: o["id"])
    pick = offers[day.get("offset", 0) % len(offers)]
    day["offset"] = day.get("offset", 0) + 1
    day["count"] = day.get("count", 0) + 1
    config.save_state(state)
    return True, pick


def _human_payload(ad):
    """The disclosed, human-facing sponsorship payload. Rides on the response
    for the human to see — never fed into the model, so it costs no tokens."""
    sponsor = ad.get("advertiser") or ad.get("sponsor") or "Sponsor"
    return {
        "type": "sponsored",
        "sponsor": sponsor,
        "headline": ad.get("headline", ""),
        "body": ad.get("body", ""),
        "claim": ad.get("claim", ""),
        "image_url": ad.get("image_url", ""),
        "link": ad.get("link", ""),
        "offer_id": ad["id"],
        "message": f"Sponsor: {sponsor} — {ad.get('headline', '')}.",
        "disclosed": True,
    }


def _footer_text(ad):
    """The block appended BELOW the model's answer, cleanly delimited by --- so
    the model content above the line stays untouched and honest."""
    sponsor = ad.get("advertiser") or ad.get("sponsor") or "Sponsor"
    lines = ["", "---", f"Sponsor: {sponsor} — {ad.get('headline', '')}"]
    if ad.get("body"):
        lines.append(ad["body"])
    if ad.get("claim"):
        lines.append(f"Claim: {ad['claim']}")
    if ad.get("image_url"):
        lines.append(f"![{sponsor}]({ad['image_url']})")
    if ad.get("link"):
        # Route the link through /go/<offer_id> so the click is logged (honest
        # funnel) before redirecting. The link must be ABSOLUTE: the delivery
        # surface is a terminal/chat client where a relative path is dead.
        base = (config.PUBLIC_HOST or "http://127.0.0.1:8000").rstrip("/")
        lines.append(f"[Learn more]({base}/go/{ad['id']})")
    return "\n".join(lines) + "\n"


def _words(s):
    return len((s or "").split())


# The sponsorship footer guac appends below an answer always starts with this
# delimiter. Agents (Hermes etc.) replay whole session histories into context,
# so an old footer would otherwise re-enter the model AND get billed as tokens
# forever. The gateway owns the wire: strip its own footers from inbound
# assistant history before forwarding.
_FOOTER_MARK = "\n---\nSponsor: "


def _strip_footers_from_content(content):
    if isinstance(content, str):
        idx = content.find(_FOOTER_MARK)
        if idx != -1:
            return content[:idx]
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                p = dict(part)
                p["text"] = _strip_footers_from_content(p["text"])
                out.append(p)
            else:
                out.append(part)
        return out
    return content


def _strip_replayed_footers(body):
    """Return the body with guac's own sponsor footers removed from assistant
    history (inbound messages only — the outbound answer is untouched)."""
    messages = body.get("messages")
    if not messages:
        return body
    cleaned = []
    changed = False
    for m in messages:
        if m.get("role") == "assistant" and m.get("content"):
            new_content = _strip_footers_from_content(m["content"])
            if new_content != m["content"]:
                m = dict(m)
                m["content"] = new_content
                changed = True
        cleaned.append(m)
    if not changed:
        return body
    body = dict(body)
    body["messages"] = cleaned
    return body


def _valid_https_url(url):
    """A link must be a well-formed https URL (no javascript:, file:, etc.)."""
    if not url:
        return True  # optional
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.netloc)


def _safe_offer_fields(headline, body, claim, image_url, link):
    """Trim + validate offer fields. Returns (cleaned_dict, error_or_None)."""
    headline = (headline or "").strip()
    body = (body or "").strip()
    claim = (claim or "").strip()
    image_url = (image_url or "").strip()
    link = (link or "").strip()
    if not headline:
        return None, "headline required"
    if link and not _valid_https_url(link):
        return None, "link must be a valid https:// URL"
    if image_url and not _valid_https_url(image_url):
        return None, "image_url must be a valid https:// URL"
    return {
        "headline": headline, "body": body, "claim": claim,
        "image_url": image_url, "link": link,
    }, None


def _prompt_tokens(body):
    n = 0
    for m in body.get("messages", []):
        c = m.get("content")
        if isinstance(c, str):
            n += len(c.split())
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("text"):
                    n += len(str(p["text"]).split())
    return n


def _billable_user(uid):
    """Only real user accounts are billed. The master gateway key (operator)
    and advertiser identities are not billed for inference."""
    return uid and uid != "master" and not uid.startswith("advertiser:")


def _resolve_discount(supplier, model):
    """The discount for one request: explicit per-model entry wins, then the
    serving supplier's discount field, then the global default. Per-model
    discounts live in config.MODEL_DISCOUNTS; per-supplier in suppliers.json."""
    d = config.MODEL_DISCOUNTS.get(model)
    if d is not None:
        return d
    if supplier.discount is not None:
        return supplier.discount
    return config.DISCOUNT_RATE


def _request_cost(supplier, body, usage, model, completion_words=None):
    """The USER's price for one request: the market rate for these tokens,
    minus the discount resolved for THIS model/supplier. Users never see the
    full price on a discounted model. Advertiser revenue funds the gap.

    Pinned suppliers: REFERENCE_PRICING (market $/M), discounted.
    Passthrough: the supplier-reported usage.cost when present (OpenRouter
    reports real cost), discounted; else the flat blended rate, discounted.
    """
    prompt_tk = usage.get("prompt_tokens", 0) or _prompt_tokens(body)
    completion_tk = usage.get("completion_tokens", 0)
    if not completion_tk and completion_words:
        completion_tk = completion_words
    keep = 1.0 - _resolve_discount(supplier, model)
    price = config.REFERENCE_PRICING.get(supplier.name)
    if price:
        p_per_m, c_per_m = price
        market = (prompt_tk * p_per_m + completion_tk * c_per_m) / 1_000_000
        return market * keep
    cost = usage.get("cost")
    if isinstance(cost, (int, float)) and cost > 0:
        return float(cost) * keep
    market = (prompt_tk + completion_tk) * config.PASSTHROUGH_WHOLESALE_PER_M / 1_000_000
    return market * keep


def _bill_user(uid, cost, model, supplier_name, discount_rate):
    """Bill one request to the user's prepaid balance at the model's
    discounted rate. Returns the bill dict recorded in the ledger. If the
    balance can't cover it, the row is marked unpaid — the pre-flight gate
    402s the NEXT request, so at most one request rides slightly past the
    balance."""
    charged = payments.charge_request(uid, cost, note=f"{model} via {supplier_name}")
    return {
        "cost": round(cost, 8),          # what the user pays (already discounted)
        "discount_rate": discount_rate,
        "unpaid": (not charged),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    """Deep health check for alerting. Returns HTTP 200 only if the app is up
    AND at least one supplier is healthy AND the state volume is writable.
    Otherwise 503 with a reason — so a poller can alert on a non-200."""
    problems = []
    # 1) at least one healthy supplier (else no requests can be served)
    healthy = [s.name for s in POOL.suppliers if s.healthy()]
    if not healthy:
        problems.append("no healthy suppliers")

    # 2) state volume writable (can the gateway persist state?)
    probe = config.STATE_FILE.with_suffix(config.STATE_FILE.suffix + ".probe")
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok")
        probe.unlink()
    except Exception:
        problems.append("state volume not writable")

    if problems:
        return JSONResponse({"status": "degraded", "problems": problems},
                            status_code=503)
    return {"status": "ok", "healthy_suppliers": healthy}


@app.get("/_pool")
def pool_status(request: Request):
    """Debug route: supplier pool quality state. Master-key only."""
    if _master_key(request):
        return POOL.stats()
    return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "guac", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    # Auth: the agent sends a guac API key (user key or master gateway key).
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    billing_id = portal.verify_gateway_key(api_key) if api_key else None
    if not billing_id:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    # Billing identity is the KEY OWNER. x-user-id may override identity only
    # for the master key (operator/testing) — otherwise a user could bill their
    # requests to someone else's balance by spoofing the header.
    header_user = request.headers.get(config.USER_ID_HEADER)
    uid = header_user if (header_user and billing_id == "master") else billing_id

    body = await request.json()
    # Hermes-style clients replay full session history: strip guac's own sponsor
    # footers from inbound assistant turns so ad text never re-enters the model
    # and is never billed as tokens twice.
    body = _strip_replayed_footers(body)
    stream = bool(body.get("stream", False))
    model = body.get("model", "guac")

    # Paid-with-discount: users prepay, and EVERY request bills the discounted
    # rate — sponsored or not. Advertiser revenue funds the discount; the user
    # just sees a cheaper price. Empty balance -> 402. Master key (operator)
    # and advertiser identities are never gated or billed here.
    if _billable_user(billing_id) and payments.balance_for(billing_id) <= 0:
        return JSONResponse({"error": {
            "message": "balance empty — top up in the portal to keep using guac",
            "code": "insufficient_balance",
        }}, status_code=402)

    # Per-key daily token budget: reject before forwarding if this key would
    # exceed its cap. Uses the prompt size as a conservative estimate so a key
    # can't burn unbounded upstream spend.
    if config.DAILY_TOKEN_CAP > 0:
        est = _prompt_tokens(body)
        if not limits.token_budget_ok(api_key or uid, est):
            return JSONResponse({"error": {"message": "daily token budget exceeded"}},
                                status_code=429)

    # V1 (decision-point): we do NOT inject anything into the model. The
    # request forwards unchanged; a sponsorship is appended BELOW the answer
    # only on a final turn (finish_reason == "stop") when funded demand exists.

    # Forward to the best healthy supplier, with failover across the pool.
    generic_model = model.lower() in ("guac", "default", "")
    headers = {"content-type": "application/json"}
    ordered = POOL.ordered()
    # Model routing: a generic request ("guac") prefers suppliers that pin a
    # real model slug (substituted for the request); if none exist, the model
    # name forwards as-is (stub/development providers). A SPECIFIC model slug
    # only goes to suppliers that serve it unchanged: passthrough suppliers,
    # or suppliers with no pinned model (nothing to substitute).
    if generic_model:
        candidates = [s for s in ordered if s.model] or ordered
    else:
        candidates = [s for s in ordered if not s.model or s.passthrough]
    last_error = None
    chosen = None

    for supplier in candidates:
        # Skip a supplier that expects a key from the environment but has none
        # configured — it can never authenticate and would hang / fail upstream,
        # so fail fast to a supplier that can serve. Suppliers with no key at
        # all (e.g. a local stub) are still allowed through.
        if supplier.key_env and not supplier.key:
            continue
        chosen = supplier
        sup_headers = dict(headers)
        if supplier.key:
            sup_headers["authorization"] = f"Bearer {supplier.key}"
        upstream = f"{supplier.base_url}/chat/completions"
        sup_body = body
        if generic_model and supplier.model:
            sup_body = dict(body)
            sup_body["model"] = supplier.model
        t0 = time.monotonic()
        try:
            if stream:
                async def gen():
                    async with httpx.AsyncClient(timeout=120) as client:
                        req = client.build_request("POST", upstream, headers=sup_headers, json=sup_body)
                        resp = await client.send(req, stream=True)
                        nbytes = 0
                        buf = b""
                        parts = []
                        finish = None
                        done_event = None
                        try:
                            async for chunk in resp.aiter_bytes():
                                nbytes += len(chunk)
                                buf += chunk
                                # Emit complete SSE events, holding [DONE] until
                                # we know whether to append the footer.
                                while True:
                                    idx = buf.find(b"\n\n")
                                    if idx == -1:
                                        break
                                    event = buf[:idx]
                                    buf = buf[idx + 2:]
                                    line = event.decode("utf-8", errors="replace")
                                    if not line.startswith("data:"):
                                        yield event + b"\n\n"
                                        continue
                                    payload = line[5:].strip()
                                    if payload == "[DONE]":
                                        done_event = event + b"\n\n"
                                        continue
                                    try:
                                        evt = json.loads(payload)
                                    except Exception:
                                        yield event + b"\n\n"
                                        continue
                                    for ch in evt.get("choices", []):
                                        c = ch.get("delta", {}).get("content")
                                        if c:
                                            parts.append(c)
                                        fr = ch.get("finish_reason")
                                        if fr:
                                            finish = fr
                                    yield event + b"\n\n"
                            if buf:
                                yield buf
                            # Now the full answer is known: decide the footer.
                            full = "".join(parts)
                            offer = None
                            if finish == "stop":
                                offer = _should_show_ad(uid)[1]
                            sponsor = None
                            impression_cost = 0.0
                            if offer:
                                sponsor = offer.get("advertiser") or offer.get("sponsor")
                                _o, impression_cost = portal.charge_impression(offer["id"])
                                footer = _footer_text(offer)
                                fe = {"id": "cmpl-guac", "object": "chat.completion.chunk",
                                      "created": 0, "model": model,
                                      "choices": [{"index": 0, "delta": {"content": footer},
                                                   "finish_reason": None}]}
                                yield f"data: {json.dumps(fe)}\n\n".encode()
                            # Bill at the discounted rate (SSE has no usage
                            # block, so cost is estimated from tokens).
                            bill = None
                            if _billable_user(billing_id):
                                s_cost = _request_cost(chosen, body, {}, model,
                                                       completion_words=_words(full))
                                bill = _bill_user(billing_id, s_cost, model,
                                                  chosen.name,
                                                  _resolve_discount(chosen, model))
                            config.log_ledger({
                                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                                "user": uid,
                                "sponsored": offer is not None,
                                "sponsor": sponsor,
                                "impression_cost": impression_cost,
                                "supplier": chosen.name,
                                "model": model,
                                "prompt_tokens": _prompt_tokens(body),
                                "completion_tokens": _words(full),
                                "bill": bill,
                            })
                            limits.record_tokens(api_key or uid,
                                                 _prompt_tokens(body) + _words(full))
                            if done_event:
                                yield done_event
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

    # Non-streaming: meter, settle, and (maybe) append the footer below the answer.
    usage = data.get("usage", {})
    prompt_tk = usage.get("prompt_tokens", 0)
    completion_tk = usage.get("completion_tokens", 0)
    content = data["choices"][0]["message"].get("content", "")
    finish = data["choices"][0].get("finish_reason")

    offer = None
    if finish == "stop":
        offer = _should_show_ad(uid)[1]

    sponsor = None
    impression_cost = 0.0
    if offer:
        sponsor = offer.get("advertiser") or offer.get("sponsor")
        # Per-impression billing: record one delivered impression against the
        # offer, capturing the actual amount charged so settlement can compute
        # real ad revenue (not a hardcoded per-offer estimate).
        _o, impression_cost = portal.charge_impression(offer["id"])
        # Append the disclosed footer BELOW the model answer, delimited by ---.
        data["choices"][0]["message"]["content"] = content + _footer_text(offer)
        data["guac"] = {
            "sponsored": True,
            "sponsorship": _human_payload(offer),
        }

    # Bill at the model's discounted rate — every request, sponsored or not.
    cost = _request_cost(chosen, body, usage, model)
    bill = _bill_user(billing_id, cost, model, chosen.name,
                      _resolve_discount(chosen, model)) \
        if _billable_user(billing_id) else None
    config.log_ledger({
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "user": uid,
        "sponsored": offer is not None,
        "sponsor": sponsor,
        "impression_cost": impression_cost,
        "supplier": chosen.name,
        "model": model,
        "prompt_tokens": prompt_tk,
        "completion_tokens": completion_tk,
        "bill": bill,
    })
    limits.record_tokens(api_key or uid, prompt_tk + completion_tk)
    return JSONResponse(data)


@app.get("/go/{offer_id}")
def offer_redirect(offer_id: str):
    """Clickthrough redirect: /go/<offer_id> logs a real click on the offer and
    302s to its link. This is the non-fakeable click — it only happens when
    someone actually clicks the offer, and it works with ANY harness (no client
    cooperation needed). Feeds the attribution funnel + can stamp tracking params.
    """
    # Look up the offer (portal store, then static ads.json fallback).
    offer = portal.get_offer(offer_id)
    if not offer:
        for a in config.load_ads():
            if a.get("id") == offer_id:
                offer = a
                break
    if not offer:
        return JSONResponse({"error": "offer not found"}, status_code=404)
    link = offer.get("link")
    if not link:
        return JSONResponse({"error": "offer has no link"}, status_code=404)
    # Record the click (honest funnel; attribution is also used by advertisers).
    config.log_ledger_row(config.ATTRIBUTION_FILE, {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "offer_id": offer_id,
        "action": "clicked",
        "source": "redirect",
    })
    # Stamp tracking params so the affiliate network attributes the conversion.
    sep = "&" if "?" in link else "?"
    target = f"{link}{sep}ref=guac&utm_source=guac&utm_campaign={offer_id}"
    return RedirectResponse(target, status_code=302)


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
    # Rate-limit signups per source IP to stop account-spam.
    client_ip = request.client.host if request.client else "unknown"
    if not limits.allow_signup(client_ip):
        return JSONResponse({"error": {"message": "too many signups — try later"}},
                            status_code=429)
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JSONResponse({"error": {"message": "valid email required"}}, status_code=400)
    user, err = portal.create_user(email)
    if err:
        return JSONResponse({"error": {"message": err}}, status_code=409)
    return {
        "api_key": user["api_key"],
        "base_url": portal.user_base_url(),
        "note": "point your agent at base_url with this api_key. A disclosed sponsor "
                "appears below the answer only at a real decision point.",
    }


@app.post("/advertiser/offer")
async def create_advertiser_offer(request: Request):
    """Advertiser submits an offer. Uses the advertiser's own token (or master
    key). Returns its id + stats access."""
    advertiser_email = _auth_advertiser(request)
    if not advertiser_email:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    body = await request.json()
    offer_type = (body.get("offer_type") or "discount").strip()
    cleaned, err = _safe_offer_fields(body.get("headline"), body.get("body"),
                                      body.get("claim"), body.get("image_url"),
                                      body.get("link"))
    if err:
        return JSONResponse({"error": {"message": err}}, status_code=400)
    budget = body.get("budget")
    if not cleaned["headline"] or budget is None:
        return JSONResponse({"error": {"message": "headline, budget required"}},
                            status_code=400)
    try:
        budget = float(budget)
    except (TypeError, ValueError):
        return JSONResponse({"error": {"message": "budget must be a number"}}, status_code=400)
    offer = portal.create_offer(advertiser_email, cleaned["headline"], cleaned["body"],
                                cleaned["claim"], budget, offer_type, [],
                                cleaned["image_url"], cleaned["link"])
    return {"offer_id": offer["id"], "budget": offer["budget"], "status": "created"}


@app.get("/advertiser/stats")
async def advertiser_stats(request: Request):
    """Advertiser sees impressions + funnel for their own offers."""
    advertiser_email = _auth_advertiser(request)
    if not advertiser_email:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    stats = portal.offer_stats_for(advertiser_email)
    balance = payments.balance_for(advertiser_email)
    return {"balance": balance, "backend": payments.backend(), "offers": stats}


@app.post("/advertiser/topup")
async def advertiser_topup(request: Request):
    """Start an advertiser balance top-up. Mock backend credits immediately and
    returns {credited: true}. Stripe backend returns a Checkout URL.
    Accepts JSON ({amount_cents}, Bearer token) or a portal form post (hidden
    'token' field)."""
    # Auth: advertiser token via Bearer header OR a form 'token' field.
    advertiser_email = _auth_advertiser(request)
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        amount_raw = body.get("amount_cents", 0)
    else:
        form = await request.form()
        if not advertiser_email:
            adv = portal.get_advertiser_by_token((form.get("token") or "").strip())
            advertiser_email = adv.get("email") if adv else None
        amount_raw = form.get("amount_cents", 0)
    if not advertiser_email or advertiser_email == "master":
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    try:
        amount_cents = int(amount_raw)
    except (TypeError, ValueError):
        return JSONResponse({"error": {"message": "amount_cents must be an integer"}},
                            status_code=400)
    try:
        result = payments.create_topup(advertiser_email, amount_cents, kind="advertiser")
    except ValueError as e:
        return JSONResponse({"error": {"message": str(e)}}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": {"message": f"payment error: {e}"}},
                            status_code=502)
    result["balance"] = payments.balance_for(advertiser_email)
    if "application/json" not in ctype:
        return HTMLResponse(f"<h2>Balance updated to ${result['balance']:.2f}</h2>"
                            f"<p><a href='/portal'>Back to portal</a></p>")
    return result


@app.post("/user/topup")
async def user_topup(request: Request):
    """Top up a USER's inference balance. Auth: user API key (Bearer) or the
    portal session cookie. Same mechanics as the advertiser top-up: mock
    backend credits immediately; stripe backend returns a Checkout URL."""
    user_email = None
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    ctype = request.headers.get("content-type", "")
    if api_key:
        u = portal.get_user_by_key(api_key)
        user_email = u["email"] if u else None
    if not user_email:
        session = _cookie(request, "guac_session")
        s_role, s_email = oauth.verify_session_cookie(session)
        if s_role == "user" and s_email:
            user_email = s_email
    if not user_email and "application/json" not in ctype:
        form = await request.form()
        u = portal.get_user_by_key((form.get("api_key") or "").strip())
        user_email = u["email"] if u else None
    if not user_email:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    if "application/json" in ctype:
        body = await request.json()
        amount_raw = body.get("amount_cents", 0)
    else:
        form = await request.form()
        amount_raw = form.get("amount_cents", 0)
    try:
        amount_cents = int(amount_raw)
    except (TypeError, ValueError):
        return JSONResponse({"error": {"message": "amount_cents must be an integer"}},
                            status_code=400)
    try:
        result = payments.create_topup(user_email, amount_cents, kind="user")
    except ValueError as e:
        return JSONResponse({"error": {"message": str(e)}}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": {"message": f"payment error: {e}"}},
                            status_code=502)
    result["balance"] = payments.balance_for(user_email)
    if "application/json" not in ctype:
        return RedirectResponse("/portal/user/dash", status_code=303)
    return result


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook endpoint: credits advertiser balance on payment success.
    Only active when the stripe backend is configured."""
    if payments.backend() != "stripe":
        return JSONResponse({"ok": True, "ignored": True})
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = payments.handle_webhook(payload, sig)
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error", "invalid")}, status_code=400)
    return JSONResponse({"ok": True})


@app.get("/advertiser/topup/success")
def topup_success(request: Request):
    """Stripe redirect target after a successful checkout. (Mock backend credits
    inline and never redirects here.)"""
    return HTMLResponse("<h2>Payment received — your balance is updated.</h2>"
                        "<p><a href='/portal'>Back to portal</a></p>")


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


def _master_key(request):
    """True iff the request carries the master gateway key (Bearer or query)."""
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    return bool(api_key) and api_key == config.GATEWAY_KEY


@app.get("/settle")
async def settle_endpoint(request: Request):
    """Operator settlement statement from the live ledger. Master-key only.
    Makes the transparent split actually visible to the operator over HTTP —
    no SSH into the box needed. Returns the settlement JSON; ?html=1 renders
    the human statement."""
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    if api_key != config.GATEWAY_KEY:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    rows = _read_ledger(config.LEDGER_FILE)
    if not rows:
        return {"period": _dt.date.today().isoformat(),
                "requests": 0, "tokens_total": 0, "ads_delivered": 0,
                "ad_revenue": 0.0, "guac_fee": 0.0, "wholesale_cost": 0.0,
                "retail_cost": 0.0, "user_paid": 0.0, "user_saving": 0.0,
                "guac_margin": 0.0, "message": "no ledger rows yet"}
    s = settlement.settle(rows)
    if request.query_params.get("html"):
        return HTMLResponse("<pre>" + settlement.render_statement(s) + "</pre>")
    return s


@app.get("/backup")
async def backup_endpoint(request: Request):
    """Operator state backup — all persistent state as one JSON bundle.
    Master-key only. Lets the operator snapshot the live volume anytime."""
    auth = request.headers.get("authorization", "")
    api_key = auth[7:] if auth.startswith("Bearer ") else ""
    if api_key != config.GATEWAY_KEY:
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
    return backup.build_bundle()


@app.get("/advertisers", response_class=HTMLResponse)
def advertisers():
    """Dedicated advertiser marketing page (the user-facing side lives at /)."""
    return portal_html.advertiser_home()


@app.get("/pitch")
def pitch():
    """The advertiser pitch, served as a styled page."""
    return _serve_doc("ADVERTISER_PITCH.md", "For advertisers")


@app.get("/terms")
def terms():
    """Terms of Service."""
    return _serve_doc("TERMS.md", "Terms of Service")


@app.get("/privacy")
def privacy():
    """Privacy Policy."""
    return _serve_doc("PRIVACY.md", "Privacy Policy")


def _serve_doc(filename: str, title: str):
    path = config.BASE / "docs" / filename
    text = path.read_text() if path.exists() else None
    return portal_html.doc_page(title, text)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Operator dashboard: impressions + clicks for both sides. Master-key only."""
    if not _master_key(request):
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)
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


def _cookie(request: Request, name: str) -> str:
    return request.cookies.get(name, "")


@app.get("/auth/login")
def auth_login(request: Request):
    """OAuth sign-in chooser. Renders provider buttons (or a note if none
    configured). `role` query param selects user vs advertiser."""
    role = request.query_params.get("role", "user")
    return portal_html.oauth_login(role, oauth.providers_configured())


@app.get("/auth/start/{provider}")
async def auth_start(request: Request, provider: str):
    """Start OAuth for a provider. `role` query param is user or advertiser.
    Sets a CSRF `oauth_state` cookie and redirects to the provider."""
    role = request.query_params.get("role", "user")
    if role not in ("user", "advertiser"):
        role = "user"
    if provider not in ("github", "google"):
        return HTMLResponse("unknown provider", status_code=400)
    if provider not in oauth.providers_configured():
        return HTMLResponse("provider not configured", status_code=400)
    state = oauth.new_state(role, provider)
    url = oauth.auth_url(provider, role, state)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie("oauth_state", state, httponly=True, samesite="lax",
                    max_age=600, secure=config.PUBLIC_HOST.startswith("https"))
    return resp


@app.get("/auth/callback")
async def auth_callback(request: Request):
    """OAuth callback: verify state, exchange code, mint session cookie, go to
    the role dashboard. The provider is recovered from the CSRF state cookie."""
    state = _cookie(request, "oauth_state")
    try:
        role, provider, _, _ = state.split("|")
    except ValueError:
        return HTMLResponse("invalid oauth state", status_code=400)
    code = request.query_params.get("code", "")
    if not code:
        return HTMLResponse("missing code", status_code=400)
    if not oauth.verify_state(state, role, provider):
        return HTMLResponse("invalid oauth state", status_code=400)
    try:
        identity = await oauth.exchange(provider, code)
    except Exception as e:
        return HTMLResponse(f"oauth error: {e}", status_code=502)
    email = identity.get("email") or ""
    if not email:
        return HTMLResponse("oauth did not return an email", status_code=400)
    # Create the account if needed (role-specific).
    if role == "user":
        if not portal.get_user_by_email(email):
            portal.create_user(email)
        user = portal.get_user_by_email(email)
    else:
        if not portal.get_advertiser(email):
            portal.create_advertiser(email)
        adv = portal.get_advertiser(email)
        user = adv
    # Mint signed session cookie + clear the oauth_state cookie.
    session = oauth.make_session_cookie(role, email)
    resp = RedirectResponse(f"/portal/{role}/dash", status_code=302)
    resp.set_cookie("guac_session", session, httponly=True, samesite="lax",
                    max_age=config.SESSION_TTL_S,
                    secure=config.PUBLIC_HOST.startswith("https"))
    resp.delete_cookie("oauth_state")
    return resp


def _user_money(email):
    """Real money numbers for the user dashboard: current balance, lifetime
    spend, and lifetime savings vs market rate — all from the ledgers."""
    balance = payments.balance_for(email)
    spent = 0.0   # what the user paid (discounted)
    market = 0.0  # what those tokens would cost at full market rate
    if config.LEDGER_FILE.exists():
        for line in config.LEDGER_FILE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("user") != email:
                continue
            bill = row.get("bill") or {}
            cost = bill.get("cost", 0.0)
            rate = bill.get("discount_rate") or 0.0
            spent += cost
            if rate and rate < 1.0:
                market += cost / (1.0 - rate)
    return balance, spent, max(market - spent, 0.0)


@app.get("/portal/{role}/dash")
def role_dashboard(request: Request, role: str):
    """Authenticated dashboard for a role, from the session cookie."""
    session = _cookie(request, "guac_session")
    s_role, email = oauth.verify_session_cookie(session)
    if s_role != role or not email:
        return RedirectResponse("/portal", status_code=302)
    if role == "user":
        user = portal.get_user_by_email(email)
        if not user:
            return RedirectResponse("/portal", status_code=302)
        balance, spent, saved = _user_money(email)
        return portal_html.user_dashboard(user, balance, spent, saved)
    adv = portal.get_advertiser(email)
    if not adv:
        return RedirectResponse("/portal", status_code=302)
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                            balance=payments.balance_for(email))


@app.post("/portal/logout")
def logout(request: Request):
    resp = RedirectResponse("/portal", status_code=302)
    resp.delete_cookie("guac_session")
    return resp


@app.get("/", response_class=HTMLResponse)
def home():
    """Marketing landing page, with the live ledger meter when there's data."""
    stats = None
    try:
        rows = _read_ledger(config.LEDGER_FILE)
        if rows:
            user_paid = sum((r.get("bill") or {}).get("cost", 0.0) for r in rows
                            if r.get("bill"))
            stats = {
                "requests": len(rows),
                "impressions": sum(1 for r in rows if r.get("sponsored")),
                "subsidized_usd": user_paid,
            }
    except Exception:
        pass
    return portal_html.marketing_home(stats)


@app.get("/favicon.svg")
def favicon():
    from fastapi.responses import Response
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           "<circle cx='50' cy='50' r='46' fill='#2f9e6e'/>"
           "<text x='50' y='66' font-size='52' font-family='Arial' font-weight='bold' "
           "text-anchor='middle' fill='white'>g</text></svg>")
    return Response(svg, media_type="image/svg+xml")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    body = """
<div class="dash" style="text-align:center">
  <h1>Page not found</h1>
  <p class="sub">That page doesn't exist — it may have moved.</p>
  <a class="btn btn-primary" href="/">Back to guac home</a>
</div>"""
    return HTMLResponse(portal_html._page("Not found", body), status_code=404)


@app.get("/portal", response_class=HTMLResponse)
def portal_landing():
    return portal_html.portal_home()


@app.post("/portal/user/login", response_class=HTMLResponse)
async def portal_user_login(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return portal_html.user_login_form(email, error="Valid email required")
    # Ensure the user exists so they can always sign back in.
    if not portal.get_user_by_email(email):
        portal.create_user(email)
    link = _magic_link_for("user", email)
    if not config.DEV_MODE:
        # Production: email the link. If email isn't configured, surface that
        # clearly rather than showing the link on screen.
        if not mailer.send_magic_link(email, link):
            return portal_html.user_login_form(
                email, error="Email delivery isn't configured yet — sign-in links "
                             "can't be sent. The portal isn't open for public sign-up.")
        return portal_html.user_login_form(email, magic_link=None, emailed=True)
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
    balance, spent, saved = _user_money(email)
    return portal_html.user_dashboard(user, balance, spent, saved)


@app.post("/portal/advertiser/login", response_class=HTMLResponse)
async def portal_advertiser_login(request: Request):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return portal_html.advertiser_login_form(email, error="Valid email required")
    if not portal.get_advertiser(email):
        portal.create_advertiser(email)
    link = _magic_link_for("advertiser", email)
    if not config.DEV_MODE:
        if not mailer.send_magic_link(email, link):
            return portal_html.advertiser_login_form(
                email, error="Email delivery isn't configured yet — sign-in links "
                             "can't be sent. The portal isn't open for public sign-up.")
        return portal_html.advertiser_login_form(email, magic_link=None, emailed=True)
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
    balance = payments.balance_for(email)
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                            balance=balance)


@app.post("/portal/advertiser/offer", response_class=HTMLResponse)
async def portal_advertiser_offer(request: Request):
    form = await request.form()
    # Auth is the advertiser TOKEN (hidden form field), never a spoofable
    # email field: anyone who knows an email could otherwise create offers
    # on someone else's account.
    adv = portal.get_advertiser_by_token((form.get("token") or "").strip())
    if not adv:
        return portal_html.advertiser_login_form(error="Not logged in")
    email = adv["email"]
    offer_type = (form.get("offer_type") or "discount").strip()
    cleaned, err = _safe_offer_fields(form.get("headline"), form.get("body"),
                                      form.get("claim"), form.get("image_url"),
                                      form.get("link"))
    if err:
        return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                                error=err,
                                                balance=payments.balance_for(email))
    budget_raw = form.get("budget")
    try:
        budget = float(budget_raw)
    except (TypeError, ValueError):
        return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                                error="Budget must be a number",
                                                balance=payments.balance_for(email))
    if not cleaned["headline"] or budget <= 0:
        return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                                error="Headline and positive budget required",
                                                balance=payments.balance_for(email))
    offer = portal.create_offer(email, cleaned["headline"], cleaned["body"], cleaned["claim"],
                                budget, offer_type, [], cleaned["image_url"], cleaned["link"])
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                            created=offer["headline"],
                                            balance=payments.balance_for(email))


@app.post("/portal/advertiser/offer/{offer_id}/toggle", response_class=HTMLResponse)
async def portal_advertiser_toggle(request: Request, offer_id: str):
    form = await request.form()
    # Token auth, same as offer creation: the form's hidden token field is
    # the advertiser credential, and the offer must belong to that advertiser.
    adv = portal.get_advertiser_by_token((form.get("token") or "").strip())
    offer = portal.get_offer(offer_id)
    if not adv or not offer or offer.get("advertiser") != adv["email"]:
        return portal_html.advertiser_login_form(error="Not authorized")
    email = adv["email"]
    portal.set_offer_paused(offer_id, not offer.get("paused", False))
    return portal_html.advertiser_dashboard(adv, portal.offer_stats_for(email),
                                            balance=payments.balance_for(email))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
