# ── Builder stage ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────────
FROM python:3.12-slim

# Security: non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# Create cache directory
RUN mkdir -p /tmp/barbican-ui-cache && chown appuser:appuser /tmp/barbican-ui-cache

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

# Run with gunicorn
ENTRYPOINT ["gunicorn"]
CMD [ \
  "--bind", "0.0.0.0:8080", \
  "--workers", "4", \
  "--timeout", "120", \
  "--access-logfile", "-", \
  "--error-logfile", "-", \
  "--forwarded-allow-ips", "*", \
  "app:create_app()" \
]

