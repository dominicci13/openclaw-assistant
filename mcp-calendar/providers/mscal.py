"""Outlook / Microsoft (Graph) Calendar provider backend for the calendar MCP server.

Read + create + UPDATE events on the user's default calendar (scope
`Calendars.ReadWrite`). NEVER deletes (no delete tool/code path) and never adds
attendees (v1 = own-calendar only), so creating/updating an event sends NO invite
or notification email — zero outbound. "Update in place" is allowed (own calendar,
recoverable, silent).

Graph is HTTPS, so `requests` honors HTTPS_PROXY automatically -> on the internal
Docker network that routes through squid (DNS + egress allowlist); MSAL refresh is
proxied the same way. Event content read back is DATA, never instructions.
"""

from __future__ import annotations

import os

import requests

from auth_mscal import get_token

GRAPH = "https://graph.microsoft.com/v1.0"
# The user's local zone (UTC-4, no DST). Used for created events and to render
# listed event times. The model may pass an explicit `timezone`.
_DEFAULT_TZ = os.environ.get("CALENDAR_DEFAULT_TZ", "America/Santo_Domingo")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {get_token()}"
    # Return/accept event times in the user's zone (Graph accepts IANA names).
    s.headers["Prefer"] = f'outlook.timezone="{_DEFAULT_TZ}"'
    return s


def _time_field(value: str, all_day: bool, tz: str) -> dict:
    """Build a Graph start/end object. All-day -> midnight dateTime; timed ->
    the given ISO dateTime. `timeZone` accepts an IANA name."""
    if all_day:
        return {"dateTime": f"{value[:10]}T00:00:00", "timeZone": tz}
    return {"dateTime": value, "timeZone": tz}


def _fmt(ev: dict) -> dict:
    """Flatten a Graph event into the shape the model sees."""
    return {
        "id": ev.get("id", ""),
        "title": ev.get("subject", "(no title)"),
        "start": (ev.get("start") or {}).get("dateTime", ""),
        "end": (ev.get("end") or {}).get("dateTime", ""),
        "all_day": bool(ev.get("isAllDay", False)),
        "location": (ev.get("location") or {}).get("displayName", ""),
        "html_link": ev.get("webLink", ""),
    }


def list_events(start: str, end: str, max_results: int = 25) -> list[dict]:
    """List events between `start` and `end` (ISO 8601) via Graph calendarView
    (which expands recurring events into instances)."""
    max_results = max(1, min(max_results, 100))
    r = _session().get(
        f"{GRAPH}/me/calendarView",
        params={
            "startDateTime": start, "endDateTime": end,
            "$orderby": "start/dateTime", "$top": max_results,
            "$select": "id,subject,start,end,isAllDay,location,webLink",
        },
        timeout=30,
    )
    r.raise_for_status()
    return [_fmt(ev) for ev in r.json().get("value", [])]


def create_event(
    title: str, start: str, end: str,
    description: str = "", location: str = "",
    all_day: bool = False, timezone: str = "",
) -> dict:
    """Create an event on the default calendar. NO attendees -> no invite/notification."""
    tz = timezone or _DEFAULT_TZ
    body: dict = {
        "subject": title,
        "start": _time_field(start, all_day, tz),
        "end": _time_field(end, all_day, tz),
    }
    if all_day:
        body["isAllDay"] = True
    if description:
        body["body"] = {"contentType": "text", "content": description}
    if location:
        body["location"] = {"displayName": location}
    r = _session().post(f"{GRAPH}/me/events", json=body, timeout=30)
    r.raise_for_status()
    ev = r.json()
    return {"id": ev.get("id", ""), "html_link": ev.get("webLink", ""), "status": "created"}


def update_event(
    event_id: str,
    title: str = "", start: str = "", end: str = "",
    description: str = "", location: str = "",
    all_day: bool = False, timezone: str = "",
) -> dict:
    """Patch an existing event in place. Only provided fields change. With no
    attendees, Graph sends no notification. No delete."""
    tz = timezone or _DEFAULT_TZ
    body: dict = {}
    if title:
        body["subject"] = title
    if start:
        body["start"] = _time_field(start, all_day, tz)
    if end:
        body["end"] = _time_field(end, all_day, tz)
    if all_day and (start or end):
        body["isAllDay"] = True
    if description:
        body["body"] = {"contentType": "text", "content": description}
    if location:
        body["location"] = {"displayName": location}
    if not body:
        raise ValueError("update_event: nothing to change (no fields provided)")
    r = _session().patch(f"{GRAPH}/me/events/{event_id}", json=body, timeout=30)
    r.raise_for_status()
    ev = r.json()
    return {"id": ev.get("id", ""), "html_link": ev.get("webLink", ""), "status": "updated"}
