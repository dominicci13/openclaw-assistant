# mcp-drive

Self-built MCP sidecar exposing **read + create** access to cloud drives — OneDrive
(Microsoft Graph) now, Google Drive later — to the OpenClaw gateway. A second, isolated sidecar:
it holds **no mail credentials**, only its own per-drive OAuth tokens.

**Tools (no delete, no overwrite):** `list_files`, `read_file`, `write_file` (code/text, native
extension), `create_excel`, `create_doc`. Every upload goes to a **non-colliding name** — the
server never overwrites or deletes; "modify" is read + create-new.

Same hardening as the mail sidecar: non-root, read-only rootfs, no published ports, egress only
through the squid proxy, bearer-auth on the HTTP endpoint. Credentials live read-only under
`instance/onedrive/` (and later `instance/gdrive/`), mounted only into this container.
