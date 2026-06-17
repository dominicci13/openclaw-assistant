#!/usr/bin/env bash
# Launch headless Chromium (loopback CDP, all egress via squid) and front it with
# an auth + source-range relay. Fail closed: no auth token -> the container exits.
set -Eeuo pipefail

CDP_PORT="${BROWSER_CDP_PORT:?BROWSER_CDP_PORT unset}"                       # relay listen (network)
CHROME_CDP_PORT="${BROWSER_CHROME_CDP_PORT:?BROWSER_CHROME_CDP_PORT unset}"  # chromium loopback
PROXY_URL="${BROWSER_PROXY_URL:?BROWSER_PROXY_URL unset}"                    # squid egress chokepoint
AUTH_TOKEN="${OPENCLAW_BROWSER_CDP_AUTH_TOKEN:?refusing to start without a CDP auth token}"
SOURCE_RANGE="${OPENCLAW_BROWSER_CDP_SOURCE_RANGE:-}"                        # optional IP allowlist (gateway only)

# Writable, ephemeral profile + caches on tmpfs (rootfs is read-only at runtime).
export HOME=/tmp/chromium-home
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
mkdir -p "$HOME" /tmp/chromium-profile

# Chromium: loopback CDP only, every page fetch through squid, locked-down flags.
chromium \
  --headless=new \
  --no-sandbox --disable-setuid-sandbox \
  --proxy-server="$PROXY_URL" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$CHROME_CDP_PORT" \
  --user-data-dir=/tmp/chromium-profile \
  --no-first-run --no-default-browser-check \
  --no-zygote \
  --disable-gpu --disable-software-rasterizer \
  --disable-dev-shm-usage \
  --disable-extensions \
  --disable-background-networking \
  --disable-breakpad --disable-crash-reporter \
  --metrics-recording-only \
  --password-store=basic --use-mock-keychain \
  about:blank &
CHROME_PID=$!

# Wait for Chromium's CDP to answer on loopback before exposing the relay.
echo "[browser] waiting for Chromium CDP on 127.0.0.1:${CHROME_CDP_PORT}..."
for _ in $(seq 1 60); do
  kill -0 "$CHROME_PID" 2>/dev/null || { echo "[browser] Chromium exited early"; exit 1; }
  if curl -fsS --max-time 0.5 "http://127.0.0.1:${CHROME_CDP_PORT}/json/version" >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 0.25
done
[ "${READY:-0}" = "1" ] || { echo "[browser] CDP not ready in time"; exit 1; }
echo "[browser] CDP ready; starting relay on 0.0.0.0:${CDP_PORT}"

# --- Relay: from OpenClaw's sandbox-browser entrypoint, ONE deliberate change. ---
# stdlib-only TCP relay; enforces source-range IP allowlist + constant-time
# Basic/Bearer token auth, then forwards to Chromium's loopback CDP.
# OUR EDIT vs upstream: rewrite_host() below rewrites the forwarded Host header to
# loopback so Chrome's DNS-rebinding guard accepts requests the gateway sends by
# service name (proven: a DNS-name Host -> HTTP 500). Auth + source-range logic
# are untouched; only the Host line is changed, AFTER both checks pass.
OPENCLAW_BROWSER_CDP_PORT="$CDP_PORT" \
OPENCLAW_BROWSER_CHROME_CDP_PORT="$CHROME_CDP_PORT" \
OPENCLAW_BROWSER_CDP_AUTH_TOKEN="$AUTH_TOKEN" \
OPENCLAW_BROWSER_CDP_SOURCE_RANGE="$SOURCE_RANGE" \
python3 - <<'PY' &
import base64
import hmac
import ipaddress
import os
import select
import socket
import socketserver
import sys
import time

LISTEN_PORT = int(os.environ["OPENCLAW_BROWSER_CDP_PORT"])
UPSTREAM_PORT = int(os.environ["OPENCLAW_BROWSER_CHROME_CDP_PORT"])
AUTH_TOKEN = os.environ["OPENCLAW_BROWSER_CDP_AUTH_TOKEN"]
SOURCE_RANGE = os.environ.get("OPENCLAW_BROWSER_CDP_SOURCE_RANGE", "").strip()
MAX_HEADER_BYTES = 65536
HEADER_READ_TIMEOUT_SECONDS = 5.0

