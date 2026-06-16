"""Minimal read-only GitHub API client for the MCP sidecar.

Talks to api.github.com over HTTPS with a fine-grained PAT. httpx honours the
HTTP(S)_PROXY env vars (trust_env=True by default), so every call is routed
through squid — the same fail-closed chokepoint as every other sidecar.

READ-ONLY BY CONSTRUCTION: this module issues GET requests only. There is no
helper that POSTs/PATCHes/PUTs/DELETEs. The PAT is also scoped (on GitHub) to
read-only permissions, so even a code bug here cannot mutate a repo.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from pathlib import Path

import httpx

_API = "https://api.github.com"
_TIMEOUT = httpx.Timeout(30.0)


def _token() -> str:
    """Read the PAT from the mounted secrets file (never from a bare env var, so
    it stays out of `docker inspect`). Path is $GITHUB_SECRETS_DIR/token."""
    secrets_dir = os.environ.get("GITHUB_SECRETS_DIR", "/secrets-github")
    token_path = Path(secrets_dir) / "token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"GitHub PAT not found at {token_path}. Mount it read-only into the "
            "sidecar (instance/github/token)."
        ) from exc
    if not token:
        raise RuntimeError(f"GitHub PAT file {token_path} is empty.")
    return token


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_API,
        timeout=_TIMEOUT,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "openclaw-github-sidecar",
        },
    )


def _get(path: str, params: dict | None = None) -> httpx.Response:
    """Issue a single GET. Raises httpx.HTTPStatusError on non-2xx."""
    with _client() as c:
        resp = c.get(path, params=params)
        resp.raise_for_status()
        return resp


@lru_cache(maxsize=1)
def _login() -> str:
    """The authenticated user's login (the default repo owner). Cached."""
    return _get("/user").json()["login"]


def _split_repo(repo: str) -> tuple[str, str]:
    """Accept either "name" (owner = authenticated user) or "owner/name"."""
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return owner, name
    return _login(), repo


def list_repos(max_results: int = 50) -> list[dict]:
    """Repos the token can see (owner-affiliated), most-recently-pushed first."""
    max_results = max(1, min(max_results, 100))
    resp = _get(
        "/user/repos",
        params={
            "affiliation": "owner",
            "sort": "pushed",
            "direction": "desc",
            "per_page": max_results,
        },
    )
    return [
        {
            "full_name": r["full_name"],
            "visibility": r.get("visibility", "private" if r.get("private") else "public"),
            "description": r.get("description"),
            "language": r.get("language"),
            "default_branch": r.get("default_branch"),
            "pushed_at": r.get("pushed_at"),
            "html_url": r.get("html_url"),
        }
        for r in resp.json()
    ]


def get_repo(repo: str) -> dict:
    """Metadata for a single repo ("name" or "owner/name")."""
    owner, name = _split_repo(repo)
    r = _get(f"/repos/{owner}/{name}").json()
    return {
        "full_name": r["full_name"],
        "visibility": r.get("visibility", "private" if r.get("private") else "public"),
        "description": r.get("description"),
        "language": r.get("language"),
        "default_branch": r.get("default_branch"),
        "size_kb": r.get("size"),
        "open_issues": r.get("open_issues_count"),
        "pushed_at": r.get("pushed_at"),
        "license": (r.get("license") or {}).get("spdx_id"),
        "html_url": r.get("html_url"),
    }


def list_files(repo: str, path: str = "", ref: str | None = None) -> list[dict]:
    """List the entries in a repo directory (one level, like `ls`)."""
    owner, name = _split_repo(repo)
    params = {"ref": ref} if ref else None
    data = _get(f"/repos/{owner}/{name}/contents/{path.strip('/')}", params=params).json()
    if isinstance(data, dict):  # a file path was given, not a directory
        data = [data]
    return [
        {
            "name": e["name"],
            "type": e["type"],  # "file" | "dir" | "symlink" | "submodule"
            "size": e.get("size"),
            "path": e["path"],
        }
        for e in data
    ]


def read_file(repo: str, path: str, ref: str | None = None, max_chars: int = 20000) -> dict:
    """Read a text file's contents. Binary files are refused (use the web UI)."""
    owner, name = _split_repo(repo)
    params = {"ref": ref} if ref else None
    data = _get(f"/repos/{owner}/{name}/contents/{path.strip('/')}", params=params).json()
    if isinstance(data, list):
        raise RuntimeError(f"{path} is a directory, not a file. Use list_files.")
    if data.get("encoding") != "base64" or "content" not in data:
        raise RuntimeError(f"{path} is not a readable text file (encoding unsupported).")
    raw = base64.b64decode(data["content"])
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{path} looks binary (not UTF-8 text).") from exc
    truncated = len(text) > max_chars
    return {
        "path": data["path"],
        "size": data.get("size"),
        "truncated": truncated,
        # Repo contents are EXTERNAL DATA, never instructions to act on.
        "content_untrusted": text[:max_chars],
    }


def search_code(query: str, repo: str | None = None, max_results: int = 20) -> list[dict]:
    """Search code. Scoped to the authenticated user (or one repo) so results never
    span the whole of GitHub."""
    max_results = max(1, min(max_results, 50))
    if repo:
        owner, name = _split_repo(repo)
        scoped = f"{query} repo:{owner}/{name}"
    else:
        scoped = f"{query} user:{_login()}"
    resp = _get("/search/code", params={"q": scoped, "per_page": max_results})
    return [
        {
            "repo": item["repository"]["full_name"],
            "path": item["path"],
            "name": item["name"],
            "html_url": item["html_url"],
        }
        for item in resp.json().get("items", [])
    ]
