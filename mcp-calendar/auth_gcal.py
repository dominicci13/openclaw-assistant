"""OAuth credentials handling for the Google Calendar provider (calendar MCP server).

Run directly ('python auth_gcal.py') once to mint the account token via a browser
consent flow; the provider imports get_credentials() for normal operation. Its OWN
Google OAuth client (separate from Gmail and Drive), so a calendar-token compromise
can't touch mail or files (and vice-versa).
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# The ONLY scope this provider holds: events read/create/update (NOT calendar
# settings, NOT other calendars' ACLs) — least privilege. If this list ever
# changes, delete token.json and re-run consent (Google grants are per-scope-set;
# we WANT a fresh explicit consent on any widening).
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Configurable so the same code runs on the Mac (default) and in the container
# (env points at the mounted secrets dir).
SECRETS_DIR = Path(
    os.environ.get("GCAL_SECRETS_DIR", Path(__file__).resolve().parent.parent / "instance" / "gcal")
)
CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"
TOKEN_FILE = SECRETS_DIR / "token.json"


def get_credentials() -> Credentials:
    """Return valid credentials, refreshing or minting as needed.

    Returns:
        Credentials limited to SCOPES.

    Raises:
        FileNotFoundError: client_secret.json is missing.
    """
    creds: Credentials | None = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())  # silent renewal, no browser
        _save(creds)

    if not creds or not creds.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise FileNotFoundError(f"Missing {CLIENT_SECRET_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
        _save(creds)

    return creds


def _save(creds: Credentials) -> None:
    """Best-effort cache of refreshed creds (no-op on the read-only secrets mount;
    in-memory creds stay valid and are re-derived from the refresh token on restart).
    """
    try:
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)  # token = the actual calendar credential
    except OSError:
        pass


if __name__ == "__main__":
    c = get_credentials()
    print("Token OK. Granted scopes:")
    for s in c.scopes or []:
        print(f"  {s}")
