# Pinned by digest (like the gateway + squid). Refresh deliberately at audit time.
FROM python:3.13-slim@sha256:f82c96458eedc847b233e582eb31336f4954b39cae020b6dcf5b3ed0e5cbcd74

# Non-root from the start: create an unprivileged user, own only what we need.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# Install deps first (layer caching), then code. requirements.txt pins versions.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY auth.py auth_outlook.py main.py ./
COPY providers ./providers

USER appuser
ENV MCP_TRANSPORT=streamable-http \
    GMAIL_SECRETS_DIR=/secrets \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# Documents the port; publishing is still controlled by compose (we won't).
EXPOSE 8000

CMD ["python", "main.py"]