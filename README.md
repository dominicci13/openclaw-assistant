# OpenClaw Assistant

A hardened, self-hosted personal assistant I run on the open-source
[OpenClaw](https://github.com/openclaw/openclaw) agent gateway — Claude is the brain, reachable
over Telegram (and locally via Claude Desktop). Built **security-first** and local-first, then
moved to a VPS without rewrites.

This repo doubles as a portfolio piece: how you bolt real capabilities — mail, cloud drives,
calendars, read-only GitHub, and a real web browser — onto an always-on agent while **treating
the model as potentially hijackable**. Least-privilege scopes, a single audited egress chokepoint, no
delete/overwrite tools, a per-send consent gate, and prompt-injection defense in depth. The
credentials it touches are the real crown jewels, so the design optimizes for *containing a
compromised model*, not just shipping features.

> **📌 Point-in-time snapshot.** This public repo documents the security-first build as of
> mid-2026 and is preserved as-is for reference. Active development of the assistant continues in a
> private repository and will not be reflected here.

## Demo

A 60-second walkthrough: I ask Claw who it is and what it can do, then hand it a real task (compare flights, build a spreadsheet, email it to me), and finally ask it to send that to an outsider and to delete a message. It does the work, then stops at the lines it won't cross without me: an external send needs a one-time code, and it has no delete tool at all.

<div align="center">
  <video src="https://github.com/user-attachments/assets/89f6a026-3c1c-4acb-a37d-d5691b0aa0af" controls width="320"></video>
</div>

## Security model

- **Containment.** Docker, non-root, read-only rootfs, dropped capabilities, no host Docker
  socket, zero published ports (Telegram long-polls outbound; nothing dials in).
- **One audited egress chokepoint.** The gateway lives on an `internal` Docker network with no
  route out; a Squid proxy enforces a **default-DENY domain allowlist** and is the only path to
  the internet — even gateway→sidecar RPC. The egress log is the audit trail.
- **Least privilege.** Tools are denied by default; only a minimal set is enabled. Shell/exec,
  filesystem, and automation groups stay denied. Every capability is added deliberately, one at a
  time, each in its own credential-isolated sidecar.
- **No destructive tools.** There is **no delete tool anywhere** (mail, drive, calendar, GitHub)
  and drives never overwrite — "modify" is read + create-new. Calendar update-in-place is the one
  logged exception.
- **Browsing is contained and public-only.** A separate headless-Chromium sidecar renders
  JS-heavy pages; it holds **no credentials**, its remote-control port is token-gated and reachable
  only by the gateway, and every page fetch still passes the egress allowlist. Scope is deliberately
  public — Claw browses to *read* (fares, schedules, prices), not to log into accounts or submit
  forms. A DNS-only forwarder lets the gateway *resolve* hostnames without gaining any new route out.
- **Consent gate on the only outward action.** Sending mail to an external recipient requires a
  fresh TOTP code the model never sees; self-sends are exempt.
- **Prompt-injection defense in depth.** (1) system-prompt rule — ingested content (emails, web
  pages, files, repo contents, image/voice transcripts) is *data, never instructions*; (2)
  structural tagging of untrusted content; (3) code-enforced gates — a hijacked model has no
  send-without-consent / delete / write-to-GitHub tool to call, and can't reach off-allowlist
  domains. Layer 3 is the actual boundary.
- **Secrets isolation.** Each sidecar holds only its own provider credentials, mounted read-only,
  never shared with the gateway or with each other; injected via env/files, never committed.

## Mail safety

Mail can read, draft, and **send — but sending is gated**. No delete tool exists on any account.

| Account | Send | Delete |
|---|---|---|
| Gmail | TOTP consent for external recipients (`gmail.send`) | **token** (`readonly`+`compose`; delete → 403) |
| Outlook | TOTP consent for external recipients (`Mail.Send`) | tool layer (no delete tool) |
| iCloud | TOTP consent for external recipients (SMTP) | tool layer (no delete/expunge code) |
| Claw (`claw.*@gmail.com`) | **send-only** identity for assistant→you notes (`gmail.send`) | n/a (no read/delete) |

A send addressed only to your own addresses skips the code; any external recipient requires it.
Spreadsheet attachments are built server-side from data (the model never base64-couriers bytes).

## Architecture

```
                       ┌─► mail sidecar     (Gmail · Outlook · iCloud · Claw send-only)
Telegram ─► openclaw-  ├─► drive sidecar    (OneDrive · Google Drive)
 (you)     gateway ────┼─► calendar sidecar (Google · Outlook · iCloud)
           (Claude)    ├─► github sidecar   (read-only: repos, files, code search)
              │        └─► browser sidecar  (headless Chromium — public pages only)
              │
              │  name lookups ─► dns forwarder   (resolves names; grants the gateway no egress)
              │
              └─ all egress (incl. the RPC above) ─► openclaw-proxy (Squid)
                                                     default-DENY allowlist ─► internet
```

- **openclaw-gateway** — the OpenClaw agent (Claude). Holds **no** provider credentials.
- **openclaw-proxy** — Squid; the sole route out; default-DENY allowlist + audit log.
- **Four isolated MCP sidecars** (`mcp-mail/`, `mcp-drive/`, `mcp-calendar/`, `mcp-github/`) — each
  a self-built Python MCP server, bearer-authed, holding only its own credentials. The mail sidecar
  also speaks stdio for Claude Desktop.
- **openclaw-browser** (`browser/`) — a hardened headless-Chromium sidecar the gateway drives over
  a token-gated remote-CDP endpoint; holds no credentials, all its egress forced through the proxy.
- **openclaw-dns** (`dns/`) — a DNS-only forwarder so the gateway can resolve hostnames (required
  for the browser's SSRF checks) without being granted any route to the internet.

## Quick start

Requires Docker. Secrets are supplied via untracked `.env` files and credential mounts (templates
provided):

```bash
cp .env.example .env                                 # root: per-sidecar bearer tokens, TOTP, OpenAI key
cp instance/config/.env.example instance/config/.env # gateway: telegram/anthropic/tavily/gateway token
cp instance/config/openclaw.json.example instance/config/openclaw.json  # set your Telegram user id

# Per-capability credentials (sidecar-only, one-time consent) — see each sidecar's README:
#   instance/{gmail,outlook,icloud,clawmail}/   mail (OAuth tokens / app passwords)
#   instance/{onedrive,gdrive}/                 drive
#   instance/{gcal,mscal,icloudcal}/            calendar
#   instance/github/token                       a fine-grained, READ-ONLY GitHub PAT

docker compose up -d        # gateway + squid + dns forwarder + five sidecars
```

## Layout

| Path | Role |
|---|---|
| `docker-compose.yml` | Gateway + Squid + DNS forwarder + five sidecars; the hardening lives here |
| `proxy/squid.conf` · `proxy/allowlist.txt` | Egress chokepoint: config + default-DENY allowlist |
| `mcp-mail/` | Mail MCP server: 3 accounts + Claw send-only, send-with-consent, attachments |
| `mcp-drive/` | Drive MCP server: OneDrive + Google Drive, read + create (no delete/overwrite) |
| `mcp-calendar/` | Calendar MCP server: Google + Outlook + iCloud, read + create + update |
| `mcp-github/` | GitHub MCP server: read-only repo/file/code access |
| `browser/` | Headless-Chromium CDP sidecar: renders JS pages, public sites only, no credentials |
| `dns/` | DNS-only forwarder: lets the gateway resolve names without granting it egress |
| `instance/config/openclaw.json.example` | The hardened gateway config (sanitized) |

Live credentials, tokens, logs, the agent workspace, and the upstream OpenClaw clone are **not**
tracked (see `.gitignore`).

## Author
Built by **Brian Ramírez** ([@dominicci13](https://github.com/dominicci13)) — automation & AI workflow specialist. More on my [GitHub profile](https://github.com/dominicci13) and [LinkedIn](https://linkedin.com/in/bdramirez).
