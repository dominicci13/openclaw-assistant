# OpenClaw Assistant

A hardened, self-hosted personal assistant I run on the open-source
[OpenClaw](https://github.com/openclaw/openclaw) agent gateway — Claude is the brain, reachable
over Telegram (and locally via Claude Desktop). Built **security-first** and local-first,
structured to move to a VPS later without rewrites.

This repo doubles as a portfolio piece: how you bolt real capabilities (mail across Gmail,
Outlook, and iCloud) onto an always-on agent while **treating the model as potentially
hijackable** — least-privilege scopes, a single audited egress chokepoint, read+draft-only
tools, and prompt-injection defense in depth. The credentials it touches are the real crown
jewels, so the design optimizes for *containing a compromised model*, not just shipping features.

## Status

- **M1 — Hardened gateway:** OpenClaw in Docker (non-root, read-only rootfs, dropped caps, **zero
  published ports**); Telegram allowlisted to a single operator; all risky tool groups denied.
- **M2 — Web (read-only):** `web_search` + `web_fetch` behind a default-DENY domain allowlist.
- **M3 — Network chokepoint:** the gateway has no egress of its own; **all** outbound is forced
  through a Squid proxy (fail-closed — no proxy, no internet).
- **M4 — Mail (Gmail):** read + draft via a self-built MCP sidecar; bearer-authed; a scheduled
  morning brief over Telegram.
- **M5 — Mail (Outlook + iCloud):** one multi-provider sidecar, three accounts, read+draft only;
  also wired to Claude Desktop over stdio.
- **Planned:** send-with-consent (per-send confirmation) → Drive (OneDrive + Google Drive) → VPS.

## Security model

- **Containment.** Docker, non-root, read-only rootfs, dropped capabilities, no host Docker
  socket, zero published ports (Telegram long-polls outbound; nothing dials in).
- **One audited egress chokepoint.** The gateway lives on an `internal` Docker network with no
  route out; a Squid proxy enforces a **default-DENY domain allowlist** and is the only path to
  the internet. The egress log is the audit trail.
- **Least privilege.** Tools are denied by default; only a minimal set is enabled (read-only web,
  read+draft mail). Shell/exec, filesystem, and automation groups stay denied.
- **Prompt-injection defense in depth.** (1) system-prompt rule — ingested content (emails, web
  pages) is *data, never instructions*; (2) structural tagging of untrusted content; (3)
  code-enforced gates — a hijacked model has no send/delete tool to call and can't reach
  off-allowlist domains. Layer 3 is the actual boundary.
- **Secrets isolation.** Provider credentials live only inside the hardened mail sidecar, never
  in the gateway; injected via environment, never committed.

## Mail safety

Mail is **read + draft only** — no send tool, no delete tool exists. How that's enforced per
provider:

| Account | No send | No delete |
|---|---|---|
| Gmail | tool layer (`compose` can send; no send tool) | **token** (`readonly`+`compose`; delete → 403) |
| Outlook | **token** (no `Mail.Send` scope; `sendMail` → 403) | tool layer (no delete tool) |
| iCloud | tool layer (no SMTP code) | tool layer (no delete/expunge code) |

Drafts wait in the account's Drafts folder for the human to review and send.

## Architecture

```
Telegram ──► openclaw-gateway ──(MCP, bearer auth)──► openclaw-mail sidecar ──┐
 (you)        (the agent / Claude)                     (Gmail · Outlook · iCloud)
                     │                                                        │
                     └──────────── all egress ──────► openclaw-proxy (Squid) ─┘
                                                       default-DENY allowlist ──► internet
```

- **openclaw-gateway** — the OpenClaw agent (Claude). Holds no mail credentials.
- **openclaw-proxy** — Squid; the sole route out; default-DENY allowlist + audit log.
- **mail sidecar (`mcp-mail/`)** — a self-built Python MCP server exposing three account-aware
  tools (`search_messages`, `get_message`, `create_draft`) across Gmail, Outlook, and iCloud.
  Reachable over HTTP (bearer-authed) for the gateway, and over stdio for Claude Desktop.

## Quick start

Requires Docker. Secrets are supplied via untracked `.env` files (templates provided):

```bash
cp .env.example .env                                # root: GMAIL_MCP_BEARER_TOKEN
cp instance/config/.env.example instance/config/.env # gateway: telegram/anthropic/tavily/gateway token
cp instance/config/openclaw.json.example instance/config/openclaw.json  # set your Telegram user id

# Per-account mail credentials (sidecar-only), one-time consent:
#   instance/gmail/    Google OAuth client + token   (python mcp-mail/auth.py)
#   instance/outlook/  Azure app config + device-code token (python mcp-mail/auth_outlook.py)
#   instance/icloud/   email + app-specific password (config.json)

docker compose up -d        # gateway + squid proxy + mail sidecar
```

## Layout

| Path | Role |
|---|---|
| `docker-compose.yml` | Gateway + Squid proxy + mail sidecar; the hardening lives here |
| `proxy/squid.conf` · `proxy/allowlist.txt` | Egress chokepoint: config + default-DENY allowlist |
| `mcp-mail/main.py` | MCP server: bearer middleware + 3 account-aware tool dispatchers |
| `mcp-mail/providers/` | Per-provider backends: `gmail.py`, `outlook.py`, `icloud.py` |
| `mcp-mail/auth.py` · `auth_outlook.py` | OAuth mint/refresh (Google, Microsoft device-code) |
| `instance/config/openclaw.json.example` | The hardened gateway config (sanitized) |

Live credentials, tokens, logs, the agent workspace, and the upstream OpenClaw clone are **not**
tracked (see `.gitignore`).

## Author
Built by **Brian Ramírez** ([@dominicci13](https://github.com/dominicci13)) — automation & AI workflow specialist. More on my [GitHub profile](https://github.com/dominicci13) and [LinkedIn](https://linkedin.com/in/bdramirez).
