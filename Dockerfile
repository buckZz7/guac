# guac gateway — Fly.io deploy
# Lightweight Python image (no GPU, just proxying inference).
FROM python:3.13-slim

WORKDIR /app

# Install deps without a lockfile churn — pin the three runtime packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the guac codebase.
COPY config.py suppliers.py gateway.py portal.py daily.py stub.py ads.json suppliers.json ./

# Runtime state + ledgers live in /data (a Fly volume if attached, else container).
ENV ADGATE_STATE_FILE=/data/state.json \
    ADGATE_LEDGER_FILE=/data/ledger.jsonl \
    ADGATE_ATTRIBUTION_FILE=/data/attribution.jsonl \
    ADGATE_SUPPLIER_STATE_FILE=/data/supplier_state.json \
    ADGATE_USERS_FILE=/data/users.json \
    ADGATE_OFFERS_FILE=/data/offers.json \
    ADGATE_ADS_FILE=/app/ads.json \
    ADGATE_SUPPLIERS_FILE=/app/suppliers.json \
    CHUTES_API_KEY= \
    OPENROUTER_API_KEY=

# Fly provides PORT; uvicorn binds it.
EXPOSE 8080
CMD ["python", "gateway.py", "--host", "0.0.0.0", "--port", "8080"]
