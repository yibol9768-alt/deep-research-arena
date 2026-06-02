"""Parsing and observation rendering for the RL tool-action loop."""

from __future__ import annotations

import json
import re
from typing import Any

from .env import Action, CallTool, Cite, Finalize, Open, Read, ReadMemory, Search, WriteMemory


_DIRECTIVE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(SEARCH|OPEN|NOTE|CITE)\s*[:：]\s*(.+?)\s*$"
)
_NO_ARG_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?(READ|RECALL)\s*(?:[:：]\s*)?$")
_TOOL_RE = re.compile(
    r"(?ims)^\s*(?:[-*]\s*)?TOOL\s*[:：]\s*([A-Za-z0-9_\-]+)\s*(.*?)\s*$"
)
_FINALIZE_RE = re.compile(r"(?is)(?:^|\n)\s*(?:[-*]\s*)?FINALIZE\s*[:：]\s*(.*)$")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
_URL_RE = re.compile(r"https?://[^\s>)\"']+")


def parse_action(text: str) -> Action:
    """Parse a model directive into a single environment action.

    The parser intentionally accepts loose fenced or unfenced directives and
    falls back to a cheap memory read when the output is not actionable.
    """

    raw = str(text or "")
    # Qwen3 (and similar) emit a <think>...</think> reasoning block before the
    # actionable directive. Strip it so the directive is parsed from what
    # follows; an unterminated <think> (ran out of budget mid-reasoning) is also
    # dropped so we do not parse directives out of the reasoning itself.
    raw = re.sub(r"(?is)<think>.*?</think>", " ", raw)
    raw = re.sub(r"(?is)<think>.*$", " ", raw)
    raw = raw.strip()
    if not raw:
        return ReadMemory()

    json_action = _parse_json_action(raw)
    if json_action is not None:
        return json_action

    unwrapped = _strip_outer_fence(raw)
    if unwrapped != raw:
        json_action = _parse_json_action(unwrapped)
        if json_action is not None:
            return json_action

    for candidate in (unwrapped, raw):
        finalize = _FINALIZE_RE.search(candidate)
        if finalize:
            report = _clean_report(finalize.group(1))
            return Finalize(report)

    if "FINALIZE" in raw.upper() and _MARKDOWN_LINK_RE.search(raw):
        return Finalize(raw)

    for candidate in _candidate_blocks(raw):
        tool_match = _TOOL_RE.search(candidate)
        if tool_match:
            name = tool_match.group(1).strip()
            args = _parse_tool_args(tool_match.group(2))
            return CallTool(name, args)

        match = _DIRECTIVE_RE.search(candidate)
        if match:
            verb = match.group(1).upper()
            payload = _clean_payload(match.group(2))
            if verb == "SEARCH":
                return Search(payload)
            if verb == "OPEN":
                return Open(_extract_url(payload) or payload)
            if verb == "NOTE":
                return WriteMemory(payload)
            if verb == "CITE":
                return Cite(_extract_url(payload) or payload)

        no_arg = _NO_ARG_RE.search(candidate)
        if no_arg:
            verb = no_arg.group(1).upper()
            if verb == "READ":
                return Read()
            if verb == "RECALL":
                return ReadMemory()

    return ReadMemory()


def render_observation(observation: dict[str, Any]) -> str:
    """Render an environment observation as a compact tool-result message."""

    obs = dict(observation or {})
    lines = [
        "TOOL RESULT",
        f"last_action: {obs.get('last_action') or 'unknown'}",
        (
            "tool_calls: "
            f"{int(obs.get('tool_calls_used') or 0)} used, "
            f"{int(obs.get('tool_calls_remaining') or 0)} remaining"
        ),
    ]

    results = [hit for hit in (obs.get("search_results") or []) if isinstance(hit, dict)]
    if results:
        lines.append("search_results:")
        for idx, hit in enumerate(results[:5], start=1):
            title = _truncate(str(hit.get("title") or hit.get("url") or "untitled"), 90)
            url = str(hit.get("url") or "").strip()
            snippet = _truncate(str(hit.get("snippet") or ""), 160)
            lines.append(f"{idx}. {title}")
            if url:
                lines.append(f"   url: {url}")
            if snippet:
                lines.append(f"   snippet: {snippet}")
    else:
        lines.append("search_results: none")

    current_url = str(obs.get("current_url") or "").strip()
    current_page = str(obs.get("current_page_text") or "").strip()
    if current_url or current_page:
        lines.append("current_page:")
        if current_url:
            lines.append(f"url: {current_url}")
        if current_page:
            lines.append(f"text: {_truncate(current_page, 900)}")
        else:
            lines.append("text: not read yet")

    memory = [str(item).strip() for item in (obs.get("memory") or []) if str(item).strip()]
    if memory:
        lines.append("memory:")
        for idx, note in enumerate(memory[-8:], start=1):
            lines.append(f"{idx}. {_truncate(note, 280)}")
    else:
        lines.append("memory: empty")

    fetched = [str(url) for url in (obs.get("fetched_urls") or []) if str(url).strip()]
    if fetched:
        lines.append("fetched_urls:")
        lines.extend(f"- {url}" for url in fetched[-8:])

    cited = [str(url) for url in (obs.get("cited_urls") or []) if str(url).strip()]
    if cited:
        lines.append("cited_urls:")
        lines.extend(f"- {url}" for url in cited[-8:])

    report = str(obs.get("report_md") or "").strip()
    if report:
        lines.append(f"report_md: {_truncate(report, 1000)}")

    return "\n".join(lines)


