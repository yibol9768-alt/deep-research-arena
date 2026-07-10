"""G6 gate: end-to-end no silent zero.

Two halves:

1. The CHECKER (scripts/check_no_silent_zero.py) applied to synthetic result
   directories covering the four mandated shapes -- NaN, 0 without reason,
   0 with reason, withheld -- plus the mixed-pof-semantics lane pattern, the
   legacy .score.json shape, tsv results, and the exit-code contract.

2. RED-ON-OLD regressions for the SPEC_ISSUES G6 implementation-bug fixes made
   in this lane. Each of these fails on the pre-fix code:
     - every scored 0 out of decidable_scorer carries a machine-readable reason
       code, per axis and in the score_report/evaluate axis_reasons map;
     - reach dedupes off-corpus URL spelling variants with the SAME identity
       transport uses (fetch_log.canonical), restoring fabrication == 1-reach;
     - aggregate()'s micro axes pool the same numerators/denominators the
       per-report axes use (distinct supported facts; sum of k_effective);
     - build_truth_board._axes_mean survives a lane that mixes pof semantics
       (so the rc=3 gate, not a KeyError, rejects the board);
     - jury _fit_one uses MAJORITY vote, not plurality-ignoring-ties;
     - jury _fit_one scores only the LATEST report-pair generation per pairing;
     - jury refuses to judge an empty question (missing task file);
     - bradley_terry.bootstrap_ci never fabricates 1000-anchor pseudo-draws for
       agents absent from a resample, and failed fits are counted, not silent.

Everything here is deterministic: fixed seeds, synthetic fixtures, no network,
no LLM. Fixtures that exercise scoring spell URLs across all three sources
(product / wiki / forum), per HANDOFF_2026-07-09 trap #1.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_no_silent_zero import (  # noqa: E402
    check,
    find_violations,
    main as checker_main,
    parse_file,
)
from src.eval import decidable_scorer as ds  # noqa: E402
from src.eval.closed_world_eval import evaluate  # noqa: E402
from src.eval.answer_key import AnswerKey  # noqa: E402
from src.eval.url_registry import UrlRegistry  # noqa: E402

KEY_PATH = ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0001.json"


def _write_json(p: pathlib.Path, obj) -> pathlib.Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def _report_json(axes: dict, axis_reasons: dict | None = None,
                 detail: dict | None = None, **extra) -> dict:
    out = {"agent": "laneX", "task": "t0001", "axes": axes,
           "axis_reasons": axis_reasons or {}, "detail": detail or {}}
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# 1. Checker: the four mandated shapes
# ---------------------------------------------------------------------------

def test_checker_flags_nan(tmp_path):
    _write_json(tmp_path / "a.json", _report_json(
        {"grounding_reach": float("nan"), "completeness": 0.5}))
    units, violations, parsed, _ = check(tmp_path)
    assert parsed == 1 and units
    assert [v.kind for v in violations] == ["nan"]
    assert violations[0].unit.axis == "grounding_reach"


def test_checker_flags_zero_without_reason(tmp_path):
    _write_json(tmp_path / "a.json", _report_json(
        {"grounding_reach": 0.0, "completeness": 0.5}))
    _, violations, _, _ = check(tmp_path)
    assert [v.kind for v in violations] == ["silent_zero"]
    assert violations[0].unit.axis == "grounding_reach"
    assert violations[0].unit.lane == "laneX"


def test_checker_accepts_zero_with_reason(tmp_path):
    _write_json(tmp_path / "a.json", _report_json(
        {"grounding_reach": 0.0, "completeness": 0.0},
        axis_reasons={"grounding_reach": "no_citations",
                      "completeness": "no_vital_covered"}))
    _, violations, _, _ = check(tmp_path)
    assert violations == []


def test_checker_accepts_withheld_axis(tmp_path):
    # Withhold spellings the pipeline actually produces: a null axis value; an
    # available=False axis-detail block (G4 stamps reason_code beside the
    # frozen prose); a canonical WithholdReason code (gates-L3-withhold enum);
    # the legacy withheld_* spelling stays tolerated.
    _write_json(tmp_path / "null_value.json", _report_json(
        {"grounding_proof_of_fetch": None, "completeness": 0.4}))
    _write_json(tmp_path / "available_false.json", _report_json(
        {"grounding_proof_of_fetch": 0.0, "completeness": 0.4},
        detail={"proof_of_fetch": {
            "available": False,
            "reason": "fetch_not_observable",
            "reason_code": "fetch_not_observable"}}))
    _write_json(tmp_path / "canonical_code.json", _report_json(
        {"grounding_proof_of_fetch": 0.0, "completeness": 0.4},
        axis_reasons={"grounding_proof_of_fetch": "no_evidence_log"}))
    _write_json(tmp_path / "legacy_prefix.json", _report_json(
        {"grounding_proof_of_fetch": 0.0, "completeness": 0.4},
        axis_reasons={"grounding_proof_of_fetch": "withheld_no_evidence_log"}))
    _, violations, parsed, _ = check(tmp_path)
    assert parsed == 4
    assert violations == []


def test_checker_accepts_g4_concept_withhold_shape(tmp_path):
    # G4's completeness observability fields: concept slots whose source page
    # the evaluator never cached are withheld (score/denominator unchanged).
    # A completeness 0 under this shape is explained, not silent.
    _write_json(tmp_path / "concept_withheld.json", _report_json(
        {"completeness": 0.0, "grounding_reach": 0.5},
        detail={"completeness": {
            "concept_nuggets_total": 3,
            "concept_withheld_count": 3,
            "concept_axis_withheld": True,
            "concept_axis_withheld_reason": "concept_page_not_cached",
        }}))
    _, violations, parsed, _ = check(tmp_path)
    assert parsed == 1
    assert violations == []


def test_checker_strict_withheld_requires_reason(tmp_path):
    _write_json(tmp_path / "a.json", _report_json(
        {"grounding_proof_of_fetch": None, "completeness": 0.4}))
    _, violations, _, _ = check(tmp_path, strict_withheld_reason=True)
    assert [v.kind for v in violations] == ["withheld_without_reason"]


def test_checker_flags_mixed_pof_semantics_lane(tmp_path):
    # One lane, two grounding-axis names: not comparable, must be flagged
    # (the board-crash-before-rc3 defect, SPEC_ISSUES G6).
    _write_json(tmp_path / "laneX__t1.json", _report_json(
        {"grounding_proof_of_fetch": 0.5}))
    _write_json(tmp_path / "laneX__t2.json", _report_json(
        {"grounding_quote_support": 0.5}))
    _, violations, _, _ = check(tmp_path)
    assert [v.kind for v in violations] == ["mixed_pof_semantics"]


def test_checker_reads_legacy_score_json(tmp_path):
    # The data/results/deep/*.score.json shape: axis blocks are top-level keys
    # carrying {"score": float, "details": {...}}. A legacy 0 without a reason
    # is exactly what the G6 dry-run is expected to surface.
    _write_json(tmp_path / "storm__t1.score.json", {
        "task": "t1",
        "url_reachability": {"score": 1.0, "passed": True, "details": {}},
        "analysis_depth": {"score": 0.0, "passed": False, "details": {}},
        "claim_nli": {"score": 0.0, "passed": False,
                      "details": {"reason": "no_claims_extracted"}},
    })
    _, violations, parsed, _ = check(tmp_path)
    assert parsed == 1
    assert [(v.kind, v.unit.axis) for v in violations] == \
        [("silent_zero", "analysis_depth")]


def test_checker_reads_tsv_long_form(tmp_path):
    (tmp_path / "r.tsv").write_text(
        "lane\ttask\taxis\tvalue\treason\n"
        "l1\tt1\tfact\t0.0\t\n"                       # silent zero
        "l1\tt1\treach\tnan\t\n"                      # NaN
        "l1\tt2\tfact\t0.0\tno_checkable_claims\n"    # explained zero
        "l2\tt1\tpof\t\t\n"                           # blank value = withheld
        "l2\tt2\tpof\t0.0\tno_evidence_log\n",        # canonical withhold code
        encoding="utf-8")
    _, violations, parsed, _ = check(tmp_path)
    assert parsed == 1
    kinds = sorted((v.kind, v.unit.axis) for v in violations)
    assert kinds == [("nan", "reach"), ("silent_zero", "fact")]


def test_checker_reads_board_json_replicates(tmp_path):
    # The build_truth_board per_task_summary shape: zeros inside replicate rows
    # must carry axis_reasons through aggregation (mandate: 汇总不丢弃).
    board = {"rows": [{
        "agent": "storm",
        "per_task_summary": {
            "t1": {"replicates": {
                "1": {"status": "pass",
                      "axes": {"grounding_reach": 0.0, "completeness": 0.3},
                      "axis_reasons": {"grounding_reach": "no_citations"}},
                "2": {"status": "missing",
                      "axes": {"grounding_reach": 0.0, "completeness": 0.0},
                      "axis_reasons": {"grounding_reach": "missing",
                                       "completeness": "missing"}},
            }},
            "t2": {"replicates": {
                "1": {"status": "pass",
                      "axes": {"grounding_reach": 0.0, "completeness": 0.3},
                      "axis_reasons": {}},   # the violation
            }},
        },
    }]}
    _write_json(tmp_path / "board.json", board)
    _, violations, parsed, _ = check(tmp_path)
    assert parsed == 1
    assert [(v.kind, v.unit.task) for v in violations] == \
        [("silent_zero", "t2#rep1")]


def test_checker_exit_codes(tmp_path, capsys):
    clean = tmp_path / "clean"
    _write_json(clean / "a.json", _report_json({"completeness": 0.4}))
    assert checker_main([str(clean), "--quiet"]) == 0

    dirty = tmp_path / "dirty"
    _write_json(dirty / "a.json", _report_json({"completeness": 0.0}))
    out = tmp_path / "report.txt"
    assert checker_main([str(dirty), "--out", str(out)]) == 1
    assert "silent_zero" in out.read_text()

    empty = tmp_path / "empty"
    empty.mkdir()
    assert checker_main([str(empty)]) == 2
    capsys.readouterr()


def test_checker_skips_unrelated_json(tmp_path):
    _write_json(tmp_path / "notes.json", {"hello": [1, 2, 3]})
    assert parse_file(tmp_path / "notes.json") == []


# ---------------------------------------------------------------------------
# 2. Reason-code pipeline (red on pre-G6 scorer: the fields did not exist)
# ---------------------------------------------------------------------------

def test_reach_zero_reasons():
    score, det = ds.score_reachability([], {})
    assert score == 0.0 and det["reason"] == "no_citations"
    # Off-corpus across all three source shapes (registry path).
    reg = UrlRegistry(products=[], submissions={}, wiki=[])
    urls = ["http://example.com/black-earhook-headphones.html",   # product-shaped
            "http://example.com/wiki/Bluetooth",                  # wiki-shaped
            "http://example.com/f/headphones/123/thread"]         # forum-shaped
    score, det = ds.score_reachability(urls, {}, registry=reg)
    assert score == 0.0 and det["reason"] == "all_citations_off_corpus"


def test_pof_zero_reasons():
    score, det = ds.score_proof_of_fetch("nothing cited here", {})
    assert score == 0.0 and det["reason"] == "no_citable_pages"
    # A cited, cached page with no verbatim support: checked and failed.
    cache = {"http://localhost:7770/x.html":
             {"status": 200, "text": "<html>totally different content</html>"}}
    md = "Unrelated prose. [x](http://localhost:7770/x.html)"
    score, det = ds.score_proof_of_fetch(md, cache)
    assert det["checked"] == 1
    assert score == 0.0 and det["reason"] == "no_quote_support"


def _pick_priced_entity(ak, generic):
    for e in ak.relevant_set:
        if getattr(e, "relevant", True) \
                and (e.facts or {}).get("price") is not None \
                and not any(ch in e.name for ch in ".!?") \
                and len(ds.name_key(e.name, generic).split()) >= 2:
            return e
    raise AssertionError("no usable priced entity in the golden key")


def test_fact_zero_reasons():
    ak = AnswerKey.load(str(KEY_PATH))
    generic = ds.build_generic_tokens(ak)
    # Silence: no checkable claim at all.
    score, det = ds.score_fact_support("Many people enjoy music.", ak,
                                       generic=generic)
    assert score == 0.0 and det["reason"] == "no_checkable_claims"
    # Error: a claim tested and contradicted -> a DIFFERENT reason code.
    ent = _pick_priced_entity(ak, generic)
    disp = ds.name_key(ent.name, generic).title()
    md = f"The {disp} costs $99999.99."
    score, det = ds.score_fact_support(md, ak, generic=generic)
    assert det["claims_tested"] >= 1 and det["contradicted"] >= 1
    assert score == 0.0 and det["reason"] == "no_supported_claims"


def test_completeness_and_spec_zero_reasons():
    ak = AnswerKey.load(str(KEY_PATH))
    score, det = ds.score_completeness("Nothing relevant.", ak)
    assert score == 0.0 and det["reason"] == "no_vital_covered"
    if ak.spec_requirements:
        score, det = ds.score_spec("", ak)
        if score == 0.0:
            assert det["reason"] == "no_spec_requirement_passed"


def test_score_report_axis_reasons_cover_every_zero_axis():
    ak = AnswerKey.load(str(KEY_PATH))
    s = ds.score_report("Headphones are popular. People enjoy music.", ak, {})
    reasons = s.detail["axis_reasons"]
    zero_axes = {"grounding_reach": s.reach,
                 ds._axis_key(s.detail["pof_semantics"]): s.proof_of_fetch,
                 "correctness_fact_support": s.fact_support,
                 "completeness": s.completeness,
                 "spec": s.spec}
    for axis, value in zero_axes.items():
        if value == 0.0:
            assert axis in reasons and reasons[axis], f"silent zero on {axis}"
    # And the codes are drawn from the declared enums: this lane's scored-zero
    # set, or (post-merge) G4's canonical WithholdReason codes.
    from scripts.check_no_silent_zero import WITHHOLD_CODES
    for code in reasons.values():
        assert (code in ds.ZERO_REASONS or code in WITHHOLD_CODES
                or code.startswith(ds.WITHHELD_REASON_PREFIX))


def test_evaluate_surfaces_axis_reasons_and_passes_checker(tmp_path):
    ak = AnswerKey.load(str(KEY_PATH))
    out = evaluate("Headphones are popular. People enjoy music.", ak, {})
    assert out["axis_reasons"]  # top-level, not only in detail
    for axis, v in out["axes"].items():
        if v == 0.0:
            assert axis in out["axis_reasons"]
    # End-to-end: the go-forward per-report json is checker-clean by construction.
    _write_json(tmp_path / "laneY__t1.json",
                json.loads(json.dumps(out, default=lambda o: None)))
    _, violations, parsed, _ = check(tmp_path)
    assert parsed == 1 and violations == []


# ---------------------------------------------------------------------------
# 3. SPEC_ISSUES G6 fix regressions (each red on the pre-fix code)
# ---------------------------------------------------------------------------

def test_reach_dedupes_offcorpus_variants_like_transport():
    """Spelling variants of ONE fabricated URL must count once, as transport
    counts them (fetch_log.canonical), across all three source shapes.
    Pre-fix: raw-string fallback keys -> den=7 here, reach=1/7."""
    reg = UrlRegistry(products=["real-product"], submissions={}, wiki=[])
    urls = [
        # product-shaped fabrication, three spellings of one page
        "http://evil.com/fake-product.html",
        "http://evil.com/fake-product.html#reviews",
        "https://evil.com/fake-product.html",
        # wiki-shaped fabrication, two spellings
        "http://evil.com/wiki/Fakepedia",
        "http://evil.com/wiki/Fakepedia#history",
        # forum-shaped fabrication, two spellings
        "http://evil.com/f/audio/42/fake-thread",
        "http://evil.com/f/audio/42/fake-thread/",
        # one real product page
        "http://localhost:7770/real-product.html",
    ]
    score, det = ds.score_reachability(urls, {}, registry=reg)
    # Same identity transport uses: distinct fetch_log.canonical forms of the
    # fabricated URLs (https on a NON-sandbox host stays distinct there too,
    # so 4 fabricated pages: the parity is with transport, not with a guess).
    from src.eval.fetch_log import canonical
    fab_pages = {canonical(u) for u in urls[:-1]}
    assert len(fab_pages) == 4
    assert det["den"] == len(fab_pages) + 1, det   # + the one real page
    assert det["num"] == 1
    assert score == 0.2                             # pre-fix: den=8, score=0.125


def test_aggregate_micro_matches_per_report_semantics():
    """Pre-fix: micro fact volume = tested (wrong claims bought volume) and
    micro completeness divided by k_star*n (per-report uses k_effective)."""
    rep = {"truth": 0.1, "detail": {"counts": {
        "fact_tested": 10, "fact_supported": 2, "fact_distinct_supported": 2,
        "comp_covered": 5, "comp_k_effective": 14,
        "reach_num": 0, "reach_den": 0, "pof_passed": 0, "pof_checked": 0,
        "spec_passed": 0, "spec_total": 0}}}
    agg = ds.aggregate([rep], k_f=10, k_star=20)
    p, rvol = 0.2, 2 / 10                  # distinct supported, NOT tested
    want_fact = 2 * p * rvol / (p + rvol)
    assert math.isclose(agg["micro_axes"]["fact_support"], round(want_fact, 4),
                        abs_tol=1e-4)
    assert math.isclose(agg["micro_axes"]["completeness"], round(5 / 14, 4),
                        abs_tol=1e-4)      # NOT 5/20


def test_board_axes_mean_survives_mixed_semantics_lane():
    """Pre-fix: build_truth_board indexed the first report's axis keys into
    every report and a mixed-semantics lane crashed with KeyError before the
    rc=3 gate could refuse the board."""
    from scripts.build_truth_board import _axes_mean
    cells = [
        {"axes": {"grounding_reach": 0.5, "grounding_proof_of_fetch": 1.0}},
        {"axes": {"grounding_reach": 0.5, "grounding_quote_support": 1.0}},
    ]
    keys = ("grounding_reach", "grounding_proof_of_fetch")
    means = _axes_mean(cells, keys, 2)      # must not raise
    assert means["grounding_reach"] == 0.5
    assert means["grounding_proof_of_fetch"] == 0.5


def _jury_rec(task, a, b, order, judge, winner, *, sha_a="X", sha_b="Y",
              ts=1.0, walkover=False):
    return {"ts": ts, "protocol": "uj_v2", "rubric_hash": "rh", "word_budget": 600,
            "backbone": "qwen3-8b", "task": task, "a": a, "b": b, "order": order,
            "judge": judge, "model_id": judge, "report_sha_a": sha_a,
            "report_sha_b": sha_b, "walkover": walkover,
            "winner": winner, "error": None}


def test_jury_majority_vote_not_plurality():
    """votes={tie,tie,A} must be a TIE under the design doc's majority rule.
    Pre-fix plurality crowned A on one vote against two tie ballots."""
    from scripts.run_usefulness_jury import fit_from_bank
    recs = [_jury_rec("t1", "alpha", "beta", "ab", j, w)
            for j, w in (("j1", "tie"), ("j2", "tie"), ("j3", "A"))]
    fit = fit_from_bank(recs, backbone="qwen3-8b")
    rows = fit["agents"]
    assert rows["alpha"]["n_ties"] == 1 and rows["alpha"]["n_wins"] == 0
    assert rows["beta"]["n_ties"] == 1 and rows["beta"]["n_losses"] == 0
    # A real majority still resolves: {A, A, tie} -> alpha wins.
    recs2 = [_jury_rec("t2", "alpha", "beta", "ab", j, w)
             for j, w in (("j1", "A"), ("j2", "A"), ("j3", "tie"))]
    fit2 = fit_from_bank(recs2, backbone="qwen3-8b")
    assert fit2["agents"]["alpha"]["n_wins"] == 1


def test_jury_fit_uses_latest_report_generation_only():
    """Two generations of one pairing in the bank: only the newest report pair
    may be scored. Pre-fix the 4-tuple item key pooled judges across
    generations ({j1:A, j2:A} from gen1 + {j3:B} from gen2 -> A won)."""
    from scripts.run_usefulness_jury import fit_from_bank
    recs = [
        _jury_rec("t1", "alpha", "beta", "ab", "j1", "A", sha_a="g1a", sha_b="g1b", ts=1.0),
        _jury_rec("t1", "alpha", "beta", "ab", "j2", "A", sha_a="g1a", sha_b="g1b", ts=1.0),
        _jury_rec("t1", "alpha", "beta", "ab", "j3", "B", sha_a="g2a", sha_b="g2b", ts=2.0),
    ]
    fit = fit_from_bank(recs, backbone="qwen3-8b")
    rows = fit["agents"]
    assert fit["n_superseded_generations"] == 1
    assert fit["n_items_ab_order_pairs"] == 1
    assert rows["beta"]["n_wins"] == 1, "latest generation's verdict must decide"
    assert rows["alpha"]["n_wins"] == 0


def test_jury_refuses_empty_question(tmp_path):
    """A missing task file must refuse, not judge an empty question as clean
    data. Pre-fix `load_intent(...) or ""` swallowed it silently."""
    import pytest
    from scripts.run_usefulness_jury import intent_for_battle
    with pytest.raises(FileNotFoundError, match="task_intent_missing"):
        intent_for_battle("no_such_task", tmp_path, walkover=False)
    # A walkover needs no intent: outcome is decided by report stubs.
    assert intent_for_battle("no_such_task", tmp_path, walkover=True) == ""


def test_bootstrap_ci_has_no_anchor_pseudo_observations():
    """A sparse agent absent from a resample must contribute NO draw. Pre-fix,
    `elo.get(a, ELO_ANCHOR)` fabricated a 1000-anchor draw for it, dragging its
    CI to the anchor; and failed fits vanished without a count."""
    from src.scoring import bradley_terry as bt
    battles = ([{"agent_a": "A", "agent_b": "B", "winner": "A"}] * 30
               + [{"agent_a": "A", "agent_b": "B", "winner": "B"}] * 10
               + [{"agent_a": "C", "agent_b": "A", "winner": "C"}])  # sparse C
    out = bt.bootstrap_ci(battles, n_boot=60, seed=7)
    row = out["C"]
    # C's battles fall out of ~1/e of resamples: its draw count must be REAL.
    assert row["n_boot"] < 55, "absent resamples must not add anchor draws"
    assert row["n_boot"] > 5
    # C only ever won; every genuine draw sits above the anchor, so the lower
    # CI bound cannot be the 1000 anchor the old pseudo-draws pinned it to.
    assert row["lo"] > 1000.0
    assert row["n_boot_requested"] == 60
    assert "n_boot_failed_fits" in row
