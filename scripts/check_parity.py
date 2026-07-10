#!/usr/bin/env python3
"""Fail the build when a lane adapter re-introduces a scored-axis injection.

The 2026-07-06 lane audit ordered several injections removed. Two days later,
three of them were still in the tree, and one that had been removed from a
runner survived in a second copy reachable through another entrypoint. Prose in
a markdown file does not keep code honest.

This scans the live adapter surface for the patterns `config/lane_protocol.yaml`
declares forbidden, and exits non-zero on any hit. It is deliberately a text
scan: it catches the pattern wherever it lands, including in a driver script
that is built as a string and exec'd in a subprocess, which is where several of
these lived.

    python3 scripts/check_parity.py            # exit 1 on violation
    python3 scripts/check_parity.py --list     # show what is scanned

Adding a legitimate exception means declaring it in `lane_protocol.yaml` under
that lane's `deviations`, not adding a pragma here.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LANE_PROTOCOL = ROOT / "config" / "lane_protocol.yaml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_LANE_REQUIRED_FIELDS = ("delivery", "fetch_observable", "fetch_mode", "deviations")
_LANE_DELIVERIES = {"in_process", "subprocess", "cli"}
_FETCH_MODES = {
    "shim_extract",
    "shim_fetch",
    "direct_requests",
    "direct_aiohttp",
    "direct_curl",
    "none",
    "unknown",
}
_UNOBSERVABLE_FETCH_MODES = {
    "direct_requests",
    "direct_aiohttp",
    "direct_curl",
    "unknown",
}

SCANNED = [
    "scripts/run_deep_task.py",
    "scripts/runners/*.py",
    "integrations/agents/**/*.py",
]

# Each rule: (id, regex, why). Regexes are matched case-insensitively against
# the file text with comments stripped, so the explanatory comments left behind
# by the removals do not trip their own rule.
# A quantifier is any of the ways a prompt names an amount. `word_count` used to
# anchor on the literal "at least", and `qx_runner.py:322` shipped
# `output_length="about 1500 words"` straight past it. Six of seven paraphrases
# evaded the rule set when probed. A checker's coverage is the ceiling of its
# credibility, so the quantifier is factored out and shared.
_NUMBER = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|(?:a\s+)?dozen|dozens?)"
)
_QTY = (r"(?:at least|no fewer than|not fewer than|no less than|minimum of|"
        r"a minimum of|at minimum|about|around|approximately|roughly|"
        r"aim for(?: at least)?|target|~|>=|≥|>|over|more than|upwards of)?\s*"
        + _NUMBER + r"\s*\+?")
# A SOFT quantifier names an amount without a numeral. "cite multiple distinct
# source URLs" steers reach's numerator exactly as "cite 5 URLs" does, and _QTY
# (which REQUIRES a number) walked straight past it -- the same evasion class
# search_breadth already closes for queries (SPEC_ISSUES §2, citation_count
# entry). Mirroring search_breadth's design, the soft form must be anchored to
# an instructing verb/requirement in the same clause: a descriptive "the search
# returned various links" is not a steer, "cite various links" is.
_SOFT_QTY = r"(?:multiple|several|many|numerous|various|diverse|plenty of|dozens of)"
_SOFT_QTY_STEER = (
    r"(?:cite|citing|cites|include|includes|including|provide|provides|use|"
    r"list|produce|add|give|gather|collect|contain|contains|must have|"
    r"should have|needs?|require[sd]?|with)\s+(?:at\s+)?" + _SOFT_QTY)

RULES: list[tuple[str, str, str]] = [
    ("citation_count",
     # Catch the count-noun steer however it is phrased: "at least N", "aim for
     # >= N", ">= N", "N different/distinct source URLs". The count is reach's
     # numerator; the earlier ">= 20 distinct sandbox URLs" / "at least 20
     # different source URLs" evasions slipped past the "at least N" form.
     # `\d+` alone let "cite at least five distinct source URLs" through: the
     # exact evasion class `_QTY` was built for, on the rule guarding reach's
     # own numerator. Number words are spelled out here too. `_SOFT_QTY_STEER`
     # closes the numeral-free form ("cite multiple distinct source URLs"),
     # which _QTY cannot see because it requires a number.
     r"(?:" + _QTY + r"|" + _SOFT_QTY_STEER + r")"
     r"\s+(?:exact |distinct |different |separate )?"
     r"(?:sandbox |wikipedia |wiki |source )?"
     r"(?:url|citation|article citation|link|source url)s?",
     "tells one lane how many citations to produce; reach's numerator"),
    ("invalid_unless_urls",
     r"invalid unless.{0,80}url",
     "threatens the model with rejection unless it cites more; a rubric leak"),
    ("word_count",
     _QTY + r"\s*(?:words|characters)\b",
     "steers completeness"),
    ("paragraph_count",
     _QTY + r"\s*(?:substantive )?paragraphs\b",
     "steers completeness"),
    ("search_count",
     r"(?:make|run|perform|do|issue)\s+" + _QTY + r"\s*(?:to\s*\d+\s*)?"
     r"(?:focused |separate |distinct )?(?:searches|search calls|queries)\b",
     "steers retrieval behaviour toward the scorer"),
    ("search_breadth",
     r"(?:issue|make|run|perform|do|use|start(?:\s+by)?(?:\s+searching)?(?:\s+with)?)"
     r"[^.\n]{0,50}\b(?:multiple|several|many|various|diverse)\b[^.\n]{0,30}"
     r"(?:searches|search calls|queries)\b",
     "prescribes a multi-query research strategy to one lane"),
    ("fetch_all_results",
     r"(?:"
     r"(?:fetch|open|visit|read|scrape)\s+(?:each|every|all)\s+"
     r"(?:promising |relevant |returned )?(?:result|page|url|source)s?\b"
     r"|for\s+(?:each|every|all)\s+(?:promising |relevant |returned )?"
     r"(?:result|page|url|source)s?\b[^.\n]{0,40}\b"
     r"(?:fetch|open|visit|read|scrape)\b"
     r")",
     "prescribes fetch breadth, which moves proof-of-fetch and completeness"),
    ("cross_reference",
     r"cross[- ](?:reference|check|validate)\b[^.\n]{0,100}"
     r"(?:sources?|magento|postmill|kiwix|catalog|forum|encyclopedia)",
     "prescribes cross-source coverage, which steers reach/completeness"),
    ("citation_format",
     r"cite every factual claim|every factual claim (?:must be|needs)|"
     r"inline citations?\s+(?:and|with)\s+(?:a\s+)?references section|"
     r"use markdown (?:links|citations)",
     "prescribes citation density"),
    ("example_url",
     r"e\.g\.\s*\[[^\]]+\]\(https?://localhost",
     "a literal example URL; observed copied verbatim as the only citation"),
    ("wiki_url_rewrite",
     # Match the rewrite CODE shape in either backslash form: the ldr comment had
     # `[^\\s` (double) and the lcdr live code had `[^\s` (single). The old rule
     # required the double form and let the single-backslash lcdr copy through.
     #
     # Neither form matched the two copies that were still LIVE on 2026-07-09:
     # `src/shim_intercept.py` and the driver source string `run_deep_task`
     # injects into a subprocess venv. Both took a model-emitted
     # `en.wikipedia.org/wiki/X` and served it the sandbox Kiwix page. So the
     # rule now anchors on what the rewrite must produce -- the kiwix content
     # path -- next to the public host, however the code spells it.
     r"en\.wikipedia\.org/wiki/\(\[\^\\{1,2}s|_rewrite_wiki_url|"
     r"en\.wikipedia\.org[\s\S]{0,400}?/content/wikipedia_en_all_nopic|"
     r"/content/wikipedia_en_all_nopic[\s\S]{0,400}?en\.wikipedia\.org",
     "rewrites model-emitted public URLs into sandbox URLs: a lane that drifted "
     "out of the sandbox on parametric memory is handed the corpus page and "
     "scored as if it had retrieved it"),
    ("masked_domain_rewrite",
     # The wiki rule above catches the en.wikipedia.org -> Kiwix laundering. The
     # SHOPPING and FORUM sandboxes have the same trap in their two mask domains:
     # onestopmarket.com (localhost:7770) and postmill.net (localhost:9999), plus
     # kiwipedia.org (the wiki mask domain, localhost:8090). ldr_runner._unmask
     # carried an UNCONDITIONAL literal-`replace` tail rewriting these three back
     # to localhost even when masking was off, so a model emitting the public
     # domain from parametric memory was handed the sandbox address and scored as
     # grounded. The FROM-side is a hardcoded PUBLIC-domain literal: that shape
     # rewrites arbitrary drift and is forbidden. The legitimate mask ROUND TRIP
     # (declared `mask_round_trip`) reverses only what the harness masked and does
     # so through the VARIABLE `_UNMASK_MAP` loop (replace(masked, original)),
     # never a hardcoded public-domain literal -- so it does not match here, and a
     # dict entry `"...": "http://onestopmarket.com"` (mask map value) has no
     # `.replace(` before it either.
     r"\.replace\(\s*['\"](?:https?://)?"
     r"(?:onestopmarket\.com|postmill\.net|kiwipedia\.org)",
     "rewrites a model-emitted sandbox mask domain (onestopmarket.com / "
     "postmill.net / kiwipedia.org) into localhost off any mask round trip: "
     "parametric drift laundered into sandbox grounding, this lane only"),
    ("attach_sources",
     r"def _attach_sources|\+ \"\\n\\n### Sources",
     "writes URLs into the report on the framework's behalf"),
    ("append_bibliography",
     r"\"\\n\\n#{1,3} ?(?:References|Sources)|result = result \+ bibliography",
     "appends the lane's URL table to the scored report"),
    ("prefetched_evidence",
     r"PREFETCHED SANDBOX EVIDENCE|Sandbox evidence gathered through",
     "harness performs the retrieval and pastes results into the prompt"),
    ("repair_on_score",
     r"previous (?:final )?report was (?:invalid|too short)",
     "gives one lane a second attempt keyed on a scored quantity"),
    ("weak_gate_on_reach",
     r"sandbox_url_count\(\w+\)\s*<\s*\w*min_urls",
     "harness gates capture on the quantity the scorer measures"),
    ("backbone_keyed_behaviour",
     # Every way an adapter can spell "am I on backbone X?", not just the `in`
     # form. The historical incident was `model.startswith("deepseek")` deciding
     # intent masking; the original rule matched only `"name" in model`, so the
     # incident's own spelling would have sailed past it on re-introduction
     # (SPEC_ISSUES §2, backbone-rule entry). Covered forms:
     #   "name" in model / backbone            (original)
     #   model.startswith("name") / model.lower().startswith(("name", ...))
     #   model == "name"  /  backbone == "name"
     # NOTE the proxy directories (integrations/ds_proxy, integrations/
     # llm_gateway) are deliberately NOT in SCANNED for this rule: their
     # per-backbone branches implement the policy lane_protocol.yaml DECLARES
     # (thinking per_backbone, max_output_tokens_exceptions), and
     # preflight.check_backbone_sampling asserts code matches declaration there.
     # This rule guards the ADAPTER surface, where no backbone branch is ever
     # declared or legitimate.
     r"[\"']\s*(?:deepseek|qwen|glm|gpt-4|claude)[\w.-]*\s*[\"']\s*in\s+"
     r"\(?\s*(?:model|backbone)"
     r"|(?:model|backbone)\w*(?:\.lower\(\))?\.startswith\(\s*\(?\s*"
     r"[\"'](?:deepseek|qwen|glm|gpt-4|claude)"
     r"|(?:model|backbone)\w*(?:\.lower\(\))?\s*==\s*"
     r"[\"'](?:deepseek|qwen|glm|gpt-4|claude)",
     "branches on the backbone's NAME, so swapping the backbone also swaps the "
     "harness. 'same harness, change the model' stops being a one-variable "
     "experiment, and the cross-backbone board means nothing"),
]

# --- env-budget parity (added 2026-07-09, P4) ------------------------------
#
# The RULES above scan the PROMPT for scored-axis steers. They say nothing about
# BUDGET. A lane's step cap, results-per-search, and token/context window are
# never in the prompt, yet each bounds how much the agent can retrieve, hold, and
# write, and so moves reach and completeness exactly as a prompt steer would.
# Until 2026-07-09 three lanes carried undeclared per-lane budgets while their
# `deviations` read `[]`: smolagents (MAX_STEPS=24, SEARCH_MAX_RESULTS=6),
# deerflow (TOKEN_LIMIT), opencode (CONTEXT_LIMIT), ldr (SEARCH_MAX_RESULTS).
#
# This rule makes code and declaration agree: every
# `os.environ.get("<PREFIX>_<SUFFIX>")` read in the adapter surface, for the four
# budget suffixes below, must be named in a `{kind: budget}` deviation for the
# mapped lane in lane_protocol.yaml. Code has it, declaration does not -> violation.
# It deliberately does NOT judge the VALUE: heterogeneous frameworks share no
# common step or token unit, so equalising the number would be theatre. It forces
# the asymmetry to be WRITTEN DOWN where the board can disclose it, which is the
# same discipline the prompt RULES enforce for the prompt.
ENV_BUDGET_SUFFIXES = ("MAX_STEPS", "SEARCH_MAX_RESULTS", "TOKEN_LIMIT", "CONTEXT_LIMIT")

# Maps the env-var prefix to its lane key in lane_protocol.yaml. A budget env
# whose prefix is absent here is itself a violation (fail loud): add the lane and
# declare the budget rather than let an unmapped prefix slip the audit.
ENV_BUDGET_PREFIX_TO_LANE = {
    "SMOLAGENTS": "smolagents",
    "DEERFLOW": "deerflow",
    "OPENCODE": "opencode",
    "LDR": "ldr",
}

# Matches os.environ.get("NAME"...) and os.getenv("NAME"...) with either quote.
# The NAME is split against ENV_BUDGET_SUFFIXES in code (the suffixes contain
# their own underscores, e.g. SEARCH_MAX_RESULTS, so a single regex group is
# simpler and less brittle than encoding the split in the pattern).
_ENV_GET_RE = re.compile(r"os\.(?:environ\.get|getenv)\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]")

# `[ \t]*`, not `\s*`: `\s` matches newlines, so `^\s*#.*$` under re.M swallowed
# the blank lines ABOVE a comment, collapsing them and shifting every reported
# line number below (ldr_runner.py drifted 549 -> 509). Horizontal whitespace
# only keeps the promise in _strip_prose's docstring that line numbers stay true.
_COMMENT = re.compile(r"^[ \t]*#.*$", re.M)


def _strip_prose(text: str) -> str:
    """Blank out comments and docstrings, keeping every other string literal.

    The removals above left long explanatory comments quoting the exact strings
    they deleted. Scanning raw text would flag those, teaching the next person
    to delete the explanation rather than keep the fix.

    Docstrings must be found with `ast`, not a `\"\"\"...\"\"\"` regex. Several
    lane prompts ARE triple-quoted strings (the CLI runners build their system
    prompt as an f-string here-doc), so a regex that strips every triple-quoted
    block would blind this checker to precisely the injections it exists to
    catch. Lines are blanked rather than deleted so reported line numbers stay
    true to the file.
    """
    lines = text.split("\n")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _COMMENT.sub("", text)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            for i in range(first.lineno - 1, first.end_lineno):
                lines[i] = ""
    return _COMMENT.sub("", "\n".join(lines))


def iter_files() -> list[Path]:
    out: list[Path] = []
    for pat in SCANNED:
        out.extend(sorted(ROOT.glob(pat)))
    return [p for p in out if p.is_file() and p.suffix == ".py"]


def scan_lane_inventory() -> list[tuple[Path, int, str, str]]:
    """Require one exact, well-formed contract for every comparative runner.

    Auto-discovery used to make adding a ``*_runner.py`` sufficient to enter the
    benchmark. That silently exposed eight lanes absent from the protocol. The
    formal inventory is now fail-closed in both directions: a runtime lane with
    no declaration is unaudited, while a declaration with no runtime runner can
    create a queue made entirely of missing work.
    """
    rule_id = "lane_inventory"
    violations: list[tuple[Path, int, str, str]] = []
    try:
        doc = yaml.safe_load(LANE_PROTOCOL.read_text(encoding="utf-8")) or {}
        lanes = doc.get("lanes")
        if not isinstance(lanes, dict) or not lanes:
            raise ValueError("lanes must be a non-empty mapping")
    except Exception as e:  # noqa: BLE001: malformed protocol must fail loud
        return [(LANE_PROTOCOL, 0, rule_id,
                 f"cannot read lane inventory: {type(e).__name__}: {e}")]

    try:
        from scripts.run_deep_task import RUNNERS, runner_choices

        if not isinstance(RUNNERS, dict) or not RUNNERS:
            raise ValueError("RUNNERS must be a non-empty mapping")
        runtime = set(RUNNERS)
        cli_choices = set(runner_choices())
    except Exception as e:  # noqa: BLE001: runtime import failure is a violation
        return [(ROOT / "scripts/run_deep_task.py", 0, rule_id,
                 f"cannot load runtime runner inventory: {type(e).__name__}: {e}")]

    declared = set(lanes)
    undeclared = sorted(runtime - declared)
    missing_runtime = sorted(declared - runtime)
    if undeclared or missing_runtime:
        violations.append((LANE_PROTOCOL, 0, rule_id,
            "RUNNERS/lane_protocol mismatch: "
            f"runner_without_declaration={undeclared}, "
            f"declared_without_runner={missing_runtime}"))
    if cli_choices != runtime:
        violations.append((ROOT / "scripts/run_deep_task.py", 0, rule_id,
            "argparse runner choices drifted from RUNNERS: "
            f"choices_only={sorted(cli_choices - runtime)}, "
            f"runners_only={sorted(runtime - cli_choices)}"))

    # The planner must consume the same exact set, not maintain a third list.
    try:
        from scripts.plan_full_leaderboard import _declared_agents

        planned = set(_declared_agents())
        if planned != declared:
            violations.append((ROOT / "scripts/plan_full_leaderboard.py", 0,
                rule_id, "planner inventory drifted from lane_protocol: "
                f"planner_only={sorted(planned - declared)}, "
                f"protocol_only={sorted(declared - planned)}"))
    except Exception as e:  # noqa: BLE001: a planner that cannot prove parity fails
        violations.append((ROOT / "scripts/plan_full_leaderboard.py", 0,
            rule_id, f"planner cannot establish exact lane inventory: "
            f"{type(e).__name__}: {e}"))

    for lane, entry in lanes.items():
        if not isinstance(lane, str) or not lane.strip():
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"invalid lane name {lane!r}"))
            continue
        if not isinstance(entry, dict):
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} contract must be a mapping"))
            continue
        missing = [field for field in _LANE_REQUIRED_FIELDS if field not in entry]
        if missing:
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} is missing required fields: {missing}"))
            continue
        delivery = entry.get("delivery")
        if delivery not in _LANE_DELIVERIES:
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} has unknown delivery {delivery!r}; "
                f"expected one of {sorted(_LANE_DELIVERIES)}"))
        observable = entry.get("fetch_observable")
        mode = entry.get("fetch_mode")
        if not isinstance(observable, bool):
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} fetch_observable must be a boolean"))
        if mode not in _FETCH_MODES:
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} has unknown fetch_mode {mode!r}; "
                f"expected one of {sorted(_FETCH_MODES)}"))
        if observable is True and mode in _UNOBSERVABLE_FETCH_MODES:
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} claims fetch_observable=true with bypass/unknown "
                f"fetch_mode={mode!r}"))
        deviations = entry.get("deviations")
        if not isinstance(deviations, list):
            violations.append((LANE_PROTOCOL, 0, rule_id,
                f"lane {lane!r} deviations must be a list"))
        else:
            for idx, deviation in enumerate(deviations):
                if (not isinstance(deviation, dict)
                        or not str(deviation.get("kind", "")).strip()
                        or not str(deviation.get("detail", "")).strip()):
                    violations.append((LANE_PROTOCOL, 0, rule_id,
                        f"lane {lane!r} deviation[{idx}] must contain non-empty "
                        "kind and detail"))
    return violations


def _declared_budget_details() -> dict[str, list[str]]:
    """Map each lane to the `detail` strings of its {kind: budget} deviations.

    Reading fails loud: a caller that gets an empty map for a lane that has code
    budgets will report violations, which is the correct signal when the
    contract file is missing or malformed.
    """
    data = yaml.safe_load(LANE_PROTOCOL.read_text(encoding="utf-8"))
    lanes = (data or {}).get("lanes") or {}
    out: dict[str, list[str]] = {}
    for lane, entry in lanes.items():
        details: list[str] = []
        for dev in (entry or {}).get("deviations") or []:
            if isinstance(dev, dict) and dev.get("kind") == "budget":
                details.append(str(dev.get("detail", "")))
        out[lane] = details
    return out


def scan_env_budget() -> list[tuple[Path, int, str, str]]:
    """Every adapter budget-env read must be declared in lane_protocol.yaml.

    See the ENV_BUDGET_* block above for why. A read is a violation when its
    prefix maps to no lane, or the mapped lane has no {kind: budget} deviation
    whose detail names the exact env var.
    """
    why = ("prompt parity does not cover budget; a per-lane step/results/token "
           "cap moves reach and completeness but was never declared")
    try:
        declared = _declared_budget_details()
    except Exception as e:  # noqa: BLE001 -- fail loud, do not pass silently
        return [(LANE_PROTOCOL, 0, "env_budget",
                 f"cannot read lane_protocol.yaml: {type(e).__name__}: {e}")]

    violations: list[tuple[Path, int, str, str]] = []
    for path in iter_files():
        raw = path.read_text(encoding="utf-8", errors="replace")
        stripped = _strip_prose(raw)
        for m in _ENV_GET_RE.finditer(stripped):
            name = m.group(1)
            suffix = next((s for s in ENV_BUDGET_SUFFIXES
                           if name.endswith("_" + s)), None)
            if suffix is None:
                continue  # not a budget env (e.g. *_TIMEOUT, *_SNIPPET_CHARS)
            prefix = name[: -(len(suffix) + 1)]
            line = stripped[: m.start()].count("\n") + 1
            lane = ENV_BUDGET_PREFIX_TO_LANE.get(prefix)
            if lane is None:
                violations.append((path, line, "env_budget",
                    f"budget env {name!r} has no lane mapping; add its prefix to "
                    f"ENV_BUDGET_PREFIX_TO_LANE and declare a {{kind: budget}} "
                    f"deviation. {why}"))
                continue
            if not any(name in d for d in declared.get(lane, [])):
                violations.append((path, line, "env_budget",
                    f"lane {lane!r} reads budget env {name!r} but declares no "
                    f"{{kind: budget}} deviation naming it in lane_protocol.yaml. "
                    f"{why}"))
    return violations


# --- sampling parity (added 2026-07-09) ------------------------------------
#
# `lane_protocol.yaml` says of the backbone block: "Cross-backbone comparison is
# only meaningful when nothing but the weights changes. These must be identical
# across lanes AND across backbones." It then names `temperature: 0.2`.
#
# Nothing checked. storm ran every one of its five stages at 0.7
# (storm_runner.py:446), and storm is #1 on the qwen board. costorm and tongyi
# did the same. None of the three declared it. Temperature is not a property of
# a framework the way a step budget is: it is a sampling knob the harness passes
# to the model, so it is equalisable, and an unequalised sampler makes "same
# harness, change the model" false.
#
# Scanned with `ast`, not a regex: `temperature=0.7` appears as a keyword arg,
# as a dict value, and inside settings-override mappings.
_SAMPLING_KEYS = ("temperature", "top_p")


def _declared_sampling() -> dict[str, float]:
    import yaml
    doc = yaml.safe_load(LANE_PROTOCOL.read_text(encoding="utf-8")) or {}
    bb = doc.get("backbone") or {}
    return {k: float(bb[k]) for k in _SAMPLING_KEYS if k in bb}


# A text scan over `_strip_prose`, not an `ast` walk. tongyi builds its agent
# loop as a Python source STRING and exec's it in a subprocess venv, so its
# `temperature=0.7` is a string constant to `ast` and invisible to a walk. That
# is exactly the hiding place this file's docstring warns about. `_strip_prose`
# keeps string literals and blanks only comments and docstrings, so the scan sees
# the driver script and does not trip over a comment quoting a deleted value.
#
# Matches `temperature=0.7`, `"temperature": 0.7`, and `"llm.temperature": 0.7`.
_SAMPLING_RE = re.compile(
    r"""['"]?(?:\w+\.)?(temperature|top_p)['"]?\s*[:=]\s*(\d+(?:\.\d+)?)""")


