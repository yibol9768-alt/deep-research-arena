"""Serper/SearchXNG-to-Tavily adapter for the sandbox search shim.

A lightweight aiohttp server that speaks both the Google Serper wire
protocol and the SearchXNG wire protocol, translating requests to our
Tavily-compatible sandbox shim (``POST /search`` with ``{"query": ...}``).

Serper format (used by qx-agents SerperClient):
    Request:  POST /search  {"q": "...", "autocorrect": false}
              Header: X-API-KEY: <key>
    Response: {"organic": [{"link": "...", "title": "...", "snippet": "..."}]}

SearchXNG format (used by qx-agents SearchXNGClient):
    Request:  GET /search?q=...&format=json
    Response: {"results": [{"url": "...", "title": "...", "content": "..."}]}

Both are translated to the Tavily shim:
    Request:  POST /search  {"query": "...", "max_results": 10}
    Response: {"results": [{"url": "...", "title": "...", "content": "...", "score": ...}]}

Usage:
    server = SerperAdapter(shim_url="http://localhost:8081")
    port = await server.start()      # picks a free port
    # ... use the adapter ...
    await server.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


class SerperAdapter:
    """Bidirectional adapter: Serper/SearchXNG wire format <-> Tavily shim."""

    def __init__(self, shim_url: str = "http://localhost:8081"):
        self.shim_url = shim_url.rstrip("/")
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.port: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Start the adapter server.

        Args:
            host: Bind address.
            port: Port to listen on (0 = pick a free port).

        Returns:
            The actual port the server is listening on.
        """
        self._app = web.Application()
        self._app.router.add_post("/search", self._handle_serper_post)
        self._app.router.add_get("/search", self._handle_searchxng_get)
        self._app.router.add_get("/healthz", self._handle_healthz)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()

        # Retrieve the actual port (important when port=0)
        sock = self._site._server.sockets[0]
        self.port = sock.getsockname()[1]
        logger.info("SerperAdapter listening on %s:%d -> shim %s",
                     host, self.port, self.shim_url)
        return self.port

    async def stop(self) -> None:
        """Shut down the adapter server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        logger.info("SerperAdapter stopped")

    @property
    def url(self) -> str:
        """Base URL of the running adapter."""
        return f"http://127.0.0.1:{self.port}"

    # ------------------------------------------------------------------
    # Core: forward to the Tavily shim
    # ------------------------------------------------------------------

    async def _query_shim(self, query: str, max_results: int = 10) -> dict:
        """POST to the Tavily shim and return the raw JSON response."""
        async with aiohttp.ClientSession() as session:
            payload = {"query": query, "max_results": max_results}
            async with session.post(
                f"{self.shim_url}/search",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    # Serper POST handler
    # ------------------------------------------------------------------

    async def _handle_serper_post(self, request: web.Request) -> web.Response:
        """Handle a Serper-format POST /search request.

        Serper sends: {"q": "...", "autocorrect": false, "num": 10}
        Serper returns: {"organic": [{"link", "title", "snippet"}], ...}
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"error": "invalid JSON body"}, status=400
            )

        query = body.get("q", "")
        num = body.get("num", 10)
        if not query:
            return web.json_response(
                {"error": "missing 'q' field"}, status=400
            )

        logger.debug("Serper POST: q=%r num=%d", query, num)

        try:
            shim_resp = await self._query_shim(query, max_results=num)
        except Exception as e:
            logger.error("Shim query failed: %s", e)
            return web.json_response(
                {"error": f"shim error: {e}"}, status=502
            )

        # Translate Tavily -> Serper format
        organic = []
        for hit in shim_resp.get("results", []):
            organic.append({
                "title": hit.get("title", ""),
                "link": hit.get("url", ""),
                "snippet": hit.get("content", ""),
                "position": len(organic) + 1,
            })

        return web.json_response({
            "searchParameters": {"q": query, "type": "search"},
            "organic": organic,
        })

    # ------------------------------------------------------------------
    # SearchXNG GET handler
    # ------------------------------------------------------------------

    async def _handle_searchxng_get(self, request: web.Request) -> web.Response:
        """Handle a SearchXNG-format GET /search?q=...&format=json request.

        SearchXNG returns: {"results": [{"url", "title", "content"}]}
        which is the same shape our shim already produces.
        """
        query = request.query.get("q", "")
        if not query:
            return web.json_response(
                {"error": "missing 'q' parameter"}, status=400
            )

        page_length = int(request.query.get("pageLength", "10"))
        logger.debug("SearchXNG GET: q=%r", query)

        try:
            shim_resp = await self._query_shim(query, max_results=page_length)
        except Exception as e:
            logger.error("Shim query failed: %s", e)
            return web.json_response(
                {"error": f"shim error: {e}"}, status=502
            )

        # The Tavily shim response already has the SearchXNG-compatible
        # shape: {"results": [{"url", "title", "content", ...}]}
        # Just pass through the results.
        results = []
        for hit in shim_resp.get("results", []):
            results.append({
                "url": hit.get("url", ""),
                "title": hit.get("title", ""),
                "content": hit.get("content", ""),
            })

        return web.json_response({"results": results})

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "adapter": "serper"})
