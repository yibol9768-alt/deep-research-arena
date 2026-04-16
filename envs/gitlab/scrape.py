"""GitLab (WebArena) scraper — thin wrapper around the GitLab v4 REST API.

Endpoints hit the local sandbox at http://localhost:8023 by default.
All functions return plain dicts/lists (JSON-serialisable).
"""

from __future__ import annotations

import os
import re
from typing import Any

import requests

GITLAB = os.environ.get("GITLAB", "http://localhost:8023").rstrip("/")

_SESS = requests.Session()
_SESS.headers.update({"Accept": "application/json"})

# WebArena default credentials
GITLAB_USER = "byteblaze"
GITLAB_PASS = "hello1234"
_TOKEN: str | None = None


def _ensure_token() -> str:
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    r = _SESS.post(
        f"{GITLAB}/oauth/token",
        data={
            "grant_type": "password",
            "username": GITLAB_USER,
            "password": GITLAB_PASS,
        },
        timeout=15,
    )
    if r.ok:
        _TOKEN = r.json().get("access_token", "")
        _SESS.headers["Authorization"] = f"Bearer {_TOKEN}"
        return _TOKEN
    # fallback: use private token API
    _SESS.headers["PRIVATE-TOKEN"] = ""
    return ""


def _api(path: str, **params: Any) -> Any:
    url = f"{GITLAB}/api/v4{path}"
    r = _SESS.get(url, params=params, timeout=20)
    if r.status_code == 401:
        _ensure_token()
        r = _SESS.get(url, params=params, timeout=20)
    return r.json() if r.ok else []


def search_projects(query: str, per_page: int = 20) -> list[dict]:
    """Search projects by name/description."""
    raw = _api("/projects", search=query, per_page=per_page,
               order_by="last_activity_at", sort="desc")
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "path": p["path_with_namespace"],
            "url": f"{GITLAB}/{p['path_with_namespace']}",
            "description": (p.get("description") or "")[:200],
            "stars": p.get("star_count", 0),
            "forks": p.get("forks_count", 0),
        }
        for p in raw
    ]


def list_project_issues(project_id: int, *, state: str = "all",
                        per_page: int = 20, page: int = 1,
                        labels: str | None = None) -> list[dict]:
    """List issues for a project."""
    params: dict[str, Any] = dict(state=state, per_page=per_page, page=page)
    if labels:
        params["labels"] = labels
    raw = _api(f"/projects/{project_id}/issues", **params)
    return [
        {
            "iid": i["iid"],
            "title": i["title"],
            "state": i["state"],
            "labels": i.get("labels", []),
            "author": i.get("author", {}).get("username", ""),
            "created_at": i.get("created_at", ""),
            "url": f"{GITLAB}/{i['references']['full'].replace('#', '/-/issues/')}",
            "description_preview": (i.get("description") or "")[:300],
        }
        for i in raw
    ]


def get_issue(project_id: int, issue_iid: int) -> dict:
    """Get a single issue with full description."""
    raw = _api(f"/projects/{project_id}/issues/{issue_iid}")
    if not raw:
        return {}
    return {
        "iid": raw.get("iid"),
        "title": raw.get("title", ""),
        "state": raw.get("state", ""),
        "labels": raw.get("labels", []),
        "author": raw.get("author", {}).get("username", ""),
        "created_at": raw.get("created_at", ""),
        "description": raw.get("description", ""),
        "url": f"{GITLAB}/{raw['references']['full'].replace('#', '/-/issues/')}",
        "upvotes": raw.get("upvotes", 0),
        "downvotes": raw.get("downvotes", 0),
    }


def get_issue_comments(project_id: int, issue_iid: int,
                       per_page: int = 20) -> list[dict]:
    """Get comments (notes) on an issue."""
    raw = _api(f"/projects/{project_id}/issues/{issue_iid}/notes",
               per_page=per_page)
    return [
        {
            "id": n["id"],
            "author": n.get("author", {}).get("username", ""),
            "body": (n.get("body") or "")[:500],
            "created_at": n.get("created_at", ""),
        }
        for n in raw
        if not n.get("system", False)  # skip system notes
    ]


def project_languages(project_id: int) -> dict[str, float]:
    """Get language breakdown for a project."""
    return _api(f"/projects/{project_id}/languages") or {}


def list_merge_requests(project_id: int, *, state: str = "all",
                        per_page: int = 10) -> list[dict]:
    """List merge requests for a project."""
    raw = _api(f"/projects/{project_id}/merge_requests",
               state=state, per_page=per_page)
    return [
        {
            "iid": mr["iid"],
            "title": mr["title"],
            "state": mr["state"],
            "author": mr.get("author", {}).get("username", ""),
            "url": mr.get("web_url", ""),
        }
        for mr in raw
    ]
