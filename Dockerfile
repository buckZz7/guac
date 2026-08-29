# guac gateway — Fly.io deploy
# Lightweight Python image (no GPU, just proxying inference).
FROM python:3.13-slim

WORKDIR /app

# Install deps without a lockfile churn — pin the three runtime packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the guac codebase (runtime files only — no tests/stub/dev tools).
COPY config.py suppliers.py settlement.py backup.py gateway.py portal.py portal_html.py mailer.py limits.py payments.py ads.json suppliers.json ./

# Docs (advertiser pitch is served at /pitch).
COPY docs/ ./docs/

# Runtime state + ledgers live in /data (a Fly volume if attached, else container).
ENV ADGATE_STATE_FILE=/data/state.json \
    ADGATE_LEDGER_FILE=/data/ledger.jsonl \
    ADGATE_ATTRIBUTION_FILE=/data/attribution.jsonl \
    ADGATE_SUPPLIER_STATE_FILE=/data/supplier_state.json \
    ADGATE_USERS_FILE=/data/users.json \
    ADGATE_OFFERS_FILE=/data/offers.json \
    ADGATE_ADVERTISERS_FILE=/data/advertisers.json \
    ADGATE_MAGIC_USED_FILE=/data/magic_used.json \
    ADGATE_PAYMENTS_LEDGER=/data/payments.jsonl \
    ADGATE_ADS_FILE=/app/ads.json \
    ADGATE_SUPPLIERS_FILE=/app/suppliers.json \
    CHUTES_API_KEY= \
    ENGY_API_KEY= \
    OPENROUTER_API_KEY=

# Fly provides PORT; uvicorn binds it.
EXPOSE 8080
CMD ["python", "gateway.py", "--host", "0.0.0.0", "--port", "8080"]
