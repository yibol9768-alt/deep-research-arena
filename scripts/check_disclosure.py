#!/usr/bin/env python3
"""Fail the build when a lane differs from the shared protocol without saying so.

`scripts/check_parity.py` catches a lane that RE-INTRODUCES a forbidden steer.
This file catches the complementary failure: a lane that legitimately differs
(reads pages off the recording shim, swaps out a retriever, truncates context)
but never DECLARES the difference, so the board cannot render a footnote and the
comparison silently stops being apples-to-apples.

Property A of the leaderboard (GOAL_GATES_V1.md, gate G0) requires that every
such difference is written into `config/lane_protocol.yaml` under that lane's
`deviations`, in a machine-readable, bilingual form the frontend can disclose:

    - kind:      the class of exception (budget / capability_delivery / ...)
      code:      a stable machine key, unique within the lane ([a-z0-9_]+)
      human_zh:  one-line disclosure, Simplified Chinese
      human_en:  one-line disclosure, English
      detail:    the authoritative long-form provenance (frozen; owned elsewhere)

This checker reconciles five families of difference SIGNAL against those
declarations and exits non-zero on any undeclared difference:

  1. schema           -- every deviation carries a non-empty, well-formed
                         {kind, code, human_zh, human_en, detail}; codes are
                         unique within a lane.
  2. fetch_withhold   -- fetch_observable is False  <=>  a fetch_withhold
                         deviation exists. A lane that reads pages off-shim (or
                         whose transport is unverified) has proof-of-fetch
                         WITHHELD, never scored 0; that withhold is a disclosed
                         difference, so the board must show it. Symmetric: a lane
                         declared observable may NOT carry a stale withhold.
  3. snippet_only     -- fetch_mode is "none"  <=>  a snippet_only deviation
                         exists. A lane with no page-read tool AT ALL (its only
                         affordance is shim /search) is architecturally on a
                         different track from every page-reading lane; that is a
                         structural difference the board must disclose, distinct
                         from the frozen semantic question of how completeness's
                         fetch threshold should treat it (docs/SPEC_ISSUES.md).
  4. code signals     -- concrete difference signals in the adapter source
                         (a bound shim retriever = tool substitution; a context
                         window / context-token truncation; adapter-injected web
                         tools a framework lacks natively = the tool-missing
                         class) must each be named in a deviation for the mapped
                         lane.
  5. gateway policy   -- router-level mechanisms in the two LLM doors
                         (llm_gateway :8100 / ds_proxy :8088) that go beyond the
                         shared sampler -- qwen-only fit_to_window rescue, the
                         glm floor, transient retries, think-stripping, the
                         json_schema downgrade, the ops max_tokens floor -- must
                         each be named in backbone.gateway_policy_disclosures
                         (SPEC_ISSUES §2 ruled: unify or declare in full).

Like check_parity, the code-signal scan is a TEXT scan over `_strip_prose`, NOT
an `ast` walk: `tongyi_runner.py` and `gpt_researcher_runner.py` build their
agent loops / retrievers as Python SOURCE STRINGS and exec them in subprocess
venvs, so `MAX_CONTEXT_TOKENS` and `_ShimTavilyRetriever` are string constants
invisible to an ast walk (HANDOFF_2026-07-09.md, trap 3).

DELIBERATELY OUT OF SCOPE: per-lane OUTER subprocess timeouts (OPENCODE_TIMEOUT,
DEERFLOW_TASK_TIMEOUT_S, ...). `lane_protocol.yaml` (budget section) declares
these uniform infrastructure caps governed by the shared stall watchdog, and
places them intentionally outside the scored surface. Forcing them to be
declared as deviations would contradict that frozen decision. If per-lane
timeout DEFAULTS should nonetheless be disclosed, that is a maintainer call,
logged in docs/SPEC_ISSUES.md, not enforced here.

    python3 scripts/check_disclosure.py            # exit 1 on undeclared difference
    python3 scripts/check_disclosure.py --list     # show what is reconciled
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse check_parity's text-scan primitive so both checkers agree on what a
# comment is versus what a live string literal is.
from scripts.check_parity import _strip_prose  # noqa: E402

LANE_PROTOCOL = ROOT / "config" / "lane_protocol.yaml"

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# The five keys every deviation must carry. `kind` and `detail` predate this
# gate (check_parity already requires them); `code`, `human_zh`, `human_en` are
# the machine-readable disclosure this gate adds and enforces.
_DEVIATION_KEYS = ("kind", "code", "human_zh", "human_en", "detail")

# The code a fetch-withhold disclosure must use, so the reconciliation and the
# board renderer key off one stable string.
FETCH_WITHHOLD_CODE = "fetch_withhold"

# The code a snippet-only (no page-read tool by architecture) disclosure must
# use, for the same reason.
SNIPPET_ONLY_CODE = "snippet_only"


# --- code-signal rules -----------------------------------------------------
#
# Each rule: a concrete difference SIGNAL that must appear (as live source, not a
# comment) in exactly one adapter file, mapped to the lane it belongs to, plus
# the disclosure that lane must therefore carry. `require` is one of:
#   ("code", <code>)          -- a deviation with exactly this code
#   ("detail_token", <token>) -- some deviation whose detail names this token
#
# A rule whose file is missing is itself a violation: a checker that cannot read
# the code it reconciles must fail loud, not pass by silence.
SIGNAL_RULES: list[dict] = [
    {
        "lane": "gpt-researcher",
        "file": "scripts/runners/gpt_researcher_runner.py",
        "signal": re.compile(r"_ShimTavilyRetriever|_build_shim_retriever_block"),
        "require": ("code", "retriever_shim"),
        "why": ("gpt-researcher binds a shim-backed retriever in place of "
                "TavilySearch (a tool substitution that changes what the lane "
                "can retrieve); it must be declared so the board discloses it"),
    },
    {
        "lane": "opencode",
        "file": "scripts/runners/opencode_runner.py",
        "signal": re.compile(r"_CONTEXT_LIMIT\b"),
        "require": ("detail_token", "CONTEXT_LIMIT"),
        "why": ("opencode is told to assume a fixed context window (context "
                "truncation bounds how much it can hold and write); the exact "
                "knob must be named in a deviation"),
    },
    {
        "lane": "tongyi-dr",
        "file": "scripts/runners/tongyi_runner.py",
        "signal": re.compile(r"MAX_CONTEXT_TOKENS\b"),
        "require": ("detail_token", "MAX_CONTEXT_TOKENS"),
        "why": ("tongyi truncates to a hardcoded context-token budget (context "
                "truncation); it is a constant, not an env, so check_parity's "
                "env_budget rule cannot see it -- it must be named in a deviation"),
    },
    {
        "lane": "deepagents",
        "file": "scripts/runners/deepagents_runner.py",
        "signal": re.compile(r"tools=\[internet_search"),
        "require": ("code", "capability_adapter_tools"),
        "why": ("DeepAgents ships no native web tools; the adapter injects "
                "internet_search + fetch_page (a tool the framework lacks, "
                "supplied by our code -- the tool-missing class), which changes "
                "what the lane can do; it must be declared so the board "
                "discloses it"),
    },
    # --- adapter-layer signals embedded in run_deep_task.py / the runners -----
    #
    # The four rules above name framework-substitution signals in the dedicated
    # *_runner.py adapters. But several lanes are driven by an adapter EMBEDDED
    # inside scripts/run_deep_task.py (camel-ai's report cleaner, langchain-odr's
    # single-lane graph patch), and two runners carry adapter-layer RETRY loops
    # and page TRUNCATION that move nothing a framework declared. The signal
    # classes below (report post-processing regex, hardcoded [:N] slice clamps,
    # injected ToolMessages, character truncation, adapter retry constants) were
    # structurally invisible because run_deep_task.py was never scanned here.
    # Each is mapped to the lane it steers and the disclosure that lane carries.
    {
        "lane": "camel-ai",
        "file": "scripts/run_deep_task.py",
        "signal": re.compile(r"_sanitize_camel_report"),
        "require": ("code", "report_postprocess"),
        "why": ("camel-ai's saved report is rewritten by the harness "
                "(_sanitize_camel_report strips balanced framework XML marker "
                "pairs from the scored text); a report post-processing step must "
                "be declared so the board discloses it"),
    },
]


# --- gateway-policy signal rules --------------------------------------------
#
# Same shape as SIGNAL_RULES, but the declaration lives at
# backbone.gateway_policy_disclosures (doc level), not under a lane: these
# mechanisms sit in the two LLM doors and affect every lane routed through
# them. The signal is matched over _strip_prose of the proxy source, so a
# comment naming a removed mechanism does not keep its disclosure alive.
GATEWAY_SIGNAL_RULES: list[dict] = [
    {
        "file": "integrations/llm_gateway/app.py",
        "signal": re.compile(r"fit_to_window"),
        "code": "gw_fit_to_window",
        "why": ("the gateway clamps/refits qwen requests to the context window "
                "(len//3 estimator, qwen-only rescue)"),
    },
    {
        "file": "integrations/llm_gateway/app.py",
        "signal": re.compile(r"max_tokens_floor"),
        "code": "gw_max_tokens_floor",
        "why": "the gateway raises glm requests to a 131072 floor",
    },
    {
        "file": "integrations/ds_proxy/app.py",
        "signal": re.compile(r"_retry_pause"),
        "code": "dsp_transient_retries",
        "why": "ds_proxy retries transient upstream failures; the gateway does not",
    },
    {
        "file": "integrations/ds_proxy/app.py",
        "signal": re.compile(r"_strip_think"),
        "code": "dsp_think_strip",
        "why": "ds_proxy strips <think> wrappers from responses; the gateway does not",
    },
    {
        "file": "integrations/ds_proxy/app.py",
        "signal": re.compile(r"json_schema"),
        "code": "dsp_json_schema_downgrade",
        "why": ("ds_proxy downgrades json_schema to json_object and injects the "
                "schema as a system nudge; the gateway does not"),
    },
    {
        "file": "integrations/ds_proxy/app.py",
        "signal": re.compile(r"MIN_MAX_TOKENS"),
        "code": "dsp_min_max_tokens",
        "why": "ds_proxy's ops floor may raise a too-small max_tokens (ceiling-bounded)",
    },
]


# --- pure reconcilers (take parsed data, return violations) ----------------
#
# Violations are (source, rule_id, why) triples. `source` is a repo-relative
# string. Pure functions so tests can drive them with fixtures directly.

Violation = tuple[str, str, str]


def check_schema(lanes: dict) -> list[Violation]:
    """Every deviation is a well-formed, machine-readable, bilingual record."""
    out: list[Violation] = []
    rid = "deviation_schema"
    src = "config/lane_protocol.yaml"
    if not isinstance(lanes, dict) or not lanes:
        return [(src, rid, "lanes must be a non-empty mapping")]
    for lane, entry in lanes.items():
        devs = (entry or {}).get("deviations")
        if devs is None:
            out.append((src, rid, f"lane {lane!r} has no deviations key"))
            continue
        if not isinstance(devs, list):
            out.append((src, rid, f"lane {lane!r} deviations must be a list"))
            continue
        seen: set[str] = set()
        for i, dev in enumerate(devs):
            if not isinstance(dev, dict):
                out.append((src, rid, f"lane {lane!r} deviation[{i}] must be a mapping"))
                continue
            for key in _DEVIATION_KEYS:
                if not str(dev.get(key, "")).strip():
                    out.append((src, rid,
                        f"lane {lane!r} deviation[{i}] is missing non-empty {key!r}"))
            code = str(dev.get("code", ""))
            if code and not _CODE_RE.match(code):
                out.append((src, rid,
                    f"lane {lane!r} deviation[{i}] code {code!r} is not a "
                    "[a-z0-9_] slug"))
            if code:
                if code in seen:
                    out.append((src, rid,
                        f"lane {lane!r} has duplicate deviation code {code!r}; "
                        "codes must be unique within a lane"))
                seen.add(code)
    return out


def check_fetch_withhold(lanes: dict) -> list[Violation]:
    """fetch_observable is False  <=>  a fetch_withhold deviation exists.

    A lane that reads pages off the recording shim (or whose transport is not
    yet proven observable) has proof-of-fetch WITHHELD, never scored 0. That
    withhold is a declared difference the board must disclose, so it must be a
    deviation, not merely the boolean field. Enforced in both directions so an
    observable lane cannot carry a stale withhold footnote either.
    """
    out: list[Violation] = []
    rid = "fetch_withhold"
    src = "config/lane_protocol.yaml"
    for lane, entry in (lanes or {}).items():
        observable = (entry or {}).get("fetch_observable")
        devs = (entry or {}).get("deviations") or []
        has = any(isinstance(d, dict) and d.get("code") == FETCH_WITHHOLD_CODE
                  for d in devs)
        if observable is False and not has:
            out.append((src, rid,
                f"lane {lane!r} is fetch_observable=false (pof withheld) but "
                f"declares no {FETCH_WITHHOLD_CODE!r} deviation; the withhold is "
                "an undeclared difference the board cannot disclose"))
        if observable is True and has:
            out.append((src, rid,
                f"lane {lane!r} is fetch_observable=true but declares a "
                f"{FETCH_WITHHOLD_CODE!r} deviation; a stale withhold footnote "
                "would misdescribe an observable lane"))
    return out


def check_snippet_only(lanes: dict) -> list[Violation]:
    """fetch_mode is "none"  <=>  a snippet_only deviation exists.

    A lane whose ONLY affordance is shim /search reads no pages by architecture.
    That is a structural difference from every page-reading lane (its pof=0 is
    honest, its citations classify as snippet_only, and completeness's fetch
    threshold interacts with it -- the frozen fork in docs/SPEC_ISSUES.md), so
    the board must disclose it. Enforced in both directions so a page-reading
    lane cannot carry a stale snippet-only footnote either.
    """
    out: list[Violation] = []
    rid = "snippet_only"
    src = "config/lane_protocol.yaml"
    for lane, entry in (lanes or {}).items():
        mode = (entry or {}).get("fetch_mode")
        devs = (entry or {}).get("deviations") or []
        has = any(isinstance(d, dict) and d.get("code") == SNIPPET_ONLY_CODE
                  for d in devs)
        if mode == "none" and not has:
            out.append((src, rid,
                f"lane {lane!r} is fetch_mode=none (no page-read tool by "
                f"architecture) but declares no {SNIPPET_ONLY_CODE!r} deviation; "
                "a structurally different lane must be disclosed on the board"))
        if mode != "none" and has:
            out.append((src, rid,
                f"lane {lane!r} is fetch_mode={mode!r} but declares a "
                f"{SNIPPET_ONLY_CODE!r} deviation; a stale snippet-only footnote "
                "would misdescribe a page-reading lane"))
    return out


def reconcile_signals(lanes: dict, file_texts: dict[str, str],
                      rules: list[dict] | None = None) -> list[Violation]:
    """A concrete code signal present in an adapter must be declared for its lane.

    `file_texts` maps a rule's repo-relative file path to that file's raw text,
    or to None if the file is unreadable/absent. The signal is matched over
    `_strip_prose`, so a comment quoting the pattern does not count and a driver
    source STRING does.
    """
    out: list[Violation] = []
    rid = "signal_reconciliation"
    for rule in (rules if rules is not None else SIGNAL_RULES):
        f = rule["file"]
        text = file_texts.get(f)
        if not text:
            out.append((f, rid,
                f"cannot read {f!r} to reconcile lane {rule['lane']!r}'s "
                f"{rule['require'][1]!r} disclosure; a checker that cannot see "
                "the code it audits must fail loud"))
            continue
        try:
            stripped = _strip_prose(text)
        except Exception:  # noqa: BLE001 -- unparseable adapter is a loud failure
            stripped = text
        if not rule["signal"].search(stripped):
            continue  # signal absent: nothing to disclose for this rule
        lane = rule["lane"]
        entry = (lanes or {}).get(lane)
        if not isinstance(entry, dict):
            out.append((f, rid,
                f"signal for lane {lane!r} is present but the lane is not "
                "declared in lane_protocol.yaml"))
            continue
        devs = entry.get("deviations") or []
        kind, val = rule["require"]
        if kind == "code":
            ok = any(isinstance(d, dict) and d.get("code") == val for d in devs)
        elif kind == "detail_token":
            ok = any(isinstance(d, dict) and val in str(d.get("detail", ""))
                     for d in devs)
        else:  # pragma: no cover -- guards a malformed rule table
            out.append((f, rid, f"malformed rule requirement {rule['require']!r}"))
            continue
        if not ok:
            need = (f"a deviation with code {val!r}" if kind == "code"
                    else f"a deviation whose detail names {val!r}")
            out.append((f, rid,
                f"lane {lane!r}: {rule['why']}. Missing {need} in "
                "config/lane_protocol.yaml"))
    return out


def check_gateway_policy(disclosures: list, file_texts: dict[str, str],
                         rules: list[dict] | None = None) -> list[Violation]:
    """Every router-level door mechanism is declared, and no stale entry lives on.

    `disclosures` is backbone.gateway_policy_disclosures (a list of the same
    {kind, code, human_zh, human_en, detail} records the lane deviations use).
    Both directions: a signal present in the proxy source with no declaration
    is an undeclared door behaviour; a declared code whose signal is gone from
    the source is a stale disclosure that misdescribes the door.
    """
    out: list[Violation] = []
    rid = "gateway_policy"
    src = "config/lane_protocol.yaml"
    rules = rules if rules is not None else GATEWAY_SIGNAL_RULES
    entries = [d for d in (disclosures or []) if isinstance(d, dict)]
    declared = {str(d.get("code", "")) for d in entries}
    # Schema: reuse the deviation record shape.
    for i, d in enumerate(entries):
        for key in _DEVIATION_KEYS:
            if not str(d.get(key, "")).strip():
                out.append((src, rid,
                    f"gateway_policy_disclosures[{i}] is missing non-empty {key!r}"))
    seen: set[str] = set()
    for d in entries:
        code = str(d.get("code", ""))
        if code in seen:
            out.append((src, rid,
                f"duplicate gateway_policy_disclosures code {code!r}"))
        seen.add(code)
    live: set[str] = set()
    for rule in rules:
        f = rule["file"]
        text = file_texts.get(f)
        if not text:
            out.append((f, rid,
                f"cannot read {f!r} to reconcile gateway disclosure "
                f"{rule['code']!r}; a checker that cannot see the code it "
                "audits must fail loud"))
            continue
        try:
            stripped = _strip_prose(text)
        except Exception:  # noqa: BLE001 -- unparseable proxy is a loud failure
            stripped = text
        if not rule["signal"].search(stripped):
            continue
        live.add(rule["code"])
        if rule["code"] not in declared:
            out.append((f, rid,
                f"{rule['why']}. Missing a gateway_policy_disclosures entry "
                f"with code {rule['code']!r} in config/lane_protocol.yaml"))
    known_codes = {r["code"] for r in rules}
    for code in sorted(declared & known_codes - live):
        out.append((src, rid,
            f"gateway_policy_disclosures declares {code!r} but its signal is "
            "gone from the proxy source; a stale disclosure misdescribes the door"))
    return out


# --- disk wiring -----------------------------------------------------------

def _load_doc(protocol: Path) -> dict:
    return yaml.safe_load(protocol.read_text(encoding="utf-8")) or {}


def _load_lanes(protocol: Path) -> dict:
    return _load_doc(protocol).get("lanes") or {}


def _read_signal_files(rules: list[dict]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for rule in rules:
        rel = rule["file"]
        p = ROOT / rel
        try:
            texts[rel] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            texts[rel] = ""
    return texts


def scan() -> list[Violation]:
    try:
        doc = _load_doc(LANE_PROTOCOL)
    except Exception as e:  # noqa: BLE001 -- a malformed protocol must fail loud
        return [("config/lane_protocol.yaml", "load",
                 f"cannot read lane inventory: {type(e).__name__}: {e}")]
    lanes = doc.get("lanes") or {}
    gw_disclosures = (doc.get("backbone") or {}).get(
        "gateway_policy_disclosures") or []
    out: list[Violation] = []
    out += check_schema(lanes)
    out += check_fetch_withhold(lanes)
    out += check_snippet_only(lanes)
    out += reconcile_signals(lanes, _read_signal_files(SIGNAL_RULES))
    out += check_gateway_policy(
        gw_disclosures, _read_signal_files(GATEWAY_SIGNAL_RULES))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true",
                    help="list what is reconciled")
    args = ap.parse_args()

    if args.list:
        print("reconciled families:")
        print("  deviation_schema      every deviation has non-empty "
              "{kind, code, human_zh, human_en, detail}; codes unique per lane")
        print("  fetch_withhold        fetch_observable=false <=> a "
              f"{FETCH_WITHHOLD_CODE!r} deviation is declared (and vice versa)")
        print("  snippet_only          fetch_mode=none <=> a "
              f"{SNIPPET_ONLY_CODE!r} deviation is declared (and vice versa)")
        print("  signal_reconciliation each concrete adapter difference signal "
              "is named in a deviation for its lane:")
        for r in SIGNAL_RULES:
            print(f"    - {r['lane']:16} {r['file']}  needs {r['require']}")
        print("  gateway_policy        each router-level door mechanism is "
              "declared in backbone.gateway_policy_disclosures (both directions):")
        for r in GATEWAY_SIGNAL_RULES:
            print(f"    - {r['code']:26} {r['file']}")
        print("\nout of scope (frozen decision): per-lane outer subprocess "
              "timeouts are uniform infra, not scored deviations")
        return 0

    violations = scan()
    if not violations:
        n_lanes = len(_load_lanes(LANE_PROTOCOL))
        print(f"disclosure OK: {n_lanes} lanes, "
              f"{3 + len(SIGNAL_RULES) + len(GATEWAY_SIGNAL_RULES)} reconcilers, "
              "0 undeclared differences")
        return 0

    print(f"UNDECLARED DIFFERENCES: {len(violations)}\n", file=sys.stderr)
    for src, rule_id, why in violations:
        print(f"  {src}  [{rule_id}]  {why}", file=sys.stderr)
    print("\nEvery lane difference must be declared in config/lane_protocol.yaml "
          "so the board can disclose it (GOAL_GATES_V1.md, G0).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
