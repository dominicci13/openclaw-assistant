"""OAuth credentials handling for the Gmail MCP server.

Run directly ('python auth.py') once to mint the account token via a browser
consent flow; the server imports gets_credentials() for normal operation.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# The ONLY scopes this server will ever hold. If this list ever changes,
# delete token.json and re-run the consent flow - Google grants are
# per-scope-set, and we WANT a fresh explicit consent on any widening.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose"
]

# Configurable so the same code runs on the Mac (default) and in the
# container (env points at the mounted secrets dir).
SECRETS_DIR = Path(
    os.environ.get("GMAIL_SECRETS_DIR", Path(__file__).resolve().parent.parent / "instance" / "gmail")
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
        creds.refresh(Request()) # silent renewal, no browser
        _save(creds)

    if not creds or not creds.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise FileNotFoundError(f"Missing {CLIENT_SECRET_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
        # Opens the browser, catches the redirect on a random localhost port.
        creds = flow.run_local_server(port=0)
        _save(creds)

    return creds


def _save(creds: Credentials) -> None:
    """Best-effort cache of refreshed creds.

    The container mounts /secrets READ-ONLY by design â the sidecar treats
    credentials as read-only input. Writes fail there, and that's correct:
    the refreshed access token lives in memory for the process's life and is
    re-derived from the refresh token on restart. On the Mac (writable) this
    caches the token normally so local runs skip a refresh round-trip.
    """
    try:
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)  # token = the actual mailbox credential
    except OSError:
        pass  # read-only secrets mount; in-memory creds remain valid


if __name__ == "__main__":
    c = get_credentials()
    print("Token OK. Granted scopes:")
    for s in c.scopes or []:
        print(f"  {s}")