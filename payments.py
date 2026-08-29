"""guac payments — advertiser prepaid balance + top-up provider abstraction.

Two backends:
  - "mock"  (default): dev mode. A top-up immediately credits the advertiser's
             balance with no real money. Fully testable, no dependencies.
  - "stripe": real money. Creates a Stripe Checkout Session for a top-up; a
             webhook (checkout.session.completed) credits the balance.

The money model: an advertiser's BALANCE (prepaid, in USD) is the source of
truth. Offers draw impressions against that balance — you cannot run ads you
haven't funded. `charge_impression` in portal.py deducts from balance.
"""
import datetime as _dt
import json

import config


def backend() -> str:
    """The active payment backend ('mock' or 'stripe')."""
    if config.PAYMENTS_BACKEND == "stripe":
        if not config.STRIPE_SECRET_KEY:
            raise RuntimeError("ADGATE_PAYMENTS_BACKEND=stripe but ADGATE_STRIPE_SECRET_KEY unset")
        return "stripe"
    return "mock"


# ---------------------------------------------------------------------------
# Money ledger (top-ups + impression charges), for settlement + transparency
# ---------------------------------------------------------------------------

def log_payment(entry: dict) -> None:
    """Append a money movement to the payments ledger (atomic, serialized)."""
    row = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        **entry,
    }
    config.log_ledger_row(config.PAYMENTS_LEDGER, row)


def balance_for(entity: str) -> float:
    """Current prepaid balance (USD) for an entity (advertiser or user),
    from the ledger: top-ups + sponsor credits − inference debits."""
    bal = 0.0
    for row in _read_ledger():
        if row.get("advertiser") == entity:
            bal += row.get("delta", 0.0)
    return bal


def charge_request(user_entity: str, cost: float, note: str = "") -> bool:
    """Bill one request against the user's prepaid balance at the ALREADY-
    DISCOUNTED rate. Returns True if charged, False if the balance can't
    cover it (caller's pre-flight gate returns 402)."""
    if cost <= 0:
        return True
    if balance_for(user_entity) < cost:
        return False
    log_payment({
        "advertiser": user_entity,
        "delta": -round(cost, 8),
        "kind": "debit",
        "source": "inference",
        "note": note,
    })
    return True


def _read_ledger():
    rows = []
    if config.PAYMENTS_LEDGER.exists():
        for line in config.PAYMENTS_LEDGER.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


# ---------------------------------------------------------------------------
# Top-up
# ---------------------------------------------------------------------------

def create_topup(entity: str, amount_cents: int, kind: str = "user") -> dict:
    """Create a top-up for an advertiser OR a user. `kind` tags the money so
    settlement can separate user prepayments from advertiser ad budgets.
    Returns {session_url} (stripe) or {session_id, amount, credited: true}
    (mock, credited immediately).

    `amount_cents` is the amount in USD cents being paid.
    """
    if amount_cents < 100:  # enforce a $1 minimum
        raise ValueError("top-up must be at least $1")
    if backend() == "stripe":
        return _stripe_create_topup(entity, amount_cents, kind=kind)
    # mock: credit immediately, return a fake session id.
    session_id = "mock_session_" + entity.replace("@", "_") + "_" + str(amount_cents)
    credit_balance(entity, amount_cents, source="topup_mock",
                   note=f"mock top-up ${amount_cents/100:.2f}", entity_kind=kind)
    return {"session_id": session_id, "amount_cents": amount_cents, "credited": True}


def credit_balance(advertiser_email: str, amount_cents: int, source: str,
                   note: str = "", entity_kind: str = "") -> None:
    """Credit an advertiser's balance (positive delta). Called on confirmed payment."""
    if amount_cents <= 0:
        return
    row = {
        "advertiser": advertiser_email,
        "delta": amount_cents / 100.0,
        "kind": "credit",
        "source": source,
        "note": note,
    }
    if entity_kind:
        row["entity_kind"] = entity_kind
    log_payment(row)


def debit_balance(advertiser_email: str, amount_cents: int, source: str, note: str = "") -> None:
    """Debit an advertiser's balance (negative delta). Called per impression."""
    if amount_cents <= 0:
        return
    log_payment({
        "advertiser": advertiser_email,
        "delta": -(amount_cents / 100.0),
        "kind": "debit",
        "source": source,
        "note": note,
    })


# ---------------------------------------------------------------------------
# Stripe backend (lazy import; only when keys are set)
# ---------------------------------------------------------------------------

def _stripe_create_topup(advertiser_email: str, amount_cents: int, kind: str = "user") -> dict:
    try:
        import stripe
    except ImportError:
        raise RuntimeError("stripe package not installed; pip install stripe")
    stripe.api_key = config.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"guac ad budget — {advertiser_email}"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        success_url=config.PUBLIC_HOST.rstrip("/") + "/advertiser/topup/success",
        cancel_url=config.PUBLIC_HOST.rstrip("/") + "/portal",
        metadata={"advertiser": advertiser_email, "entity_kind": kind},
    )
    return {"session_id": session.id, "url": session.url}


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Handle a Stripe webhook event. Credits balance on
    checkout.session.completed. Returns {ok, event_type}."""
    try:
        import stripe
    except ImportError:
        raise RuntimeError("stripe package not installed; pip install stripe")
    stripe.api_key = config.STRIPE_SECRET_KEY
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    except Exception:
        return {"ok": False, "error": "invalid signature"}
    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        advertiser = sess.get("metadata", {}).get("advertiser")
        entity_kind = sess.get("metadata", {}).get("entity_kind", "")
        amount = sess.get("amount_total", 0)
        if advertiser:
            credit_balance(advertiser, amount, source="stripe",
                           note=f"stripe session {sess.get('id')}",
                           entity_kind=entity_kind)
            return {"ok": True, "event_type": event["type"], "credited": True}
    return {"ok": True, "event_type": event["type"]}
