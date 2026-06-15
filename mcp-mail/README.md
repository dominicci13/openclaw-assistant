# mcp-gmail

A least-privilege Gmail MCP server: **read + draft only**. Exposes three tools —
`search_messages`, `get_message`, `create_draft`. Send, delete, and modify are
not implemented, and the OAuth token (`gmail.readonly` + `gmail.compose`) could
not perform them anyway. Two independent walls, one decision.

## Transports

- **stdio** (default) — client spawns the server as a subprocess. Used by
  Claude Desktop on macOS. Zero network, zero ports.
- **streamable-http** (`MCP_TRANSPORT=streamable-http`) — used by the
  containerized sidecar that serves the OpenClaw gateway over the internal
  Docker network.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python auth.py        # one-time browser consent; mints token.json
.venv/bin/python main.py        # run the server (stdio)
```

Secrets live outside this folder in `instance/gmail/` (`client_secret.json`,
`token.json`), overridable via `GMAIL_SECRETS_DIR`.

## Author

- GitHub: [github.com/dominicci13](https://github.com/dominicci13)
- LinkedIn: [linkedin.com/in/bdramirez](https://linkedin.com/in/bdramirez)
