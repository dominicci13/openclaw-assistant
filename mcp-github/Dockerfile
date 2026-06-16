# Pinned by digest (like the gateway + squid + other sidecars). Refresh at audit time.
FROM python:3.13-slim@sha256:f82c96458eedc847b233e582eb31336f4954b39cae020b6dcf5b3ed0e5cbcd74

# Non-root from the start: an unprivileged user owns only what we need.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# Deps first (layer caching), then code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY github_client.py main.py ./

USER appuser
ENV MCP_TRANSPORT=streamable-http \
    GITHUB_SECRETS_DIR=/secrets-github \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]
