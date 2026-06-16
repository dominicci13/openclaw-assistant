"""Provider registry for the calendar MCP server.

Each provider is a plain module exposing: list_events, create_event, update_event
(NO delete). `account` strings map to provider modules here. Each provider holds
its OWN credentials (separate OAuth apps / app password) — isolation per-provider
and per-sidecar.
"""

from __future__ import annotations

from types import ModuleType

from . import gcal, icloudcal, mscal

# account name -> provider module
PROVIDERS: dict[str, ModuleType] = {
    "google": gcal,
    "outlook": mscal,
    "icloud": icloudcal,
}


def get_provider(account: str) -> ModuleType:
    """Return the provider module for an account, or raise on an unknown one.

    Raises:
        ValueError: the account is not a registered provider.
    """
    try:
        return PROVIDERS[account]
    except KeyError:
        raise ValueError(f"Unknown account '{account}'. Available: {sorted(PROVIDERS)}")