def _parse_json_action(text: str) -> Action | None:
    payload = _json_payload(text)
    if payload is None:
        return None
    verb = str(
        payload.get("action")
        or payload.get("type")
        or payload.get("tool")
        or payload.get("name")
        or ""
    ).strip().lower()
    if not verb:
        return None
    if verb in {"tool", "call_tool", "calltool"}:
        tname = _clean_payload(
            payload.get("name") or payload.get("tool_name") or payload.get("tool") or ""
        )
        targs = payload.get("args") or payload.get("arguments") or payload.get("input") or {}
        return CallTool(tname, dict(targs) if isinstance(targs, dict) else {})
    if verb == "search":
        return Search(_clean_payload(payload.get("query") or payload.get("q") or ""))
    if verb == "open":
        url = _clean_payload(payload.get("url") or payload.get("link") or "")
        return Open(_extract_url(url) or url)
    if verb == "read":
        return Read()
    if verb in {"note", "write_memory", "memory_write"}:
        return WriteMemory(_clean_payload(payload.get("text") or payload.get("note") or ""))
    if verb in {"recall", "read_memory", "memory_read"}:
        return ReadMemory()
    if verb == "cite":
        url = _clean_payload(payload.get("url") or payload.get("link") or "")
        return Cite(_extract_url(url) or url)
    if verb == "finalize":
        return Finalize(
            _clean_report(
                payload.get("report_md")
                or payload.get("report")
                or payload.get("markdown")
                or payload.get("content")
                or ""
            )
        )
    return None


def _parse_tool_args(tail: str) -> dict[str, Any]:
    """Parse the arg tail of a ``TOOL: <name> <args>`` directive.

    Accepts three forms:
      - a trailing JSON object: ``{"url": "..."}`` -> ``json.loads``
      - whitespace key=value pairs: ``url=... kind=product`` (values coerced)
      - empty tail -> ``{}``
    """

    tail = str(tail or "").strip()
    if not tail:
        return {}
    if tail.startswith("{"):
        try:
            data = json.loads(tail)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return data
    args: dict[str, Any] = {}
    for token in tail.split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        key = key.strip()
        if not key:
            continue
        args[key] = _coerce_scalar(value.strip())
    return args


def _coerce_scalar(value: str) -> Any:
    value = value.strip().strip("\"'")
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _json_payload(text: str) -> dict[str, Any] | None:
    candidate = _strip_outer_fence(str(text or "").strip())
    if candidate.lower().startswith("json\n"):
        candidate = candidate.split("\n", 1)[1].strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _candidate_blocks(text: str) -> list[str]:
    blocks = [text, _strip_outer_fence(text)]
    blocks.extend(match.group(1).strip() for match in re.finditer(r"(?is)```[a-zA-Z0-9_-]*\n(.*?)```", text))
    out: list[str] = []
    for block in blocks:
        if block and block not in out:
            out.append(block)
    return out


def _strip_outer_fence(text: str) -> str:
    stripped = str(text or "").strip()
    match = re.fullmatch(r"(?is)```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```", stripped)
    return match.group(1).strip() if match else stripped


def _clean_payload(value: Any) -> str:
    payload = str(value or "").strip()
    payload = payload.strip("` \t\r\n")
    if len(payload) >= 2 and payload[0] == payload[-1] and payload[0] in {"'", '"'}:
        payload = payload[1:-1].strip()
    if payload.startswith("<") and payload.endswith(">"):
        payload = payload[1:-1].strip()
    return payload


def _clean_report(value: Any) -> str:
    report = str(value or "").strip()
    return _strip_outer_fence(report)


def _extract_url(text: str) -> str | None:
    link = _MARKDOWN_LINK_RE.search(text)
    if link:
        return link.group(1).rstrip(".,;")
    url = _URL_RE.search(text)
    if url:
        return url.group(0).rstrip(".,;")
    return None


def _truncate(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 12)].rstrip() + " [truncated]"


__all__ = ["parse_action", "render_observation"]
