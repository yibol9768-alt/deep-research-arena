"""WikiOverlay — a tiny HTTP proxy in front of Kiwix that serves a
*modified* copy of selected articles, so we can detect agents that
answer from training prior instead of retrieved sandbox content.

Pattern:
  Kiwix runs on westd:8090 and is unmodified.
  WikiOverlay runs on westd:8091 and proxies to 8090 by default.
  For URLs declared in configs/wiki_overlay.yaml, the response body is
  rewritten before being returned — typically swapping a load-bearing
  fact for a fictional one.

Detection flow:
  - Task config sets `__WIKIPEDIA__` host = `localhost:8091`.
  - Agent fetches modified URL, sees the sandbox_value.
  - Agent answer is scored by `contamination_verifier.py`: did the
    agent's prose use the prior_value or the sandbox_value?
  - prior_value found → agent went from training prior, not the page.
  - sandbox_value found → agent actually retrieved the page.

Run on westd (any venv with httpx+fastapi works; we reuse .venv-camel):
  WIKI_UPSTREAM=http://localhost:8090 \
  WIKI_OVERLAY_CONFIG=/opt/deep_reserch/configs/wiki_overlay.yaml \
  uvicorn integrations.wiki_overlay.app:app --host 0.0.0.0 --port 8091
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

UPSTREAM = os.environ.get("WIKI_UPSTREAM", "http://localhost:8090").rstrip("/")
CONFIG_PATH = os.environ.get("WIKI_OVERLAY_CONFIG", "/opt/deep_reserch/configs/wiki_overlay.yaml")


def _load_config() -> dict:
    if not Path(CONFIG_PATH).exists():
        return {"articles": []}
    try:
        import yaml
        return yaml.safe_load(Path(CONFIG_PATH).read_text()) or {"articles": []}
    except Exception as e:
        return {"articles": [], "_load_error": str(e)}


_config = _load_config()


def _article_for_path(path: str) -> dict | None:
    """Return the overlay entry that matches the request path, or None."""
    for art in _config.get("articles", []):
        marker = art.get("path_contains", "") or art.get("url_suffix", "")
        if marker and marker in path:
            return art
    return None


def _apply_modifications(html: str, art: dict) -> tuple[str, list[dict]]:
    """For each modification in the article entry, replace the prior_value
    with the sandbox_value in the HTML body. Returns (modified_html, applied_log)."""
    applied = []
    for mod in art.get("modifications", []):
        prior = mod.get("prior_value")
        sand  = mod.get("sandbox_value")
        if not prior or not sand:
            continue
        n = html.count(prior)
        if n == 0:
            applied.append({"id": mod.get("id"), "prior": prior, "sandbox": sand,
                            "applied": 0, "note": "prior_value_not_found"})
            continue
        html = html.replace(prior, sand)
        applied.append({"id": mod.get("id"), "prior": prior, "sandbox": sand,
                        "applied": n})
    return html, applied


app = FastAPI(title="WikiOverlay (adversarial wiki injector)")


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "upstream": UPSTREAM,
        "config_path": CONFIG_PATH,
        "n_articles": len(_config.get("articles", [])),
        "load_error": _config.get("_load_error"),
    }


@app.get("/_overlay/log")
async def overlay_log():
    """Inspect what overlays are configured (for debugging)."""
    return JSONResponse({"articles": _config.get("articles", [])})


@app.get("/_overlay/reload")
async def reload_config():
    global _config
    _config = _load_config()
    return JSONResponse({"reloaded": True, "n_articles": len(_config.get("articles", []))})


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
async def proxy(path: str, request: Request):
    """Proxy everything to upstream Kiwix; rewrite specific articles."""
    url = f"{UPSTREAM}/{path}"
    qs = str(request.url.query)
    if qs:
        url += f"?{qs}"

    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            r = await client.request(request.method, url)
        except Exception as e:
            return PlainTextResponse(f"upstream error: {e}", status_code=502)

        ctype = r.headers.get("content-type", "")
        if "html" not in ctype.lower():
            return Response(
                content=r.content,
                status_code=r.status_code,
                headers={k: v for k, v in r.headers.items()
                         if k.lower() not in {"content-length", "content-encoding", "transfer-encoding", "connection"}},
                media_type=ctype or None,
            )

        body = r.text
        # Match against BOTH the requested path and the final upstream URL,
        # because Kiwix issues 302 from /A/Title to canonical /Title.
        match_haystack = "/" + path + " " + str(r.url)
        art = _article_for_path(match_haystack)
        if art:
            body, applied_log = _apply_modifications(body, art)
            # Inject a comment so we can tell from a fetched copy that it was overlaid.
            marker = f"<!-- wiki-overlay applied: {art.get('id')} {[a['id'] for a in applied_log]} -->"
            body = body.replace("</head>", marker + "</head>", 1) if "</head>" in body else (marker + body)

        return HTMLResponse(content=body, status_code=r.status_code)
