# Hardened headless-Chromium CDP sidecar for OpenClaw's remote-browser plugin.
# Public, read-mostly automation only: NO credentials, NO secret mounts.
# Chromium binds loopback; a stdlib Python relay (token auth + source-range) is
# the only thing on the network. ALL page egress is forced through squid by the
# entrypoint. Pinned by digest like our other images; refresh at audit time.
FROM debian:trixie-slim@sha256:4e401d95de7083948053197a9c3913343cd06b706bf15eb6a0c3ccd26f436a0e

ENV DEBIAN_FRONTEND=noninteractive

# chromium = the browser; python3 = the CDP relay (stdlib only, no pip);
# curl = the loopback CDP readiness probe + healthcheck; fonts so pages render
# text; tini = PID 1 to reap Chromium's children; ca-certificates for TLS.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium \
      python3 \
      curl \
      ca-certificates \
      fonts-liberation \
      tini \
 && rm -rf /var/lib/apt/lists/*

# Non-root from the start (uid 10001 = the appuser convention across our sidecars
# and the VPS chown rules).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0555 /usr/local/bin/entrypoint.sh

USER appuser

# Relay listens on BROWSER_CDP_PORT (the only network-facing port); Chromium's own
# CDP sits on the loopback port and is never exposed. Both fixed so the
# healthcheck can probe. Proxy = our squid egress chokepoint.
ENV BROWSER_CDP_PORT=18792 \
    BROWSER_CHROME_CDP_PORT=18793 \
    BROWSER_PROXY_URL=http://openclaw-proxy:3128

EXPOSE 18792

# Liveness = Chromium's loopback CDP answering. Dependency-free and tokenless;
# the relay's auth is exercised by the real gateway path in step 2.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${BROWSER_CHROME_CDP_PORT}/json/version" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
