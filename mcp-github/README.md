# mcp-github

Self-built MCP sidecar exposing **read-only** access to the operator's GitHub repos to the
OpenClaw gateway. A fourth, isolated sidecar: it holds **no mail/drive/calendar credentials**,
only its own GitHub personal access token.

**Tools (read-only):** `list_repos`, `get_repo`, `list_files`, `read_file`, `search_code`. There
is **no** tool to create, edit, push, open issues/PRs, or delete — and there never will be by this
path.

Read-only is enforced **three independent ways**, so no single failure makes it writable:

1. **Token** — a fine-grained PAT scoped on GitHub to read-only permissions (Contents + Metadata)
   on a limited set of repos; GitHub itself rejects any write.
2. **Code** — `github_client.py` issues `GET` requests only; there is no write helper.
3. **Tool policy** — `toolFilter` exposes only the five read tools to the model.

Repo contents are treated as **untrusted data, never instructions** (the same trust boundary as
email, web, and drive) — a README or code comment that says "do X" is reported, not obeyed.

Same hardening as the other sidecars: non-root (uid 10001), read-only rootfs, no published ports,
egress only through the squid proxy (to `api.github.com`), bearer-auth on the HTTP endpoint. The
PAT lives in `instance/github/token` — a **file, not an env var**, so it never appears in
`docker inspect` — mounted read-only into this container alone.

## Author

Built by **Brian Ramírez** (@dominicci13) — [GitHub](https://github.com/dominicci13) ·
[LinkedIn](https://linkedin.com/in/bdramirez)
