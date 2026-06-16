# mcp-drive

Self-built MCP sidecar exposing **read + create** access to cloud drives — OneDrive (Microsoft
Graph) and Google Drive (Drive API v3) — to the OpenClaw gateway. A second, isolated sidecar: it
holds **no mail credentials**, and each drive provider holds its own OAuth token.

**Tools (no delete, no overwrite):** `list_files`, `read_file`, `write_file` (code/text, native
extension), `create_excel`, `create_doc`, `create_folder`, `download_file` (small files, base64,
for emailing as an attachment). Every upload goes to a **non-colliding name** — the server never
overwrites or deletes; "modify" is read + create-new.

Same hardening as the mail sidecar: non-root, read-only rootfs, no published ports, egress only
through the squid proxy, bearer-auth on the HTTP endpoint. Credentials live read-only under
`instance/onedrive/` and `instance/gdrive/`, mounted only into this container.
