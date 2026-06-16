# mcp-calendar

Self-built MCP sidecar exposing **read + create + update** access to calendars — Google Calendar
now, Outlook (Microsoft Graph) and iCloud (CalDAV) later — to the OpenClaw gateway. A third,
isolated sidecar: it holds **no mail or drive credentials**, only its own per-calendar OAuth
tokens / app password.

**Tools (no delete, no external invites):** `list_events`, `create_event`, `update_event`. Events
are created/updated on the user's own calendar only — **no attendees**, and both create and update
set `sendUpdates="none"` so **no notification email is ever sent** (zero outbound). Update edits an
event in place (e.g. fix a wrong date); there is no delete tool.

Same hardening as the mail/drive sidecars: non-root, read-only rootfs, no published ports, egress
only through the squid proxy, bearer-auth on the HTTP endpoint. Credentials live read-only under
`instance/gcal/` (and later `instance/mscal/`, `instance/icloudcal/`), mounted only into this
container.

## Author

Built by **Brian Ramírez** (@dominicci13) — [GitHub](https://github.com/dominicci13) ·
[LinkedIn](https://linkedin.com/in/bdramirez)
