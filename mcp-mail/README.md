# mcp-mail

A least-privilege, multi-provider mail MCP server: **Gmail, Outlook, and iCloud**, plus a
**send-only Claw identity** for assistant→you notes. Every tool takes an `account`.

**Tools:** `search_messages`, `get_message`, `create_draft`, `send_mail`. There is **no delete
tool** on any account.

## Sending is gated (send-with-consent)

`send_mail` to any **external** recipient requires a fresh **TOTP code** the model never sees;
a send addressed only to the operator's own addresses (`OWN_EMAIL_ADDRESSES`) skips the code.
The Claw identity (`gmail.send` scope) is **send-only** — it cannot read, search, or delete, and
is used for one-way assistant notifications so they don't clutter the operator's own Sent/Inbox.

Spreadsheet attachments are built **server-side** from row data (`send_mail`'s `excel_attachments`),
so the model never has to base64-courier bytes through its context.

Incoming timestamps are normalized to the operator's local zone (`timeutil.to_local`, default
`America/Santo_Domingo`) regardless of whether the provider returned UTC or a sender offset.

| Account | Send | Delete |
|---|---|---|
| Gmail | TOTP consent for external (`gmail.send`) | **token** (`readonly`+`compose`; delete → 403) |
| Outlook | TOTP consent for external (`Mail.Send`) | tool layer (no delete code) |
| iCloud | TOTP consent for external (SMTP STARTTLS) | tool layer (no delete/expunge code) |
| Claw | **send-only** (`gmail.send`); read/search/draft refused | n/a |

## Transports

- **stdio** (default) — client spawns the server as a subprocess (Claude Desktop on macOS). Zero
  network, zero ports.
- **streamable-http** (`MCP_TRANSPORT=streamable-http`) — the containerized sidecar serving the
  OpenClaw gateway over the internal Docker network, bearer-authed.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python auth.py          # Gmail: one-time browser consent → token.json
.venv/bin/python auth_outlook.py  # Outlook: device-code consent
.venv/bin/python auth_claw.py     # Claw send-only identity (gmail.send)
.venv/bin/python main.py          # run the server (stdio)
```

Secrets live outside this folder, mounted read-only and overridable via env:
`instance/gmail/` (`GMAIL_SECRETS_DIR`), `instance/outlook/` (`OUTLOOK_SECRETS_DIR`),
`instance/icloud/` (`ICLOUD_SECRETS_DIR`), `instance/clawmail/` (`CLAW_SECRETS_DIR`). The TOTP
secret and the operator's own-address list come from the environment (`SEND_TOTP_SECRET`,
`OWN_EMAIL_ADDRESSES`); the model never sees them.

## Author

- GitHub: [github.com/dominicci13](https://github.com/dominicci13)
- LinkedIn: [linkedin.com/in/bdramirez](https://linkedin.com/in/bdramirez)
