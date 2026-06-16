"""Provider registry for the drive MCP server.

Each provider is a plain module exposing: list_files, read_file, write_file,
create_excel, create_doc. `account` strings map to provider modules here.
Duck-typed modules in a dict (no class hierarchy) match the mail sidecar's house
style. Each provider holds its OWN OAuth credentials (separate Microsoft/Google
apps) - isolation is per-provider as well as per-sidecar.
"""

from __future__ import annotations

from types import ModuleType

from . import gdrive, onedrive

# account name -> provider module
PROVIDERS: dict[str, ModuleType] = {
    "onedrive": onedrive,
    "gdrive": gdrive,
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