try:
    SOURCE_NETWORK = ipaddress.ip_network(SOURCE_RANGE, strict=False) if SOURCE_RANGE else None
except ValueError:
    print(f"[sandbox-browser] ERROR: invalid CDP source range: {SOURCE_RANGE}", file=sys.stderr)
    raise SystemExit(1)

EXPECTED_BASIC = "Basic " + base64.b64encode(f"openclaw:{AUTH_TOKEN}".encode()).decode()
EXPECTED_BEARER = "Bearer " + AUTH_TOKEN
UPSTREAM_HOST_HEADER = f"127.0.0.1:{UPSTREAM_PORT}"


def source_allowed(host):
    if SOURCE_NETWORK is None:
        return True
    try:
        return ipaddress.ip_address(host) in SOURCE_NETWORK
    except ValueError:
        return False


def has_auth(header_bytes):
    try:
        text = header_bytes.decode("iso-8859-1")
    except UnicodeDecodeError:
        return False
    for line in text.split("\r\n")[1:]:
        name, sep, value = line.partition(":")
        if sep and name.strip().lower() == "authorization":
            auth = value.strip()
            basic_ok = hmac.compare_digest(auth, EXPECTED_BASIC)
            bearer_ok = hmac.compare_digest(auth, EXPECTED_BEARER)
            return basic_ok or bearer_ok
    return False


def read_headers(conn, deadline):
    data = b""
    while b"\r\n\r\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return b""
        conn.settimeout(remaining)
        try:
            chunk = conn.recv(4096)
        except socket.timeout:
            return b""
        if not chunk:
            return b""
        data += chunk
        if len(data) > MAX_HEADER_BYTES:
            return b""
    return data


def relay(left, right):
    sockets = [left, right]
    try:
        while sockets:
            readable, _, _ = select.select(sockets, [], [])
            for src in readable:
                dst = right if src is left else left
                data = src.recv(65536)
                if not data:
                    return
                dst.sendall(data)
    finally:
        for sock in (left, right):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


def rewrite_host(header_bytes):
    # OUR ADDITION: replace the Host header with loopback:chrome-port so Chrome's
    # DevTools DNS-rebinding guard accepts requests the gateway addresses by
    # service name. Runs only after auth + source-range have passed. Only the
    # header block is touched; any already-read body bytes are preserved as-is.
    sep = b"\r\n\r\n"
    idx = header_bytes.find(sep)
    if idx == -1:
        return header_bytes
    head = header_bytes[:idx].decode("iso-8859-1")
    rest = header_bytes[idx:]
    lines = head.split("\r\n")
    out = []
    replaced = False
    for i, line in enumerate(lines):
        if i == 0:
            out.append(line)  # request line, never touched
            continue
        name, field_sep, _ = line.partition(":")
        if field_sep and name.strip().lower() == "host":
            out.append(f"Host: {UPSTREAM_HOST_HEADER}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.insert(1, f"Host: {UPSTREAM_HOST_HEADER}")
    return "\r\n".join(out).encode("iso-8859-1") + rest


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        client_host = self.client_address[0]
        if not source_allowed(client_host):
            return
        header_deadline = time.monotonic() + HEADER_READ_TIMEOUT_SECONDS
        header_bytes = read_headers(self.request, header_deadline)
        if not header_bytes:
            return
        if not has_auth(header_bytes):
            self.request.sendall(
                b"HTTP/1.1 401 Unauthorized\r\n"
                b'WWW-Authenticate: Basic realm="OpenClaw CDP"\r\n'
                b"Connection: close\r\n"
                b"Content-Length: 0\r\n\r\n"
            )
            return
        upstream = socket.create_connection(("127.0.0.1", UPSTREAM_PORT), timeout=5)
        upstream.settimeout(None)
        self.request.settimeout(None)
        upstream.sendall(rewrite_host(header_bytes))
        relay(self.request, upstream)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(("0.0.0.0", LISTEN_PORT), Handler) as server:
    print("[browser] CDP relay started", flush=True)
    server.serve_forever()
PY
RELAY_PID=$!

# If Chromium or the relay dies, exit non-zero so Docker's restart policy
# recreates a clean pair (a half-dead sidecar is worse than a restart).
wait -n "$CHROME_PID" "$RELAY_PID"
echo "[browser] a child exited; shutting down"
kill "$CHROME_PID" "$RELAY_PID" 2>/dev/null || true
exit 1
