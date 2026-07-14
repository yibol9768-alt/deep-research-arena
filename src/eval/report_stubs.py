"""Centralized runner-failure / stub detection for research reports.

A research "report" produced by a Deep Research Arena runner is a markdown
answer. When the runner itself fails (timeout, crash, framework exception,
empty output) it emits a short placeholder string instead of a report. Those
placeholders must never be scored as if they were a genuine 0.0 answer: a
broken lane is not the same signal as an agent that produced a real but weak
report, and conflating the two silently corrupts every downstream aggregate.

This module is the single source of truth for that distinction. The two
prefix regexes below were originally defined in
``scripts/build_deep_leaderboard.py`` and are re-exported from there so
existing imports keep working.

``classify_report(text)`` returns exactly one of:

  "ok"                  real report; safe to score
  "stub_timeout"        raw parenthesized single-line runner message, e.g.
                        "(opencode timeout after 360s)" or
                        "(empty flowsearcher report)"
  "stub_runner_failure" "(<Agent> produced no report after Ns, exit=N)" head
  "stub_exception"      "(<Agent> error: ...)" / "(<Agent> stderr: ...)" head
  "too_short"           under the length floor and carrying no markdown
                        structure

The classifier is deliberately conservative on the "ok" side: a genuine
markdown report must never be classified as a stub.
"""

from __future__ import annotations

import re

# Report shorter than this and lacking any markdown structure is treated as a
# non-report stub. A short answer that still carries markdown (heading, list,
# link, table) stays "ok" so a terse-but-real report is never dropped.
MIN_REPORT_CHARS = 100

# Runner-failure placeholder pattern: e.g.
#   "(DeerFlow produced no report after 1256s, exit=1)"
#   "(STORM produced no report after 600s, exit=137)"
# The agent crashed; any markdown that follows the marker is stdout-tail noise,
# not a real research report.
_RUNNER_FAILURE_PREFIX_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+produced no report\s+after\s+\d+\s*s\s*,\s*exit\s*=\s*\d+\s*\)",
    re.IGNORECASE,
)
# Framework-exception placeholder produced when the runner raises a Python
# exception mid-run. Examples:
#   "(qx-agents error: ValidationError: 2 validation errors for ...)"
#   "(qx-agents error: IndexError: list index out of range)"
#   "(qx stderr: Traceback (most recent call last):..."
# These can carry a long traceback tail, so a length check alone misses them.
_RUNNER_EXCEPTION_PREFIX_RE = re.compile(
    r"^\(\s*[A-Za-z][\w\- ]*\s+(error|stderr)\s*:",
    re.IGNORECASE,
)
# Native open_deep_research returns these strings as ordinary graph values
# when its final/compression model call fails. They are framework exceptions,
# not terse research reports, even when the embedded provider payload pushes
# them above the generic short-output floor.
_NATIVE_EXCEPTION_PREFIX_RE = re.compile(
    r"^Error\s+(generating\s+final|synthesizing\s+research)\s+report\s*:",
    re.IGNORECASE,
)
# Raw parenthesized single-line runner message: the entire answer is one
# parenthesized line, e.g. "(opencode timeout after 360s)",
# "(empty flowsearcher report)", "(qx-agents produced no report)". The
# ``[^\n]`` class forbids interior newlines, so a multi-paragraph markdown
# report can never match this pattern.
_TIMEOUT_STUB_RE = re.compile(r"^\(\s*[A-Za-z][^\n]*\)\Z")

# Markdown-structure signals used to spare a short-but-real report from the
# length floor. Any one hit is enough.
_MARKDOWN_STRUCTURE_RE = re.compile(
    r"^#{1,6}\s"                 # ATX heading
    r"|^\s*[-*+]\s+\S"           # bullet list item
    r"|^\s*\d+\.\s+\S"           # ordered list item
    r"|^\s*\|.+\|"               # table row
    r"|^>\s"                     # blockquote
    r"|```"                      # code fence
    r"|\[[^\]]+\]\([^)]+\)"      # inline link
    r"|\*\*\S",                  # bold span
    re.MULTILINE,
)

# Ordered so the more specific failure prefixes win over the generic
# single-line and length fallbacks.
_STUB_PREFIX_CLASSIFIERS = (
    (_RUNNER_FAILURE_PREFIX_RE, "stub_runner_failure"),
    (_RUNNER_EXCEPTION_PREFIX_RE, "stub_exception"),
    (_NATIVE_EXCEPTION_PREFIX_RE, "stub_exception"),
    (_TIMEOUT_STUB_RE, "stub_timeout"),
)

_ALL_CLASSES = (
    "ok",
    "stub_timeout",
    "stub_runner_failure",
    "stub_exception",
    "too_short",
)


def _has_markdown_structure(text: str) -> bool:
    return bool(_MARKDOWN_STRUCTURE_RE.search(text))


def classify_report(text: str | None) -> str:
    """Classify a report body as one of the five report classes.

    Conservative by construction: only a leading runner-failure marker, a
    whole-answer single parenthesized line, or a sub-floor answer with no
    markdown structure is ever called a stub. A genuine markdown report
    returns "ok".
    """
    if text is None:
        return "too_short"
    # Strip a UTF-8 BOM the runners sometimes prepend, plus surrounding
    # whitespace, so the leading-prefix and single-line checks see the real
    # first and last characters.
    s = text.lstrip("\ufeff").strip()
    if not s:
        return "too_short"
    for pattern, label in _STUB_PREFIX_CLASSIFIERS:
        if pattern.match(s):
            return label
    if len(s) < MIN_REPORT_CHARS and not _has_markdown_structure(s):
        return "too_short"
    return "ok"


def is_stub(text: str | None) -> bool:
    """True when the report body is any non-"ok" class."""
    return classify_report(text) != "ok"
