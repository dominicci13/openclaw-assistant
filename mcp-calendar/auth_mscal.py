"""Outlook/Microsoft (Graph) Calendar OAuth via MSAL device-code flow.

Run directly ('python auth_mscal.py') ONCE on a machine with a browser to mint the
token via device-code consent; the provider imports get_token() for normal
operation. Mirrors the mail sidecar's auth_outlook.py, with the Calendars scope and
its OWN Azure app (separate from Outlook mail) — calendar-token compromise can't
touch mail.

Device-code flow is headless-friendly: it prints a code + URL; open the URL in any
browser and enter the code. No redirect/local server needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import msal

# The ONLY scope this provider holds: Calendars.ReadWrite (read + create + update
# events). Delete is permitted by this scope but blocked at the TOOL layer (no
# delete tool). MSAL adds reserved scopes (offline_access/openid/profile)
# automatically; do not list them. Changing this requires a re-mint.
SCOPES = ["Calendars.ReadWrite"]

SECRETS_DIR = Path(
    os.environ.get(
        "MSCAL_SECRETS_DIR",
        Path(__file__).resolve().parent.parent / "instance" / "mscal",
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
            "No Outlook calendar account in cache. Run `python auth_mscal.py` once to mint."
        )
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result or "access_token" not in result:
        detail = result.get("error_description", result) if result else "no token in cache"
        raise RuntimeError(f"Outlook calendar token refresh failed: {detail}")
    # Best-effort persist a rotated refresh token; no-ops on the read-only mount in
    # the container (refresh stays valid in memory for the process lifetime).
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
    print(flow["message"], flush=True)
    result = app.acquire_token_by_device_flow(flow)  # blocks until consent completes
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
