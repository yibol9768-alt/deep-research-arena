"""G0 disclosure-completeness gate: config/lane_protocol.yaml declares every
lane difference the board must footnote, in a machine-readable bilingual form.

Every fixture that varies a lane's SOURCE spans product / wiki / forum, never a
single source type. HANDOFF_2026-07-09.md trap 1: the original nav-citation test
used a product-only fixture, and a product's served spelling already equals its
registry canonical, so the fixture could not exercise the very bug it was written
for. The audit's recurring defect shape is "products spared" while wiki and forum
are treated differently -- so a disclosure fixture that only checks a product lane
would pass while a wiki/forum lane silently loses its footnote. Each fixture below
therefore carries one lane per corpus source.

The old (pre-gate) lane_protocol.yaml declared deviations with only {kind, detail},
no fetch_withhold/snippet_only entries and no gateway_policy_disclosures, so
`scan()` against it reports 101 violations
(see test_disclosure_gate_is_red_on_the_pre_gate_protocol). That is the red-on-old
proof required by GOAL_GATES_V1.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_disclosure as cd


# --- source-spanning fixture builders --------------------------------------
#
# One lane per corpus source. `reads` is documentation of which sandbox source
# the lane's off-shim fetch would open; the checker does not read it, but it
# forces every fixture to exercise all three source types, not just products.

def _lane(*, observable, mode, deviations):
    return {
        "delivery": "subprocess",
        "fetch_observable": observable,
        "fetch_mode": mode,
        "deviations": deviations,
    }


def _withhold_dev():
    return {
        "kind": "fetch_withhold",
        "code": "fetch_withhold",
        "human_zh": "页面读取绕过记录 shim,proof-of-fetch 予以保留,绝不记 0。",
        "human_en": "Page reads bypass the recording shim; pof withheld, never 0.",
        "detail": "off-shim page read; pof withheld (available=False + reason).",
    }


def _tri_source_lanes(*, prod_devs, wiki_devs, forum_devs,
                      prod_obs=False, wiki_obs=False, forum_obs=False):
    """Three lanes, one reading each of shopping / wiki / forum."""
    return {
        # product lane reads the Magento store off-shim via requests
        "prod-lane": _lane(observable=prod_obs, mode="direct_requests", deviations=prod_devs),
        # wiki lane reads Kiwix off-shim via curl
        "wiki-lane": _lane(observable=wiki_obs, mode="direct_curl", deviations=wiki_devs),
        # forum lane's transport to Postmill is not yet proven observable
        "forum-lane": _lane(observable=forum_obs, mode="unknown", deviations=forum_devs),
    }


# --- the real protocol is clean --------------------------------------------

def test_real_lane_protocol_has_zero_undeclared_differences():
    assert cd.scan() == []


def test_cli_exit_zero_on_the_committed_protocol():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_disclosure.py")],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


# --- fetch_withhold reconciliation, spanning all three sources -------------

def test_fetch_withhold_missing_flags_every_source_not_just_products():
    # All three off-shim, none declaring the withhold: the gate must fire for
    # the wiki and forum lanes too, not only the product lane.
    lanes = _tri_source_lanes(prod_devs=[], wiki_devs=[], forum_devs=[])
    v = cd.check_fetch_withhold(lanes)
    flagged = {why.split("'")[1] for _, rid, why in v if rid == "fetch_withhold"}
    assert flagged == {"prod-lane", "wiki-lane", "forum-lane"}


def test_fetch_withhold_products_only_declared_still_flags_wiki_and_forum():
    # The "products spared" asymmetry made concrete: only the product lane
    # declares the withhold. A product-only fixture would have called this clean.
    lanes = _tri_source_lanes(
        prod_devs=[_withhold_dev()], wiki_devs=[], forum_devs=[])
    flagged = {why.split("'")[1] for _, rid, why in cd.check_fetch_withhold(lanes)
               if rid == "fetch_withhold"}
    assert flagged == {"wiki-lane", "forum-lane"}
    assert "prod-lane" not in flagged


def test_fetch_withhold_all_declared_is_clean():
    lanes = _tri_source_lanes(
        prod_devs=[_withhold_dev()], wiki_devs=[_withhold_dev()],
        forum_devs=[_withhold_dev()])
    assert cd.check_fetch_withhold(lanes) == []


def test_fetch_withhold_symmetric_rejects_stale_footnote_on_observable_lane():
    # An observable lane must NOT carry a withhold, or the board would show a
    # footnote that misdescribes it. Spanning sources: the wiki lane is the
    # observable one here.
    lanes = _tri_source_lanes(
        prod_devs=[_withhold_dev()], wiki_devs=[_withhold_dev()],
        forum_devs=[_withhold_dev()], wiki_obs=True)
    v = cd.check_fetch_withhold(lanes)
    assert any("wiki-lane" in why and "true" in why for _, _, why in v)


# --- snippet_only reconciliation (fetch_mode none <=> declared) -------------

def _snippet_only_dev():
    return {
        "kind": "snippet_only",
        "code": "snippet_only",
        "human_zh": "架构上无页面读取工具,仅消费搜索片段。",
        "human_en": "No page-read tool by architecture; snippets only.",
        "detail": "fetch_mode none; only affordance is shim /search.",
    }


def test_snippet_only_missing_is_flagged_and_spans_sources():
    # A snippet-only lane per source flavour: none declares it -> all flagged.
    lanes = {
        "prod-lane": _lane(observable=True, mode="none", deviations=[]),
        "wiki-lane": _lane(observable=True, mode="none", deviations=[]),
        "forum-lane": _lane(observable=True, mode="none", deviations=[]),
    }
    flagged = {why.split("'")[1] for _, rid, why in cd.check_snippet_only(lanes)
               if rid == "snippet_only"}
    assert flagged == {"prod-lane", "wiki-lane", "forum-lane"}


def test_snippet_only_stale_footnote_on_page_reading_lane_is_flagged():
    # Symmetric direction: a page-reading lane must not carry the footnote.
    lanes = _tri_source_lanes(
        prod_devs=[_withhold_dev(), _snippet_only_dev()],
        wiki_devs=[_withhold_dev()], forum_devs=[_withhold_dev()])
    v = cd.check_snippet_only(lanes)
    assert any("prod-lane" in why and "stale" in why for _, _, why in v)
    assert len(v) == 1


def test_snippet_only_declared_is_clean():
    lanes = {
        "wiki-lane": _lane(observable=True, mode="none",
                           deviations=[_snippet_only_dev()]),
        "prod-lane": _lane(observable=False, mode="direct_requests",
                           deviations=[_withhold_dev()]),
    }
    assert cd.check_snippet_only(lanes) == []


def test_real_protocol_snippet_only_lanes_are_declared():
    # The shipped protocol's three snippet-only lanes (storm, langchain-odr,
    # co-storm) each carry the disclosure; the pre-gate protocol declared
    # fetch_mode none with no snippet_only deviation, so this reconciler is red
    # on it (asserted in the red-on-old test below).
    lanes = cd._load_lanes(cd.LANE_PROTOCOL)
    none_lanes = {ln for ln, e in lanes.items()
                  if (e or {}).get("fetch_mode") == "none"}
    assert none_lanes == {"storm", "langchain-odr", "co-storm"}
    assert cd.check_snippet_only(lanes) == []


# --- deviation schema: machine-readable + bilingual ------------------------

def test_schema_requires_code_and_both_human_strings():
    # Each source lane is missing a different required key, so the gate is proven
    # to enforce the whole {code, human_zh, human_en} set, not a single key.
    lanes = _tri_source_lanes(
        prod_devs=[{"kind": "budget", "detail": "d", "human_zh": "z", "human_en": "e"}],       # no code
        wiki_devs=[{"kind": "budget", "detail": "d", "code": "c1", "human_en": "e"}],          # no human_zh
        forum_devs=[{"kind": "budget", "detail": "d", "code": "c2", "human_zh": "z"}],          # no human_en
    )
    reasons = "\n".join(why for _, rid, why in cd.check_schema(lanes)
                        if rid == "deviation_schema")
    assert "'prod-lane'" in reasons and "code" in reasons
    assert "'wiki-lane'" in reasons and "human_zh" in reasons
    assert "'forum-lane'" in reasons and "human_en" in reasons


def test_schema_rejects_duplicate_and_malformed_codes():
    dup = [
        {"kind": "budget", "code": "dup", "human_zh": "z", "human_en": "e", "detail": "d"},
        {"kind": "budget", "code": "dup", "human_zh": "z", "human_en": "e", "detail": "d"},
    ]
    bad = [{"kind": "budget", "code": "Not-A-Slug", "human_zh": "z", "human_en": "e", "detail": "d"}]
    lanes = _tri_source_lanes(prod_devs=dup, wiki_devs=bad, forum_devs=[_withhold_dev()])
    reasons = "\n".join(why for _, rid, why in cd.check_schema(lanes))
    assert "duplicate deviation code 'dup'" in reasons
    assert "not a" in reasons and "slug" in reasons


def test_schema_accepts_the_well_formed_tri_source_fixture():
    good = [{"kind": "budget", "code": "budget_native", "human_zh": "z",
             "human_en": "e", "detail": "d"}, _withhold_dev()]
    lanes = _tri_source_lanes(prod_devs=good, wiki_devs=good, forum_devs=good)
    assert cd.check_schema(lanes) == []


# --- code-signal reconciliation (text scan over _strip_prose) --------------

_RETRIEVER_RULE = [{
    "lane": "prod-lane",
    "file": "fake/runner.py",
    "signal": re.compile(r"_ShimTavilyRetriever|_build_shim_retriever_block"),
    "require": ("code", "retriever_shim"),
    "why": "binds a shim retriever",
}]


def test_signal_in_driver_string_is_caught_even_without_the_code():
    # The retriever class is built as a SOURCE STRING and exec'd -- an ast walk
    # would miss it; the text scan over _strip_prose keeps the string literal
    # (HANDOFF trap 3). Lane declares no retriever_shim code -> violation.
    file_texts = {"fake/runner.py": 'BLOCK = "class _ShimTavilyRetriever:\\n    pass"\n'}
    lanes = {"prod-lane": _lane(observable=False, mode="direct_requests",
                                deviations=[_withhold_dev()])}
    v = cd.reconcile_signals(lanes, file_texts, rules=_RETRIEVER_RULE)
    assert any(rid == "signal_reconciliation" and "retriever_shim" in why
               for _, rid, why in v)


def test_signal_in_a_comment_only_does_not_false_positive():
    # A comment quoting the pattern must not count; otherwise the fix would be to
    # delete the explanatory comment rather than keep the declaration.
    file_texts = {"fake/runner.py": "# _build_shim_retriever_block explained here\nx = 1\n"}
    lanes = {"prod-lane": _lane(observable=False, mode="direct_requests",
                                deviations=[_withhold_dev()])}
    assert cd.reconcile_signals(lanes, file_texts, rules=_RETRIEVER_RULE) == []


def test_signal_declared_code_is_clean():
    file_texts = {"fake/runner.py": 'BLOCK = "class _ShimTavilyRetriever: pass"\n'}
    dev = {"kind": "capability_delivery", "code": "retriever_shim",
           "human_zh": "z", "human_en": "e", "detail": "d"}
    lanes = {"prod-lane": _lane(observable=False, mode="direct_requests",
                                deviations=[dev, _withhold_dev()])}
    assert cd.reconcile_signals(lanes, file_texts, rules=_RETRIEVER_RULE) == []


def test_signal_missing_file_fails_loud():
    lanes = {"prod-lane": _lane(observable=False, mode="direct_requests",
                                deviations=[_withhold_dev()])}
    v = cd.reconcile_signals(lanes, {"fake/runner.py": ""}, rules=_RETRIEVER_RULE)
    assert any("cannot read" in why for _, _, why in v)


# --- the REAL tool-missing (adapter-injected tools) rule, on real code -------

def _deepagents_rule():
    return [r for r in cd.SIGNAL_RULES if r["lane"] == "deepagents"]


def test_tool_missing_rule_exists_and_targets_deepagents():
    # The task's 4th signal class -- a framework that lacks a native tool and
    # has one injected by the adapter -- is reconciled, not merely declared.
    rules = _deepagents_rule()
    assert len(rules) == 1, "deepagents tool-injection rule must be present"
    assert rules[0]["require"] == ("code", "capability_adapter_tools")


def test_tool_missing_signal_present_but_undeclared_is_flagged():
    # deepagents' adapter really does inject internet_search+fetch_page. Strip
    # the capability_adapter_tools deviation and the gate must fire: an injected
    # tool the framework lacks is an undisclosed difference.
    rule = _deepagents_rule()[0]
    text = (cd.ROOT / rule["file"]).read_text(encoding="utf-8", errors="replace")
    devs = [d for d in cd._load_lanes(cd.LANE_PROTOCOL)["deepagents"]["deviations"]
            if d.get("code") != "capability_adapter_tools"]
    lanes = {"deepagents": {"fetch_observable": False, "deviations": devs}}
    v = cd.reconcile_signals(lanes, {rule["file"]: text}, rules=[rule])
    assert any(rid == "signal_reconciliation" and "capability_adapter_tools" in why
               for _, rid, why in v)


def test_tool_missing_signal_with_declaration_is_clean_on_real_code():
    rule = _deepagents_rule()[0]
    text = (cd.ROOT / rule["file"]).read_text(encoding="utf-8", errors="replace")
    lanes = cd._load_lanes(cd.LANE_PROTOCOL)
    assert cd.reconcile_signals(lanes, {rule["file"]: text}, rules=[rule]) == []


# --- gateway-policy disclosure (two LLM doors; SPEC_ISSUES §2) --------------

def _gw_entry(code):
    return {"kind": "routing", "code": code, "human_zh": "z", "human_en": "e",
            "detail": "d"}


_GW_RULE = [{
    "file": "fake/gw.py",
    "signal": __import__("re").compile(r"fit_to_window"),
    "code": "gw_fit_to_window",
    "why": "qwen-only fit rescue",
}]


def test_gateway_signal_without_declaration_is_flagged():
    texts = {"fake/gw.py": 'if entry.get("fit_to_window"):\n    pass\n'}
    v = cd.check_gateway_policy([], texts, rules=_GW_RULE)
    assert any(rid == "gateway_policy" and "gw_fit_to_window" in why
               for _, rid, why in v)


def test_gateway_declared_signal_is_clean():
    texts = {"fake/gw.py": 'if entry.get("fit_to_window"):\n    pass\n'}
    assert cd.check_gateway_policy(
        [_gw_entry("gw_fit_to_window")], texts, rules=_GW_RULE) == []


def test_gateway_stale_declaration_is_flagged():
    # The mechanism was removed from the door; its disclosure must go too, or
    # the board describes policy the door no longer applies.
    texts = {"fake/gw.py": "x = 1\n"}
    v = cd.check_gateway_policy(
        [_gw_entry("gw_fit_to_window")], texts, rules=_GW_RULE)
    assert any("stale" in why for _, _, why in v)


def test_gateway_missing_proxy_file_fails_loud():
    v = cd.check_gateway_policy([], {"fake/gw.py": ""}, rules=_GW_RULE)
    assert any("cannot read" in why for _, _, why in v)


def test_gateway_schema_is_enforced_on_disclosure_entries():
    bad = {"kind": "routing", "code": "gw_fit_to_window"}  # no human/detail
    texts = {"fake/gw.py": 'if entry.get("fit_to_window"):\n    pass\n'}
    v = cd.check_gateway_policy([bad], texts, rules=_GW_RULE)
    reasons = "\n".join(why for _, _, why in v)
    assert "human_zh" in reasons and "human_en" in reasons and "detail" in reasons


def test_real_config_declares_every_live_door_mechanism():
    doc = cd._load_doc(cd.LANE_PROTOCOL)
    disclosures = (doc.get("backbone") or {}).get("gateway_policy_disclosures")
    texts = cd._read_signal_files(cd.GATEWAY_SIGNAL_RULES)
    assert cd.check_gateway_policy(disclosures, texts) == []
    declared = {d["code"] for d in disclosures}
    assert {"gw_fit_to_window", "gw_max_tokens_floor", "dsp_transient_retries",
            "dsp_think_strip", "dsp_json_schema_downgrade",
            "dsp_min_max_tokens"} <= declared


# --- red-on-old proof ------------------------------------------------------

def test_disclosure_gate_is_red_on_the_pre_gate_protocol(tmp_path, monkeypatch):
    old = subprocess.check_output(
        ["git", "show", "HEAD:config/lane_protocol.yaml"], cwd=ROOT)
    p = tmp_path / "old_lane_protocol.yaml"
    p.write_bytes(old)
    monkeypatch.setattr(cd, "LANE_PROTOCOL", p)
    v = cd.scan()
    kinds = {rid for _, rid, _ in v}
    # The pre-gate file has no machine-readable disclosure, no fetch_withhold
    # entries, no snippet_only entries, and gpt-researcher's retriever swap is
    # undeclared: all four families must fire.
    assert "deviation_schema" in kinds
    assert "fetch_withhold" in kinds
    assert "snippet_only" in kinds
    assert "signal_reconciliation" in kinds
    # The old file also had no backbone.gateway_policy_disclosures while both
    # proxy doors carried live mechanisms.
    assert "gateway_policy" in kinds
    assert len(v) > 20
