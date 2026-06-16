"""Per-send consent gate.

Sending requires a fresh TOTP code that only the user can produce (from his
authenticator). The secret (SEND_TOTP_SECRET, env) lives in the sidecar and is
NEVER in the model's context — so a prompt-injected model cannot send: it can't
generate a valid code. Codes are single-use within their window (replay-blocked).

This is the code-enforced gate OpenClaw can't provide for an MCP tool (its
approvals are exec-only; elicitation fails closed for general MCP servers).
"""

from __future__ import annotations

import os
import threading
from email.utils import getaddresses

import pyotp

_lock = threading.Lock()
_used: set[str] = set()  # codes consumed this process-lifetime (replay block)


def verify_send_code(code: str) -> None:
    """Raise PermissionError unless ``code`` is a fresh, valid, unused TOTP.

    Args:
        code: the 6-digit code the user read from his authenticator for THIS send.

    Raises:
        PermissionError: secret unset, malformed/invalid/expired code, or replay.
    """
    secret = os.environ.get("SEND_TOTP_SECRET")
    if not secret:
        raise PermissionError("Send is disabled: SEND_TOTP_SECRET is not configured.")

    cleaned = (code or "").strip().replace(" ", "")
    if not (cleaned.isdigit() and len(cleaned) == 6):
        raise PermissionError(
            "Invalid confirmation code: expected the 6-digit code from the user's authenticator."
        )

    # valid_window=1 tolerates ~30s of clock skew on either side; nothing else.
    if not pyotp.TOTP(secret).verify(cleaned, valid_window=1):
        raise PermissionError(
            "Confirmation code rejected (wrong or expired). Ask the user for the current code."
        )

    with _lock:
        if cleaned in _used:
            raise PermissionError("That code was already used. Ask the user for the next code.")
        _used.add(cleaned)


def _own_addresses() -> set[str]:
    """The user's own email addresses (env OWN_EMAIL_ADDRESSES, comma-separated,
    lowercased). Config the model cannot touch - this set is the security
    boundary that decides which sends may skip the code."""
    raw = os.environ.get("OWN_EMAIL_ADDRESSES", "")
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


def code_required(to: str) -> bool:
    """True unless EVERY recipient is one of the user's own addresses.

    Self-only sends (the user's Gmail/Outlook/iCloud, any direction) skip the TOTP -
    they can't exfiltrate to an attacker or impersonate to others. Fail-safe: any
    external, mixed-in, or unparseable recipient -> code required.
    """
    own = _own_addresses()
    recipients = [addr.lower() for _name, addr in getaddresses([to or ""]) if addr]
    if not recipients:
        return True  # empty / unparseable -> require the code
    return not all(r in own for r in recipients)
