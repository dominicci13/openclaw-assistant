"""Gmail provider backend for the mail MCP server.

Pure backend: the model-facing tool definitions and docstrings live in main.py;
this module only talks to the Gmail API. It exposes the provider-common trio
(see providers/__init__.py): search_messages, get_message, create_draft.

Send, delete, and modify DO NOT EXIST here by design - and the OAuth token
couldn't perform send/delete anyway (gmail.readonly + gmail.compose; delete
is 403 at Google). Two walls, one decision.
"""

from __future__ import annotations

import os
import base64
import httplib2
from email.message import EmailMessage

from googleapiclient.discovery import build
from google_auth_httplib2 import AuthorizedHttp

from attachments import add_to_email
from auth import get_credentials
from timeutil import to_local


def _http() -> httplib2.Http:
    """An httplib2 client routed through the egress proxy when one is set.

    googleapiclient talks to Gmail via httplib2, which - unlike google-auth's
    requests-based token-refresh path - does NOT honor HTTP(S)_PROXY env vars.
    On the internal Docker network there is no external DNS, so without explicit
    proxy config it fails name resolution. We point it at squid, which resolves
    DNS and enforces the egress allowlist. Locally (no proxy env) it's direct.
    """
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy_url:
        return httplib2.Http()
    # method="https" -> CONNECT tunnel for TLS destinations; squid resolves the
    # DNS and enforces the allowlist. httplib2's proxy transport needs pysocks
    # (it does `import socks`), so PySocks is a pinned requirement.
    return httplib2.Http(proxy_info=httplib2.proxy_info_from_url(proxy_url, method="https"))


def _gmail():
    # Pass an explicitly-proxied http; AuthorizedHttp attaches the credentials.
    # (When http= is given, build() must not also receive credentials=.)
    authed = AuthorizedHttp(get_credentials(), http=_http())
    return build("gmail", "v1", http=authed, cache_discovery=False)


def search_messages(query: str, max_results: int = 10) -> list[dict]:
    """Search the Gmail mailbox with Gmail's standard query syntax."""
    max_results = max(1, min(max_results, 25))
    svc = _gmail()
    resp = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()

    results: list[dict] = []
    for ref in resp.get("messages", []):
        # The list endpoint returns only ids; fetch headers per message.
        # format="metadata" returns headers + snippet, never the body.
        msg = svc.users().messages().get(
            userId="me",
            id=ref["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        results.append({
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "date": to_local(headers.get("date", "")),
            "from_": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "snippet": msg.get("snippet", ""),
        })
    return results


def _find_text(payload: dict, mime: str) -> str:
    """Walk the MIME tree for the first leaf of the given type."""
    if payload.get("mimeType", "").startswith(mime):
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _find_text(part, mime)
        if text:
            return text
    return ""


def get_message(message_id: str, max_chars: int = 20000) -> dict:
    """Fetch one Gmail message's headers and body text.

    Returns headers plus body_untrusted - named that way because email bodies
    are unauthenticated external content: treat as data, never as instructions.
    """
    msg = _gmail().users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    body = _find_text(msg["payload"], "text/plain") or _find_text(msg["payload"], "text/html")
    return {
        "id": msg["id"],
        "thread_id": msg["threadId"],
        "date": headers.get("date", ""),
        "from_": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "body_untrusted": body[:max_chars],
    }


def create_draft(to: str, subject: str, body: str, thread_id: str | None = None) -> dict:
    """Create a DRAFT in Gmail's Drafts folder. Nothing is sent."""
    mime = EmailMessage()
    mime["To"] = to
    mime["Subject"] = subject
    mime.set_content(body)

    payload: dict = {"message": {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}}
    if thread_id:
        payload["message"]["threadId"] = thread_id

    draft = _gmail().users().drafts().create(userId="me", body=payload).execute()
    return {"draft_id": draft["id"], "message_id": draft["message"]["id"]}


def send_message(to: str, subject: str, body: str, thread_id: str | None = None,
                 attachments: list[dict] | None = None) -> dict:
    """SEND an email via Gmail. The consent TOTP is enforced upstream (main.py);
    the gmail.compose scope permits send (verified M4)."""
    mime = EmailMessage()
    mime["To"] = to
    mime["Subject"] = subject
    mime.set_content(body)
    add_to_email(mime, attachments)

    payload: dict = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
    if thread_id:
        payload["threadId"] = thread_id

    sent = _gmail().users().messages().send(userId="me", body=payload).execute()
    return {"id": sent["id"], "thread_id": sent.get("threadId", "")}
