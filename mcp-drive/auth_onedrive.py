"""OneDrive (Microsoft Graph Files) OAuth via MSAL device-code flow.

Run directly ('python auth_onedrive.py') ONCE on a machine with a browser to mint
the account token; the server imports get_token() for normal operation. Mirrors
mcp-mail/auth_outlook.py, but a SEPARATE Azure app + token so drive credentials
are isolated from mail (a drive compromise can't touch mail, and vice-versa).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import msal

# Files.ReadWrite = read + write the user's whole OneDrive (delegated, personal
# account, no admin consent). The provider exposes NO delete/overwrite path, so
# the token's write power is constrained to "create new" at the tool layer. MSAL
# adds reserved scopes (offline_access/openid/profile) automatically.
SCOPES = ["Files.ReadWrite"]

SECRETS_DIR = Path(
    os.environ.get(
        "ONEDRIVE_SECRETS_DIR",
        Path(__file__).resolve().parent.parent / "instance" / "onedrive",
    )
)
CONFIG_FILE = SECRETS_DIR / "config.json"
CACHE_FILE = SECRETS_DIR / "token_cache.json"


def _load_config() -> dict:
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
            "No OneDrive account in cache. Run `python auth_onedrive.py` once to mint the token."
        )
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result or "access_token" not in result:
        detail = result.get("error_description", result) if result else "no token in cache"
        raise RuntimeError(f"OneDrive token refresh failed: {detail}")
    if cache.has_state_changed:
        try:
            CACHE_FILE.write_text(cache.serialize())
        except OSError:
            pass  # /secrets-onedrive is read-only in the container; refresh stays in memory
    return result["access_token"]


def mint() -> None:
    """Interactive device-code mint. Run on a machine with a browser."""
    cache = _load_cache()
    app = _build_app(cache)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow init failed: {flow}")
    print(flow["message"], flush=True)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Mint failed: {result.get('error_description', result)}")
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
