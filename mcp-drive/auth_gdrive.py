"""OAuth credentials handling for the Google Drive provider (drive MCP server).

Run directly ('python auth_gdrive.py') once to mint the account token via a
browser consent flow; the provider imports get_credentials() for normal
operation. Mirrors the mail sidecar's Gmail auth, with the Drive scope and its
own secrets dir - a SEPARATE Google OAuth client from Gmail, so a drive-token
compromise can't touch mail (and vice-versa).
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# The ONLY scope this provider will ever hold: full Drive (read + create across
# the user's whole drive), deliberately chosen for parity with OneDrive. If this
# list ever changes, delete token.json and re-run consent - Google grants are
# per-scope-set, and we WANT a fresh explicit consent on any widening.
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Configurable so the same code runs on the Mac (default) and in the container
# (env points at the mounted secrets dir).
SECRETS_DIR = Path(
    os.environ.get("GDRIVE_SECRETS_DIR", Path(__file__).resolve().parent.parent / "instance" / "gdrive")
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
        # Opens the browser, catches the redirect on a random localhost port.
        creds = flow.run_local_server(port=0)
        _save(creds)

    return creds


def _save(creds: Credentials) -> None:
    """Best-effort cache of refreshed creds.

    The container mounts the secrets dir READ-ONLY by design - the sidecar treats
    credentials as read-only input. Writes fail there, and that's correct: the
    refreshed access token lives in memory for the process's life and is
    re-derived from the refresh token on restart. On the Mac (writable) this
    caches the token normally so local runs skip a refresh round-trip.
    """
    try:
        TOKEN_FILE.write_text(creds.to_json())
        TOKEN_FILE.chmod(0o600)  # token = the actual drive credential
    except OSError:
        pass  # read-only secrets mount; in-memory creds remain valid


if __name__ == "__main__":
    c = get_credentials()
    print("Token OK. Granted scopes:")
    for s in c.scopes or []:
        print(f"  {s}")
