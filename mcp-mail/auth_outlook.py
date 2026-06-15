"""Outlook (Microsoft Graph) OAuth via MSAL device-code flow.

Run directly ('python auth_outlook.py') ONCE on a machine with a browser to
mint the account token via device-code consent; the server imports get_token()
for normal operation. Mirrors auth.py (Gmail).

Device-code flow is headless-friendly: it prints a code + URL, you open the URL
in any browser and enter the code. No redirect/local server needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import msal

# The ONLY scopes this server will ever hold for Outlook. Mail.ReadWrite covers
# read + draft. We deliberately DO NOT request Mail.Send -> the token physically
# CANNOT send (verified: send requires a separate Mail.Send scope). Delete is
# permitted by Mail.ReadWrite but is blocked at the tool layer (no delete tool).
# MSAL adds the reserved scopes (offline_access/openid/profile) automatically;
# do not list them here.
SCOPES = ["Mail.ReadWrite"]

# Configurable so the same code runs on the Mac (default) and in the container
# (env points at the mounted secrets dir).
SECRETS_DIR = Path(
    os.environ.get(
        "OUTLOOK_SECRETS_DIR",
        Path(__file__).resolve().parent.parent / "instance" / "outlook",
    )
)
CONFIG_FILE = SECRETS_DIR / "config.json"
CACHE_FILE = SECRETS_DIR / "token_cache.json"


def _load_config() -> dict:
    """Read client_id + authority (client_id is a public identifier, not a secret)."""
    with open(CONFIG_FILE) as f:
        return json.load(f)


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text())
    return cache


def _build_app(cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    cfg = _load_config()
    return msal.PublicClientApplication(
        cfg["client_id"],
        authority=cfg.get("authority", "https://login.microsoftonline.com/consumers"),
        token_cache=cache,
    )


def get_token() -> str:
    """Return a valid Graph access token, refreshing silently as needed.

    Raises:
        RuntimeError: no cached account (mint not run) or refresh failed.
    """
    cache = _load_cache()
    app = _build_app(cache)
    accounts = app.get_accounts()
    if not accounts:
        raise RuntimeError(
            "No Outlook account in cache. Run `python auth_outlook.py` once to mint the token."
        )
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result or "access_token" not in result:
        detail = result.get("error_description", result) if result else "no token in cache"
        raise RuntimeError(f"Outlook token refresh failed: {detail}")
    # Best-effort persist a rotated refresh token. In the container /secrets-outlook
    # is mounted READ-ONLY, so this silently no-ops there (refresh still works in
    # memory for the process lifetime); on the writable mint host it persists.
    # KNOWN RISK: MS rotates refresh tokens; if a rotation can't persist (read-only
    # mount) a later cold start reuses the seed token. Revisit (writable tmpfs cache)
    # if re-consent starts being required too often.
    if cache.has_state_changed:
        try:
            CACHE_FILE.write_text(cache.serialize())
        except OSError:
            pass
    return result["access_token"]


def mint() -> None:
    """Interactive device-code mint. Run on a machine with a browser."""
    cache = _load_cache()
    app = _build_app(cache)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow init failed: {flow}")
    print(flow["message"], flush=True)  # "open <url> and enter code <code>"
    result = app.acquire_token_by_device_flow(flow)  # blocks until consent completes
    if "access_token" not in result:
        raise RuntimeError(f"Mint failed: {result.get('error_description', result)}")
    # Confirm at birth that no unexpected scope (e.g. Mail.Send) was granted.
    print("Granted scopes:", result.get("scope", "<none reported>"), flush=True)
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(cache.serialize())
    try:
        os.chmod(CACHE_FILE, 0o600)
    except OSError:
        pass
    print(f"Token cached at {CACHE_FILE}", flush=True)


if __name__ == "__main__":
    mint()
