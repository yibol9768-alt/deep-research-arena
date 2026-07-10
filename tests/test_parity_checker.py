"""Prose-stripping regression for scripts/check_parity.py.

The load-bearing property: `_strip_prose` blanks docstrings and `#` comments
but keeps every other string literal, *including triple-quoted ones*. Several
CLI lane runners build their system prompt as a triple-quoted f-string here-doc;
an earlier implementation stripped every `\"\"\"...\"\"\"` block with a regex and
so went blind to exactly the injections this checker exists to catch.

These tests drive `_strip_prose` + `RULES` on synthetic source text (the task's
instruction), not `scan()`, because `scan()` globs the real adapter tree under
ROOT rather than a fixture.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_parity import (  # noqa: E402
    RULES,
    _strip_prose,
    scan,
    scan_lane_inventory,
)


def _scan_text(src: str) -> list[str]:
    """Reproduce scan()'s core on in-memory text: strip prose, apply RULES."""
    stripped = _strip_prose(src)
    hits: list[str] = []
    for rule_id, pattern, _why in RULES:
        for _m in re.finditer(pattern, stripped, re.I):
            hits.append(rule_id)
    return hits


# --- the regression: triple-quoted prompts must NOT be stripped ------------

def test_injection_inside_triple_quoted_fstring_is_caught():
    # A CLI lane's system prompt, built as a triple-quoted f-string assigned to a
    # variable. It is not a docstring (not the first statement of a scope), so it
    # must survive stripping and trip the rules.
    src = (
        'MODEL = "qwen"\n'
        'SYSTEM_PROMPT = f"""\n'
        'You are a research agent for {MODEL}.\n'
        'Your report is invalid unless it includes at least 5 exact sandbox URLs.\n'
        '"""\n'
    )
    hits = _scan_text(src)
    assert "citation_count" in hits
    assert "invalid_unless_urls" in hits


def test_injection_inside_plain_triple_quoted_string_is_caught():
    src = (
        'PROMPT = """\n'
        'Please make 6 focused searches before writing.\n'
        '"""\n'
    )
    assert "search_count" in _scan_text(src)


# --- explanations must not self-trip --------------------------------------

def test_same_string_in_module_docstring_does_not_trip():
    # The removals left long docstrings quoting the exact strings they deleted.
    # Blanking docstrings is what lets the fix keep its own explanation.
    src = (
        '"""Removed: the prompt that said invalid unless it includes at least 5\n'
        'exact sandbox URLs. Do not reintroduce it."""\n'
        'X = 1\n'
    )
    assert _scan_text(src) == []


def test_same_string_in_function_docstring_does_not_trip():
    src = (
        'def build_prompt():\n'
        '    """We deleted the line: at least 5 exact sandbox URLs."""\n'
        '    return "ok"\n'
    )
    assert _scan_text(src) == []


def test_same_string_in_hash_comment_does_not_trip():
    src = (
        '# removed injection: invalid unless it includes at least 5 sandbox URLs\n'
        'X = 1\n'
    )
    assert _scan_text(src) == []


# --- a docstring and a live prompt in the same file are told apart ---------

def test_docstring_and_live_prompt_coexist():
    src = (
        '"""Module doc mentioning at least 5 exact sandbox URLs was removed."""\n'
        'PROMPT = """\n'
        'Your report is invalid unless it includes at least 5 exact sandbox URLs.\n'
        '"""\n'
    )
    hits = _scan_text(src)
    # The live prompt trips; the docstring does not double-count it.
    assert "citation_count" in hits
    assert "invalid_unless_urls" in hits


@pytest.mark.parametrize(
    ("prompt", "rule"),
    [
        ("Issue MULTIPLE search queries covering different angles.", "search_breadth"),
        ("Start by searching for the topic with several queries.", "search_breadth"),
        ("For each relevant result, fetch the page.", "fetch_all_results"),
        ("Cross-reference between Magento, Postmill, and Kiwix.", "cross_reference"),
        ("Cite approximately eleven distinct source URLs.", "citation_count"),
        ("Use a dozen citations.", "citation_count"),
        ("Write with inline citations and a References section.", "citation_format"),
    ],
)
def test_semantic_prompt_rule_snapshot(prompt, rule):
    """Snapshot the paraphrase classes that escaped the old literal regexes."""
    hits = _scan_text(f"PROMPT = {prompt!r}\n")
    assert rule in hits, (prompt, hits)


# --- unparseable source degrades to comment stripping, still catches -------

def test_syntax_error_falls_back_to_comment_strip():
    # ast.parse fails, so _strip_prose can only blank `#` comments. A live prompt
    # in broken source must still be visible (fail-loud, not fail-silent).
    src = (
        'def broken(:\n'  # deliberate syntax error
        'PROMPT = "invalid unless it includes at least 5 sandbox URLs"\n'
    )
    assert "invalid_unless_urls" in _scan_text(src)


# --- the real tree is clean ------------------------------------------------

def test_current_repo_has_no_parity_violations():
    assert scan() == []


# --- exact comparative-lane inventory --------------------------------------

