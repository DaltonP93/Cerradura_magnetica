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

# --proxy-headers makes uvicorn honour X-Forwarded-For/Proto from the reverse
# proxy, so the client IP used for rate limiting is the real client, not nginx.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
