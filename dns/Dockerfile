# Minimal DNS forwarder. Lets the hardened gateway RESOLVE names (required by
# OpenClaw's browser-navigation SSRF pin) WITHOUT granting it egress: the gateway
# still routes only through squid. Every query is forwarded to Docker's embedded
# resolver (127.0.0.11), which resolves internal service names locally AND - because
# this container is also on the egress net - forwards external names upstream.
# Same Debian base + digest as the browser sidecar (shared Scout posture).
FROM debian:trixie-slim@sha256:4e401d95de7083948053197a9c3913343cd06b706bf15eb6a0c3ccd26f436a0e

ENV DEBIAN_FRONTEND=noninteractive

# dnsmasq = the forwarder; dnsutils (host) = the healthcheck probe only.
RUN apt-get update \
 && apt-get install -y --no-install-recommends dnsmasq dnsutils \
 && rm -rf /var/lib/apt/lists/*

COPY dnsmasq.conf /etc/dnsmasq.conf

EXPOSE 53/udp 53/tcp

# dnsmasq binds :53 (needs NET_BIND_SERVICE) then drops from root to its own
# unprivileged user (needs SETUID/SETGID) - all granted in compose. Foreground so
# Docker manages it; log to stderr (-) so startup/warnings show in `docker logs`.
ENTRYPOINT ["dnsmasq", "--keep-in-foreground", "--log-facility=-", "--conf-file=/etc/dnsmasq.conf"]
