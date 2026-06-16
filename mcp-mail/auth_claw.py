"""OAuth for Claw's OWN send-only email identity (claw.brian.ai@gmail.com).

A dedicated outbound address so assistant -> user emails (files, reports, the
weekly security-watch) arrive in the user's inbox FROM Claw, instead of the user
self-sending and getting the message in both Sent and Inbox.

SEND-ONLY by scope: gmail.send can ONLY send - it cannot read, list, or draft. So
even if this token leaked, it can't read the Claw mailbox, and the per-send consent
gate (main.py) still blocks sending to EXTERNAL recipients without a TOTP.

Run directly ('python auth_claw.py') ONCE, signed in AS claw.brian.ai@gmail.com,
to mint the token. Mirrors auth.py (Gmail), with its own scope + secrets dir.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Send-only. The narrowest Gmail scope: it sends and nothing else.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

SECRETS_DIR = Path(
    os.environ.get("CLAW_SECRETS_DIR", Path(__file__).resolve().parent.parent / "instance" / "clawmail")
)
CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"
TOKEN_FILE = SECRETS_DIR / "token.json"


def get_credentials() -> Credentials:
    """Return valid send-only credentials, refreshing or minting as needed."""
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save(creds)
    if not creds or not creds.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise FileNotFoundError(f"Missing {CLIENT_SECRET_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
        _save(creds)
    return creds


def _save(creds: Credentials) -> None:
    """Best-effort cache (no-op on the read-only secrets mount in the container)."""
    try:
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass


if __name__ == "__main__":
    c = get_credentials()
    print("Token OK. Granted scopes:")
    for s in c.scopes or []:
        print(f"  {s}")
