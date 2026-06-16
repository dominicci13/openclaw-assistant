"""Provider registry for the mail MCP server.

Each provider is a plain module exposing the same three functions:
    search_messages(query, max_results) -> list[dict]
    get_message(message_id, max_chars)  -> dict
    create_draft(to, subject, body, thread_id) -> dict

`account` strings map to provider modules here. Outlook and iCloud join the
registry in later milestones. Duck-typed modules in a dict beat a class
hierarchy at this scale: each backend is plainly visible and self-contained.
"""

from __future__ import annotations

from types import ModuleType

from . import claw, gmail, icloud, outlook

# account name -> provider module. "claw" is Claw's OWN send-only address
# (claw.brian.ai@gmail.com) - it only sends (search/get/draft raise there).
PROVIDERS: dict[str, ModuleType] = {
    "gmail": gmail,
    "outlook": outlook,
    "icloud": icloud,
    "claw": claw,
}


def get_provider(account: str) -> ModuleType:
    """Return the provider module for an account, or raise on an unknown one.

    Args:
        account: mailbox selector, e.g. "gmail".

    Returns:
        The provider module exposing search_messages / get_message / create_draft.

    Raises:
        ValueError: the account is not a registered provider.
    """
    try:
        return PROVIDERS[account]
    except KeyError:
        raise ValueError(
            f"Unknown account '{account}'. Available: {sorted(PROVIDERS)}"
        )
