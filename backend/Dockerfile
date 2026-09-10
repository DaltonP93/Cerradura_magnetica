FROM python:3.11-slim

WORKDIR /app

# mdbtools powers the legacy iCCard3000.mdb importer
RUN apt-get update && apt-get install -y --no-install-recommends curl mdbtools && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user, never root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness check (does not depend on the database); readiness is /health/ready.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -sf http://localhost:8000/health || exit 1

# --proxy-headers makes uvicorn honour X-Forwarded-For/Proto, but ONLY from the
# trusted reverse proxy IP(s) in ACP_FORWARDED_ALLOW_IPS (default 127.0.0.1 —
# never "*", which would let any client spoof its source IP). Set it to your
# reverse proxy's address in deployment. Shell form so the env var expands.
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "${ACP_FORWARDED_ALLOW_IPS:-127.0.0.1}"