def scan_sampling() -> list[tuple[Path, int, str, str]]:
    try:
        declared = _declared_sampling()
    except Exception as e:  # noqa: BLE001 -- fail loud
        return [(LANE_PROTOCOL, 0, "sampling_parity",
                 f"cannot read lane_protocol.yaml: {type(e).__name__}: {e}")]
    if not declared:
        return [(LANE_PROTOCOL, 0, "sampling_parity",
                 "lane_protocol declares no backbone.temperature; nothing to enforce")]

    violations: list[tuple[Path, int, str, str]] = []
    for path in iter_files():
        stripped = _strip_prose(path.read_text(encoding="utf-8", errors="replace"))
        for m in _SAMPLING_RE.finditer(stripped):
            key, value = m.group(1), float(m.group(2))
            line = stripped[: m.start()].count("\n") + 1
            want = declared.get(key)
            if want is None or abs(value - want) < 1e-9:
                continue
            violations.append((path, line, "sampling_parity",
                f"{key}={value} but lane_protocol.yaml declares backbone.{key}="
                f"{want}, which it requires to be identical across lanes AND "
                "across backbones. A lane sampling differently is not the same "
                "experiment as its neighbours"))
    return violations


def scan() -> list[tuple[Path, int, str, str]]:
    violations: list[tuple[Path, int, str, str]] = []
    for path in iter_files():
        raw = path.read_text(encoding="utf-8", errors="replace")
        stripped = _strip_prose(raw)
        for rule_id, pattern, why in RULES:
            for m in re.finditer(pattern, stripped, re.I):
                line = stripped[: m.start()].count("\n") + 1
                violations.append((path, line, rule_id, why))
    violations += scan_env_budget()
    violations += scan_sampling()
    violations += scan_lane_inventory()
    return violations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list scanned files and rules")
    args = ap.parse_args()

    if args.list:
        print("scanned files:")
        for p in iter_files():
            print(f"  {p.relative_to(ROOT)}")
        print("\nrules:")
        for rid, pat, why in RULES:
            print(f"  {rid:20s} {why}")
        print(f"  {'env_budget':20s} per-lane budget env reads "
              f"({', '.join(ENV_BUDGET_SUFFIXES)}) must be declared as "
              f"{{kind: budget}} in lane_protocol.yaml")
        print(f"  {'sampling_parity':20s} temperature/top_p must equal the "
              "lane_protocol backbone declaration")
        print(f"  {'lane_inventory':20s} RUNNERS, CLI choices, planner and "
              "lane_protocol must be an exact, well-formed set")
        return 0

    violations = scan()
    if not violations:
        print(f"parity OK: {len(iter_files())} adapter files, {len(RULES) + 3} rules, 0 violations")
        return 0

    print(f"PARITY VIOLATIONS: {len(violations)}\n", file=sys.stderr)
    for path, line, rule_id, why in violations:
        print(f"  {path.relative_to(ROOT)}:{line}  [{rule_id}]  {why}", file=sys.stderr)
    print("\nA lane may only deviate in ways declared in config/lane_protocol.yaml.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
