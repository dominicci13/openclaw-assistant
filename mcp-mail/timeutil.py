"""Normalize email timestamps to the user's local timezone for display.

Providers return timestamps in different shapes: Outlook/Graph in UTC ('...Z'),
Gmail/iCloud as RFC 2822 Date headers carrying the SENDER's offset. Shown raw,
arrival times look hours off (e.g. a UTC 14:33 reads as 2:33 PM instead of the
real 10:33 AM AST). to_local() parses either shape and renders the instant in the
user's zone (default America/Santo_Domingo, UTC-4) so the model just displays a
correct local time, no conversion math required of it.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

_TZ = os.environ.get("MAIL_TZ", "America/Santo_Domingo")


def to_local(raw: str) -> str:
    """Render an RFC 2822 or ISO 8601 timestamp as local time, e.g.
    '2026-06-16 10:33 AST'. Returns the original string if it can't be parsed."""
    if not raw:
        return ""
    dt = None
    try:
        dt = parsedate_to_datetime(raw)  # RFC 2822 (Gmail / iCloud Date headers)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))  # ISO 8601 (Graph)
        except ValueError:
            return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(_TZ)).strftime("%Y-%m-%d %H:%M %Z")
