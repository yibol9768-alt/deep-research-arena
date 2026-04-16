"""Minimal Playwright-based task runner for fixed-env benchmarks.

Responsibilities:
  1. Substitute site placeholders (__SHOPPING__ etc.) in a WebArena-style task config.
  2. Launch a Playwright browser, navigate to start_url.
  3. Invoke a user-supplied `oracle` or `agent` callback that produces an answer string.
  4. Run appropriate verifiers against the task's eval spec.

The runner itself is Agent-agnostic: whatever callable you pass gets the
`Page` and the resolved task dict, and must return a str answer.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.verifiers import (
    StringVerifier,
    URLVerifier,
    DOMVerifier,
    ReportVerifier,
    CitationVerifier,
    VerifierResult,
)


AgentFn = Callable[["Any", dict], str]  # (playwright_page, task_cfg) -> answer


@dataclass
class RunResult:
    task_id: int
    passed: bool
    score: float
    elapsed_sec: float
    answer: str
    eval_types: list[str]
    verifier_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "score": self.score,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "answer": self.answer,
            "eval_types": self.eval_types,
            "verifier_results": self.verifier_results,
            "error": self.error,
        }


class PlaywrightRunner:
    """Drive one task end-to-end: env is assumed up, runner handles browser+eval."""

    def __init__(
        self,
        site_map: dict[str, str] | None = None,
        headless: bool = True,
        timeout_ms: int = 60_000,
    ) -> None:
        # Site env vars fallback chain: explicit arg -> env var -> localhost default ports
        default_map = {
            "SHOPPING": os.environ.get("SHOPPING", "http://localhost:7770"),
            "SHOPPING_ADMIN": os.environ.get("SHOPPING_ADMIN", "http://localhost:7780/admin"),
            "REDDIT": os.environ.get("REDDIT", "http://localhost:9999"),
            "GITLAB": os.environ.get("GITLAB", "http://localhost:8023"),
            "MAP": os.environ.get("MAP", "http://localhost:3000"),
            "WIKIPEDIA": os.environ.get("WIKIPEDIA", "http://localhost:8888"),
        }
        self.site_map = {**default_map, **(site_map or {})}
        self.headless = headless
        self.timeout_ms = timeout_ms

    def resolve(self, task_cfg: dict) -> dict:
        """Replace __SHOPPING__ etc. placeholders in URLs and eval refs."""
        cfg = json.loads(json.dumps(task_cfg))  # deep copy

        def sub(s: str) -> str:
            for key, url in self.site_map.items():
                s = s.replace(f"__{key}__", url)
            return s

        if isinstance(cfg.get("start_url"), str):
            cfg["start_url"] = sub(cfg["start_url"])
        ev = cfg.get("eval") or {}
        if isinstance(ev.get("reference_url"), str):
            ev["reference_url"] = sub(ev["reference_url"])
        for item in ev.get("program_html", []) or []:
            if isinstance(item.get("url"), str):
                item["url"] = sub(item["url"])
        return cfg

    def run(self, task_cfg: dict, agent: AgentFn) -> RunResult:
        """Execute one task, return RunResult."""
        from playwright.sync_api import sync_playwright  # local import (heavy dep)

        cfg = self.resolve(task_cfg)
        tid = cfg["task_id"]
        t0 = time.time()
        answer = ""
        err: str | None = None

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=self.headless)
                ctx = browser.new_context()
                # storage_state support (optional)
                state_path = cfg.get("storage_state")
                if state_path and Path(state_path).exists():
                    ctx = browser.new_context(storage_state=state_path)
                page = ctx.new_page()
                page.set_default_timeout(self.timeout_ms)
                start_url = cfg.get("start_url") or ""
                if start_url and start_url != "about:blank":
                    page.goto(start_url)

                # Agent / oracle produces an answer
                answer = agent(page, cfg) or ""

                # Run verifiers
                results, total = self._verify(cfg, answer, page)

                browser.close()

                passed = total > 0
                return RunResult(
                    task_id=tid,
                    passed=passed,
                    score=total,
                    elapsed_sec=time.time() - t0,
                    answer=answer,
                    eval_types=cfg.get("eval", {}).get("eval_types", []),
                    verifier_results=results,
                )
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            return RunResult(
                task_id=tid,
                passed=False,
                score=0.0,
                elapsed_sec=time.time() - t0,
                answer=answer,
                eval_types=cfg.get("eval", {}).get("eval_types", []),
                error=err,
            )

    def _verify(self, cfg: dict, answer: str, page: Any) -> tuple[list[dict], float]:
        # WebArena's composite: product of all enabled evaluators (0 or 1 each, mostly).
        eval_types = cfg.get("eval", {}).get("eval_types", [])
        results: list[dict] = []
        total = 1.0
        for et in eval_types:
            if et == "string_match":
                r = StringVerifier().verify(task_config=cfg, answer=answer, page=page)
            elif et == "url_match":
                r = URLVerifier().verify(task_config=cfg, answer=answer, page=page)
            elif et == "program_html":
                r = DOMVerifier().verify(task_config=cfg, answer=answer, page=page)
            elif et == "report_match":
                r = ReportVerifier().verify(task_config=cfg, answer=answer, page=page)
            elif et == "citation_check":
                r = CitationVerifier().verify(task_config=cfg, answer=answer, page=page)
            else:
                r = VerifierResult(score=0.0, passed=False, details={"reason": f"unsupported eval_type: {et}"})
            results.append({"type": et, "score": r.score, "passed": r.passed, "details": r.details})
            total *= r.score
        if not eval_types:
            total = 0.0
        return results, total