def test_lane_inventory_matches_runtime_cli_and_planner():
    import yaml

    from scripts import plan_full_leaderboard
    from scripts import run_deep_task
    from scripts.runners import browser_dr_runner, gemini_cli_runner

    protocol = yaml.safe_load(
        (ROOT / "config/lane_protocol.yaml").read_text(encoding="utf-8")
    )
    declared = set(protocol["lanes"])
    assert declared == set(run_deep_task.RUNNERS)
    assert declared == set(run_deep_task.runner_choices())
    assert declared == set(plan_full_leaderboard._declared_agents())

    # These adapters remain directly callable for standalone experiments, but
    # each would mislabel the requested backbone on a comparative board.
    assert {"browser-dr", "gemini-cli", "dzhng"}.isdisjoint(declared)
    assert browser_dr_runner.BENCHMARK_ENABLED is False
    assert gemini_cli_runner.BENCHMARK_ENABLED is False
    assert "dzhng" not in run_deep_task._MANUAL_RUNNERS
    assert {
        "co-storm",
        "codex",
        "deepagents",
        "local-deep-researcher",
        "tongyi-dr",
    } <= declared


def test_lane_inventory_checker_fails_both_drift_directions(tmp_path, monkeypatch):
    import yaml

    from scripts import plan_full_leaderboard
    from scripts import run_deep_task
    from scripts import check_parity

    protocol_path = tmp_path / "lane_protocol.yaml"
    protocol_path.write_text(yaml.safe_dump({
        "lanes": {
            "declared-only": {
                "delivery": "subprocess",
                "fetch_observable": False,
                "fetch_mode": "unknown",
                "deviations": [],
            }
        }
    }), encoding="utf-8")
    monkeypatch.setattr(check_parity, "LANE_PROTOCOL", protocol_path)
    monkeypatch.setattr(run_deep_task, "RUNNERS", {"runtime-only": object()})
    monkeypatch.setattr(
        plan_full_leaderboard,
        "_declared_agents",
        lambda: ["declared-only"],
    )

    hits = scan_lane_inventory()
    reasons = "\n".join(reason for _path, _line, rule, reason in hits
                        if rule == "lane_inventory")
    assert "runner_without_declaration=['runtime-only']" in reasons
    assert "declared_without_runner=['declared-only']" in reasons


def test_lane_inventory_checker_rejects_false_observability(tmp_path, monkeypatch):
    import yaml

    from scripts import plan_full_leaderboard
    from scripts import run_deep_task
    from scripts import check_parity

    protocol_path = tmp_path / "lane_protocol.yaml"
    protocol_path.write_text(yaml.safe_dump({
        "lanes": {
            "bad-fetch": {
                "delivery": "subprocess",
                "fetch_observable": True,
                "fetch_mode": "direct_requests",
                "deviations": [],
            }
        }
    }), encoding="utf-8")
    monkeypatch.setattr(check_parity, "LANE_PROTOCOL", protocol_path)
    monkeypatch.setattr(run_deep_task, "RUNNERS", {"bad-fetch": object()})
    monkeypatch.setattr(plan_full_leaderboard, "_declared_agents", lambda: ["bad-fetch"])

    reasons = [reason for _path, _line, rule, reason in scan_lane_inventory()
               if rule == "lane_inventory"]
    assert any("claims fetch_observable=true" in reason for reason in reasons)


# --- sampling parity -------------------------------------------------------
#
# `lane_protocol.yaml` requires backbone.temperature to be "identical across
# lanes AND across backbones". Nothing enforced it. storm ran all five of its
# stages at 0.7 while sitting at #1 on the qwen board, and declared no deviation;
# costorm and tongyi did the same. A step budget cannot be equalised across
# heterogeneous frameworks, but a sampler can: it is a number the harness passes
# to the model.

def _scan_sampling_text(src: str, declared: dict[str, float]) -> list[tuple[str, float]]:
    from scripts.check_parity import _SAMPLING_RE
    out = []
    for m in _SAMPLING_RE.finditer(_strip_prose(src)):
        key, val = m.group(1), float(m.group(2))
        want = declared.get(key)
        if want is not None and abs(val - want) > 1e-9:
            out.append((key, val))
    return out


def test_sampling_deviation_is_caught_as_keyword_and_as_dict_value():
    src = (
        'r = client.chat.completions.create(model=M, temperature=0.7)\n'
        'settings = {"llm.temperature": 0.9, "top_p": 0.5}\n'
    )
    hits = _scan_sampling_text(src, {"temperature": 0.2, "top_p": 1.0})
    assert ("temperature", 0.7) in hits
    assert ("temperature", 0.9) in hits, "dotted settings key missed"
    assert ("top_p", 0.5) in hits


def test_sampling_deviation_hidden_in_an_execd_driver_string_is_caught():
    """tongyi builds its agent loop as a source STRING and exec's it.

    An `ast` walk sees one string constant and nothing inside it. That is the
    hiding place this checker's docstring warns about, and the first version of
    this rule fell into it: it flagged storm and costorm and walked straight past
    tongyi_runner.py:153.
    """
    src = (
        'DRIVER = """\n'
        'resp = client.chat.completions.create(\n'
        '    model=MODEL,\n'
        '    temperature=0.7,\n'
        ')\n'
        '"""\n'
    )
    assert ("temperature", 0.7) in _scan_sampling_text(src, {"temperature": 0.2})


def test_conforming_temperature_and_commented_out_value_do_not_trip():
    src = (
        '# we used to pass temperature=0.7 here; equalised 2026-07-09\n'
        'r = create(model=M, temperature=0.2)\n'
    )
    assert _scan_sampling_text(src, {"temperature": 0.2}) == []
