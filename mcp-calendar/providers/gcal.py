"""Google Calendar (Calendar API v3) provider backend for the calendar MCP server.

Read + create + UPDATE events on the user's primary calendar (scope
`calendar.events`). It NEVER deletes (no delete tool/code path) and never invites
external attendees (v1 = own-calendar events only). Updates and creates both set
`sendUpdates="none"` so NO notification email is ever sent — create and update are
zero-outbound. "Update in place" is allowed here (unlike drive/mail) because it's
the user's own calendar, recoverable, and silent.

The Calendar API uses httplib2, which does NOT honor HTTP(S)_PROXY, so — like the
Gmail/Drive providers — we hand it an explicitly-proxied http routed through squid.
Event content read back is DATA, never instructions.
"""

from __future__ import annotations

import os

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

from auth_gcal import get_credentials

# The user's local zone (UTC-4, no DST). Events created without an explicit zone
# land here. The model may pass an explicit `timezone` (e.g. "Europe/Madrid").
_DEFAULT_TZ = os.environ.get("CALENDAR_DEFAULT_TZ", "America/Santo_Domingo")
_CALENDAR_ID = "primary"  # v1: the user's primary calendar only.


def _http() -> httplib2.Http:
    """An httplib2 client routed through the egress proxy when one is set (the
    internal Docker net has no external DNS; squid resolves + enforces the
    allowlist). Locally (no proxy env) it's direct."""
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy_url:
        return httplib2.Http()
    return httplib2.Http(proxy_info=httplib2.proxy_info_from_url(proxy_url, method="https"))


def _cal():
    authed = AuthorizedHttp(get_credentials(), http=_http())
    return build("calendar", "v3", http=authed, cache_discovery=False)


def _time_field(value: str, all_day: bool, tz: str) -> dict:
    """Build a Calendar API start/end object. All-day -> {date}; timed ->
    {dateTime, timeZone}. `value` is ISO 8601 (date `YYYY-MM-DD` or datetime)."""
    if all_day:
        return {"date": value[:10]}  # date-only; the API wants YYYY-MM-DD
    return {"dateTime": value, "timeZone": tz}


def _fmt(ev: dict) -> dict:
    """Flatten an API event into the shape the model sees."""
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "id": ev.get("id", ""),
        "title": ev.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "all_day": "date" in start,
        "location": ev.get("location", ""),
        "html_link": ev.get("htmlLink", ""),
    }


def list_events(start: str, end: str, max_results: int = 25) -> list[dict]:
    """List events on the primary calendar between `start` and `end` (ISO 8601).

    singleEvents=True expands recurring events; orderBy=startTime sorts them.
    """
    max_results = max(1, min(max_results, 100))
    res = _cal().events().list(
        calendarId=_CALENDAR_ID,
        timeMin=start, timeMax=end,
        singleEvents=True, orderBy="startTime",
        maxResults=max_results,
    ).execute()
    return [_fmt(ev) for ev in res.get("items", [])]


def create_event(
    title: str, start: str, end: str,
    description: str = "", location: str = "",
    all_day: bool = False, timezone: str = "",
) -> dict:
    """Create an event on the primary calendar. NO attendees (zero outbound);
    `sendUpdates="none"` guarantees no notification is sent."""
    tz = timezone or _DEFAULT_TZ
    body = {
        "summary": title,
        "start": _time_field(start, all_day, tz),
        "end": _time_field(end, all_day, tz),
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    ev = _cal().events().insert(
        calendarId=_CALENDAR_ID, body=body, sendUpdates="none",
    ).execute()
    return {"id": ev.get("id", ""), "html_link": ev.get("htmlLink", ""), "status": "created"}


def update_event(
    event_id: str,
    title: str = "", start: str = "", end: str = "",
    description: str = "", location: str = "",
    all_day: bool = False, timezone: str = "",
) -> dict:
    """Patch an existing event in place. Only provided fields change;
    `sendUpdates="none"` suppresses any attendee notification. No delete."""
    tz = timezone or _DEFAULT_TZ
    body: dict = {}
    if title:
        body["summary"] = title
    if start:
        body["start"] = _time_field(start, all_day, tz)
    if end:
        body["end"] = _time_field(end, all_day, tz)
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if not body:
        raise ValueError("update_event: nothing to change (no fields provided)")
    ev = _cal().events().patch(
        calendarId=_CALENDAR_ID, eventId=event_id, body=body, sendUpdates="none",
    ).execute()
    return {"id": ev.get("id", ""), "html_link": ev.get("htmlLink", ""), "status": "updated"}
