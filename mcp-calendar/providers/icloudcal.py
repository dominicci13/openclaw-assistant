"""iCloud Calendar (CalDAV) provider backend for the calendar MCP server.

Read + create + UPDATE events on the user's primary iCloud calendar over CalDAV
(`caldav.icloud.com`) using an APP-SPECIFIC password. NEVER deletes (no delete
tool/code path) and never adds attendees (v1 = own-calendar only) — so create and
update are zero-outbound. "Update in place" is allowed (own calendar, recoverable).

CalDAV is HTTPS, so the `caldav` library's underlying `requests` session honors
HTTPS_PROXY -> on the internal Docker network it routes through squid (DNS + egress
allowlist). Unlike iCloud IMAP (which needed a hand-rolled CONNECT tunnel), CalDAV
proxies natively.

NOTE: an iCloud app-specific password is ALL-OR-NOTHING (it can reach mail,
calendar, contacts, etc.), so a compromise of this credential has the same blast
radius as the mail one — no-delete is enforced at the TOOL layer (no delete code).
A SEPARATE app password (from the mail one) buys independent revocation + mount
isolation, not reduced scope.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import caldav
import icalendar

CALDAV_URL = "https://caldav.icloud.com/"
_DEFAULT_TZ = os.environ.get("CALENDAR_DEFAULT_TZ", "America/Santo_Domingo")

SECRETS_DIR = Path(
    os.environ.get(
        "ICLOUDCAL_SECRETS_DIR",
        Path(__file__).resolve().parent.parent / "instance" / "icloudcal",
    )
)
CONFIG_FILE = SECRETS_DIR / "config.json"


def _load_config() -> dict:
    """Read iCloud email + app-specific password (both secret; 600 read-only mount)."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f"iCloud calendar not configured: create {CONFIG_FILE} with 'email' and 'app_password'."
        )
    if not cfg.get("email") or not cfg.get("app_password"):
        raise RuntimeError("iCloud calendar config.json missing 'email' or 'app_password'.")
    return cfg


def _calendar():
    """Discover + return the user's primary iCloud calendar collection.

    caldav's requests session honors HTTPS_PROXY (trust_env), so this routes
    through squid on the internal network. Discovery (principal -> calendar-home ->
    calendars) runs per call; fine for v1.
    """
    cfg = _load_config()
    client = caldav.DAVClient(url=CALDAV_URL, username=cfg["email"], password=cfg["app_password"])
    principal = client.principal()
    cals = principal.calendars()
    if not cals:
        raise RuntimeError("No iCloud calendars found for this account.")
    # Prefer the first collection that supports VEVENT; fall back to the first.
    for c in cals:
        try:
            comps = c.get_supported_components()
        except Exception:
            comps = []
        if not comps or "VEVENT" in comps:
            return c
    return cals[0]


def _tz(name: str) -> ZoneInfo:
    return ZoneInfo(name or _DEFAULT_TZ)


def _parse_dt(value: str, all_day: bool, tz: str):
    """ISO 8601 -> date (all-day) or tz-aware datetime."""
    if all_day:
        return date.fromisoformat(value[:10])
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(tz))
    return dt


def _fmt(comp) -> dict:
    """Flatten an icalendar VEVENT component into the shape the model sees."""
    def g(key: str) -> str:
        v = comp.get(key)
        return str(v) if v is not None else ""

    start = comp.get("dtstart")
    end = comp.get("dtend")
    sval = start.dt if start is not None else None
    return {
        "id": g("uid"),
        "title": g("summary") or "(no title)",
        "start": sval.isoformat() if sval is not None else "",
        "end": end.dt.isoformat() if end is not None else "",
        "all_day": isinstance(sval, date) and not isinstance(sval, datetime),
        "location": g("location"),
        "html_link": "",  # CalDAV has no web link
    }


def list_events(start: str, end: str, max_results: int = 25) -> list[dict]:
    """List events between `start` and `end` (ISO 8601) via a CalDAV time-range search."""
    max_results = max(1, min(max_results, 100))
    cal = _calendar()
    s = _parse_dt(start, all_day=False, tz=_DEFAULT_TZ)
    e = _parse_dt(end, all_day=False, tz=_DEFAULT_TZ)
    found = cal.search(start=s, end=e, event=True, expand=True)
    out: list[dict] = []
    for ev in found[:max_results]:
        for comp in icalendar.Calendar.from_ical(ev.data).walk("VEVENT"):
            out.append(_fmt(comp))
    return out


def _build_ics(title, start, end, description, location, all_day, tz, uid=None) -> str:
    cal = icalendar.Calendar()
    cal.add("prodid", "-//OpenClaw//Calendar//EN")
    cal.add("version", "2.0")
    ev = icalendar.Event()
    ev.add("uid", uid or f"{uuid.uuid4()}@openclaw")
    ev.add("dtstamp", datetime.now(_tz(tz)))
    ev.add("summary", title)
    ev.add("dtstart", _parse_dt(start, all_day, tz))
    ev.add("dtend", _parse_dt(end, all_day, tz))
    if description:
        ev.add("description", description)
    if location:
        ev.add("location", location)
    cal.add_component(ev)
    return cal.to_ical().decode()


def create_event(
    title: str, start: str, end: str,
    description: str = "", location: str = "",
    all_day: bool = False, timezone: str = "",
) -> dict:
    """Create an event on the primary iCloud calendar. NO attendees -> no invites."""
    tz = timezone or _DEFAULT_TZ
    uid = f"{uuid.uuid4()}@openclaw"
    ics = _build_ics(title, start, end, description, location, all_day, tz, uid=uid)
    _calendar().save_event(ics)
    return {"id": uid, "html_link": "", "status": "created"}


def update_event(
    event_id: str,
    title: str = "", start: str = "", end: str = "",
    description: str = "", location: str = "",
    all_day: bool = False, timezone: str = "",
) -> dict:
    """Patch an existing event in place by UID. Only provided fields change. No delete."""
    tz = timezone or _DEFAULT_TZ
    cal = _calendar()
    ev = cal.event_by_uid(event_id)
    parsed = icalendar.Calendar.from_ical(ev.data)
    changed = False
    for comp in parsed.walk("VEVENT"):
        if title:
            comp["summary"] = title
            changed = True
        if start:
            comp.pop("dtstart", None)
            comp.add("dtstart", _parse_dt(start, all_day, tz))
            changed = True
        if end:
            comp.pop("dtend", None)
            comp.add("dtend", _parse_dt(end, all_day, tz))
            changed = True
        if description:
            comp["description"] = description
            changed = True
        if location:
            comp["location"] = location
            changed = True
    if not changed:
        raise ValueError("update_event: nothing to change (no fields provided)")
    ev.data = parsed.to_ical().decode()
    ev.save()
    return {"id": event_id, "html_link": "", "status": "updated"}
