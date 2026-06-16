"""Claw's own SEND-ONLY email identity (claw.brian.ai@gmail.com).

A dedicated outbound address so assistant -> user emails (files, reports, the
weekly security-watch) arrive in the user's inbox FROM Claw - instead of the user
self-sending and getting the message in both Sent and Inbox.

SEND-ONLY by scope (gmail.send): it can only send. search/get/draft raise here, so
this account can never read or list mail even if misused. Sending is still gated by
the per-send consent TOTP (main.py) for EXTERNAL recipients; emailing the user's own
addresses needs no code.

Mirrors the Gmail send path (httplib2 routed through squid), with its own token.
"""

from __future__ import annotations

import base64
import os
from email.message import EmailMessage

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

from attachments import add_to_email
from auth_claw import get_credentials

_SEND_ONLY = (
    "claw is a SEND-ONLY account (Claw's own address). It can only send. "
    "Use gmail / outlook / icloud to search, read, or draft."
)


def _http() -> httplib2.Http:
    """httplib2 routed through the egress proxy when set (same as the Gmail provider)."""
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy_url:
        return httplib2.Http()
    return httplib2.Http(proxy_info=httplib2.proxy_info_from_url(proxy_url, method="https"))


def _claw():
    authed = AuthorizedHttp(get_credentials(), http=_http())
    return build("gmail", "v1", http=authed, cache_discovery=False)


def search_messages(query: str, max_results: int = 10) -> list[dict]:
    raise ValueError(_SEND_ONLY)


def get_message(message_id: str, max_chars: int = 20000) -> dict:
    raise ValueError(_SEND_ONLY)


def create_draft(*args, **kwargs) -> dict:
    raise ValueError(_SEND_ONLY)


def send_message(to: str, subject: str, body: str, thread_id: str | None = None,
                 attachments: list[dict] | None = None) -> dict:
    """SEND from Claw's own address. gmail.send scope; the per-send consent gate is
    enforced upstream (main.py)."""
    mime = EmailMessage()
    mime["To"] = to
    mime["Subject"] = subject
    mime.set_content(body)
    add_to_email(mime, attachments)
    payload: dict = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
    if thread_id:
        payload["threadId"] = thread_id
    sent = _claw().users().messages().send(userId="me", body=payload).execute()
    return {"id": sent["id"], "thread_id": sent.get("threadId", "")}
