"""G4 gate: withhold, never zero (GOAL_GATES_V1.md).

A `0` must always mean "the instrument observed it and it is genuinely absent".
When the instrument was BLIND -- no evidence log, a damaged or incomplete log,
an off-shim lane, a page the evaluator never cached -- the score is withheld:
`available=False` (or an explicit `*_withheld` detail field) plus a
machine-readable reason code from `decidable_scorer.WithholdReason`. Scoring a
blind instrument as 0 is a false accusation (HANDOFF_2026-07-09.md section 7).

Every test here stages a report that is IMPECCABLE on the axis under test and
then blinds the instrument one way; the assertion is always "withheld with a
reason", never "scored 0". Fixtures span all three sources (shopping 7770 /
wiki 8090 / forum 9999).

Instrument-missing paths enumerated (task G4):

  1. no fetch_log / malformed brackets  -> transport withhold (13 log shapes)
  2. page cache missing a concept page  -> concept_axis_withheld detail
     (score/denominator FROZEN: observability only, see SPEC_ISSUES)
  3. damaged log / records lost to _unattributed.jsonl -> transport withhold
  4. fetch_observable=false lanes (8/12) -> transport withhold AND completeness
     falls back to the cache-quote criterion instead of demanding a fetch the
     shim never saw (the fix this file regression-pins)

Plus: the WithholdReason enum is total over every live reason string, and the
kiwix /A/<id> vs /<id> redirect double-spelling is pinned as ONE page identity
(the double-spelling false-accusation class).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.answer_key import AnswerKey, Entity, Nugget  # noqa: E402
from src.eval.fetch_log import (  # noqa: E402
    RunEvidence,
    canonical,
    load_run_evidence,
)
from src.eval import decidable_scorer as ds  # noqa: E402
from src.eval.decidable_scorer import (  # noqa: E402
    MissingEvidenceLog,
    WithholdReason,
    withhold_reason_code,
)
from src.eval.url_registry import UrlRegistry  # noqa: E402


# --- three-source fixture -----------------------------------------------------

PRODUCT = "http://localhost:7770/sony-wh1000.html"
WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth"
WIKI_REDIRECT = "http://localhost:8090/content/wikipedia_en_all_nopic/Bluetooth"
WIKI_SHORT = "http://localhost:8090/A/Bluetooth"
WIKI_WIKI = "http://localhost:8090/wiki/Bluetooth"
FORUM = "http://localhost:9999/f/headphones/20234"

WIKI_PAGE = (
    "Bluetooth is a short-range wireless technology standard using UHF radio "
    "waves for exchanging data between fixed and mobile devices over short "
    "distances. It employs frequency-hopping spread spectrum across "
    "seventy-nine designated channels in the industrial scientific and medical "
    "band, and a master device may communicate with up to seven paired devices."
)
FORUM_PAGE = (
    "Owners say active noise cancellation helps bus commuters and noisy office "
    "workers hear their music clearly at lower volumes. Long listening "
    "sessions can still feel uncomfortable around the ears after several "
    "hours. Several commuters recommend taking short breaks during a long "
    "ride, and most agree the isolation is worth the occasional pressure."
)

# One report that earns every slot: a true product price, a quoted wiki
# concept, a quoted on-topic forum thread. Each quote sits in PROSE directly
# before its citation (a quote inside a link label is stripped by the
# verbatim-evidence judge, by design), and each section is long enough that
# the 400-char evidence window before its citation is dominated by its own
# source's text. "Impeccable report, blinded instrument."
REPORT = (
    f"The Sony WH-1000 sells for $278.00 [spec]({PRODUCT}).\n\n"
    f"{WIKI_PAGE} [background]({WIKI})\n\n"
    f"{FORUM_PAGE} [thread]({FORUM})"
)

CACHE_FULL = {
    WIKI: {"status": 200, "text": WIKI_PAGE},
    FORUM: {"status": 200, "text": FORUM_PAGE},
}
# The instrument gap under test in path 2: the concept page was never cached.
CACHE_NO_WIKI = {
    FORUM: {"status": 200, "text": FORUM_PAGE},
}

REG = UrlRegistry.load()  # local file + bloom, no network


def three_source_key() -> AnswerKey:
    return AnswerKey(
        task_id="g4",
        relevant_set=[
            Entity(PRODUCT, "Sony WH-1000", "shopping_product",
                   {"price": "278.00"}),
        ],
        vital_nuggets=[
            Nugget(text="price", subject="Sony WH-1000", predicate="price",
                   object="278.00", source_url=PRODUCT, importance="vital"),
            Nugget(text="concept", subject="Bluetooth",
                   predicate="concept_coverage", object="Bluetooth",
                   source_url=WIKI, importance="vital"),
        ],
        metadata={
            "forums": ["headphones"],
            "forum_core_keywords": ["headphones", "audio"],
            "forum_query_keywords": ["noise", "cancellation", "bus", "office"],
        },
    )


def _score_comp(cache, evidence=None):
    return ds.score_completeness(REPORT, three_source_key(), k_star=3,
                                 cache=cache, registry=REG, evidence=evidence)


ALWAYS = lambda u: True  # noqa: E731


def _write_log(path: Path, records) -> None:
    path.write_text("\n".join(json.dumps(r) if isinstance(r, dict) else r
                              for r in records) + "\n")


def _mk(ts, kind, phase=None, **kw):
    rec = {"ts": ts, "run_id": "r", "worker": "w0", "kind": kind}
    if phase:
        rec["phase"] = phase
    rec.update(kw)
    return rec


def _healthy_records():
    """A complete bracket whose traffic spans all three sources."""
    return [
        _mk(1.0, "mark", "start"),
        _mk(2.0, "fetch", url=PRODUCT, status=200, links=[]),
        _mk(3.0, "fetch", url=WIKI, status=200, links=[]),
        _mk(4.0, "search", urls_returned=[FORUM]),
        _mk(5.0, "mark", "end"),
    ]


CITED = [PRODUCT, WIKI, FORUM]


# ===========================================================================
# Path 1: no fetch_log / malformed evidence brackets
# ===========================================================================

def test_missing_log_withholds_with_reason_code(tmp_path):
    ev = load_run_evidence(tmp_path / "never_written.jsonl")
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert "pof" not in m and "fabrication" not in m
    assert m["reason"] == "no evidence log"
    assert m["reason_code"] == WithholdReason.NO_EVIDENCE_LOG.value


def test_no_evidence_object_at_score_report_level_never_zeroes_pof():
    """evidence=None: pof keeps its text_v1 meaning, gate stays reach_v1.

    The transport number must not silently become 0; the semantics stamp is the
    guard against mixing the two meanings on one board.
    """
    out = ds.score_report(REPORT, three_source_key(), CACHE_FULL, registry=REG,
                          evidence=None)
    assert out.detail["pof_semantics"] == "text_v1"
    assert out.detail["gate_semantics"] == "reach_v1"
    assert out.detail["transport"] is None


def test_unavailable_evidence_at_score_report_level(tmp_path):
    ev = load_run_evidence(tmp_path / "none.jsonl")
    out = ds.score_report(REPORT, three_source_key(), CACHE_FULL, registry=REG,
                          evidence=ev)
    t = out.detail["transport"]
    assert t["available"] is False
    assert t["reason_code"] == WithholdReason.NO_EVIDENCE_LOG.value
    # pof fell back to the textual measure, it was NOT transport-zeroed.
    assert out.detail["pof_semantics"] == "text_v1"
    assert out.detail["gate_semantics"] == "reach_v1"


def test_require_transport_pof_refuses_rather_than_scoring(tmp_path):
    ev = load_run_evidence(tmp_path / "none.jsonl")
    with pytest.raises(MissingEvidenceLog):
        ds.score_report(REPORT, three_source_key(), CACHE_FULL, registry=REG,
                        evidence=ev, require_transport_pof=True)
    with pytest.raises(MissingEvidenceLog):
        ds.score_report(REPORT, three_source_key(), CACHE_FULL, registry=REG,
                        evidence=None, require_transport_pof=True)


@pytest.mark.parametrize("mutate, expected_code", [
    # empty file
    (lambda recs: [], WithholdReason.EMPTY_EVIDENCE_LOG),
    # bracket-shape failures
    (lambda recs: recs[1:], WithholdReason.MISSING_START_MARK),
    (lambda recs: recs[:-1], WithholdReason.MISSING_END_MARK),
    (lambda recs: [recs[0]] + recs, WithholdReason.MULTIPLE_START_MARKS),
    (lambda recs: recs + [recs[-1]], WithholdReason.MULTIPLE_END_MARKS),
    (lambda recs: recs + [_mk(9.0, "fetch", url=FORUM, status=200)],
     WithholdReason.TRAFFIC_AFTER_END),
    # orphan reclaim writes an end mark stamped orphaned=True
    (lambda recs: recs[:-1] + [_mk(5.0, "mark", "end", orphaned=True)],
     WithholdReason.ORPHANED_BRACKET),
    # timestamp failures
    (lambda recs: [{**recs[0], "ts": "not-a-ts"}] + recs[1:],
     WithholdReason.INVALID_TIMESTAMP),
    (lambda recs: recs[:-1] + [{**recs[-1], "ts": None}],
     WithholdReason.INVALID_TIMESTAMP),
    (lambda recs: [{**recs[0], "ts": 50.0}] + recs[1:],
     WithholdReason.END_BEFORE_START),
    # one log mixing two runs
    (lambda recs: recs[:2] + [{**recs[2], "run_id": "other"}] + recs[3:],
     WithholdReason.LOG_MULTIPLE_RUN_IDS),
])
def test_malformed_bracket_withholds_never_zero(tmp_path, mutate, expected_code):
    log = tmp_path / "r.jsonl"
    records = mutate(_healthy_records())
    if records:
        _write_log(log, records)
    else:
        log.write_text("")
    ev = load_run_evidence(log)
    assert ev.available is False
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert "pof" not in m and "hallucinated_grounding" not in m
    assert m["reason_code"] == expected_code.value


def test_healthy_log_control_case_scores_instead_of_withholding(tmp_path):
    """The withhold paths must not over-trigger: the same traffic with a clean
    bracket produces a real transport block (this is what makes the withhold
    assertions above meaningful)."""
    log = tmp_path / "r.jsonl"
    _write_log(log, _healthy_records())
    ev = load_run_evidence(log)
    assert ev.available is True
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is True
    assert "reason_code" not in m
    assert m["pof"] > 0.0  # product + wiki were served


# ===========================================================================
# Path 2: page cache missing the concept page (score_completeness)
# ===========================================================================

def test_concept_cache_missing_is_observable_as_withheld_not_a_bare_zero():
    """The evaluator never cached the concept's source page: the same impeccable
    report loses the concept slot for an INSTRUMENT reason. Semantics are frozen
    (score and denominator unchanged, see SPEC_ISSUES), so the gate here is
    observability: the detail must say the concept axis was withheld and why,
    so a board can never present that 0 as an earned miss. Red on old code:
    these fields did not exist."""
    score, det = _score_comp(CACHE_NO_WIKI)
    assert det["concept_axis_withheld"] is True
    assert det["concept_withheld_count"] == 1
    assert det["concept_nuggets_total"] == 1
    assert det["concept_axis_withheld_reason"] == \
        WithholdReason.CONCEPT_PAGE_NOT_CACHED.value
    # Frozen scoring: product + forum still earn, concept contributes 0,
    # denominator does NOT move (observability only).
    assert det["k_effective"] == 3
    assert det["covered"] == 2
    assert score == pytest.approx(2 / 3)


def test_concept_cache_present_is_not_withheld():
    score, det = _score_comp(CACHE_FULL)
    assert score == 1.0
    assert det["concept_axis_withheld"] is False
    assert det["concept_withheld_count"] == 0
    assert det["concept_axis_withheld_reason"] is None
    assert det["covered_by_predicate"]["concept_coverage"] == 1
    assert det["forum_covered"] is True


def test_concept_in_cache_but_not_quoted_is_a_real_miss_not_withheld():
    """The mirror control: page IS cached, prose does not quote it. That 0 is
    earned and must NOT be labelled withheld, or withhold stops meaning
    anything."""
    report = (
        f"The Sony WH-1000 sells for $278.00 [spec]({PRODUCT}).\n\n"
        f"Bluetooth exists. [background]({WIKI})\n\n"  # shell, no quote
        f"{FORUM_PAGE} [thread]({FORUM})"
    )
    _, det = ds.score_completeness(report, three_source_key(), k_star=3,
                                   cache=CACHE_FULL, registry=REG)
    assert det["concept_axis_withheld"] is False
    assert det["covered_by_predicate"].get("concept_coverage", 0) == 0


def test_concept_withheld_detail_reaches_score_report_output():
    """build_truth_board reads score_report().detail; the withhold signal must
    survive to that surface or the board stays blind."""
    out = ds.score_report(REPORT, three_source_key(), CACHE_NO_WIKI,
                          registry=REG, k_star=3)
    cd = out.detail["completeness"]
    assert cd["concept_axis_withheld"] is True
    assert cd["concept_axis_withheld_reason"] == \
        WithholdReason.CONCEPT_PAGE_NOT_CACHED.value


# ===========================================================================
# Path 3: damaged log / records lost to _unattributed.jsonl
# ===========================================================================

def test_damaged_log_withholds_with_code(tmp_path):
    log = tmp_path / "r.jsonl"
    recs = _healthy_records()
    _write_log(log, recs[:2] + ["{this line lost a flush"] + recs[2:])
    ev = load_run_evidence(log)
    assert ev.available is True and ev.write_errors == 1
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert "pof" not in m
    assert m["reason_code"] == WithholdReason.LOG_DAMAGED.value


def test_unattributed_records_in_window_withhold_with_code(tmp_path):
    log = tmp_path / "r.jsonl"
    _write_log(log, _healthy_records())
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 3.5, "run_id": None, "worker": "w0", "kind": "fetch",
         "url": FORUM, "status": 200},
    ])
    ev = load_run_evidence(log)
    assert ev.available is True and ev.unattributed_in_window == 1
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert m["reason_code"] == WithholdReason.LOG_INCOMPLETE_UNATTRIBUTED.value


def test_unlabelled_unattributed_record_withholds_as_ambiguous(tmp_path):
    log = tmp_path / "r.jsonl"
    _write_log(log, _healthy_records())
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 3.5, "run_id": None, "kind": "fetch", "url": WIKI},
    ])
    ev = load_run_evidence(log)
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert m["reason_code"] == WithholdReason.ISOLATION_AMBIGUOUS.value


def test_shim_restart_tail_cannot_slip_past_the_window(tmp_path):
    """R5 candidate 'unattributed tail with ts > t_end is not counted': on
    current code the restart that strands that tail also loses the bracket, so
    the run log has no end mark and is withheld BEFORE the window question can
    arise. Pinned here as the disposition of that candidate."""
    log = tmp_path / "r.jsonl"
    _write_log(log, _healthy_records()[:-1])  # restart: end mark never written
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 99.0, "run_id": None, "worker": "w0", "kind": "fetch",
         "url": PRODUCT, "status": 200},
    ])
    ev = load_run_evidence(log)
    assert ev.available is False
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert m["reason_code"] == WithholdReason.MISSING_END_MARK.value


# ===========================================================================
# Path 4: fetch_observable=false lanes (8/12) -- withhold, and completeness
# must NOT convert the withhold into a zero
# ===========================================================================

def _offshim_log(tmp_path) -> Path:
    log = tmp_path / "r.jsonl"
    recs = _healthy_records()
    # The harness stamps the declaration on every record of the bracket. An
    # off-shim lane's log typically has no fetch records at all.
    recs = [dict(r, fetch_observable=False) for r in recs
            if r["kind"] != "fetch"]
    _write_log(log, recs)
    return log


def test_fetch_observable_false_withholds_pof(tmp_path):
    ev = load_run_evidence(_offshim_log(tmp_path))
    assert ev.available is True and ev.fetch_observable is False
    m = ds.transport_metrics_for(CITED, ev, registry=REG, cache=CACHE_FULL)
    assert m["available"] is False
    assert "pof" not in m
    assert m["reason"] == "fetch_not_observable"
    assert m["reason_code"] == WithholdReason.FETCH_NOT_OBSERVABLE.value


def test_offshim_score_report_keeps_text_semantics_never_transport_zero(tmp_path):
    ev = load_run_evidence(_offshim_log(tmp_path))
    out = ds.score_report(REPORT, three_source_key(), CACHE_FULL, registry=REG,
                          evidence=ev, k_star=3)
    assert out.detail["transport"]["reason_code"] == \
        WithholdReason.FETCH_NOT_OBSERVABLE.value
    assert out.detail["pof_semantics"] == "text_v1"
    assert out.detail["gate_semantics"] == "reach_v1"


def test_offshim_lane_completeness_falls_back_instead_of_zeroing(tmp_path):
    """THE regression this lane fixes (red on old code).

    Old behaviour: score_completeness keyed its fetch requirement on
    `evidence.available` alone. An off-shim lane's log is available, its
    fetched_ok is empty FOR AN INSTRUMENT REASON, so the impeccable concept and
    forum slots scored 0 while pof was (correctly) withheld -- the withhold was
    silently converted into a completeness zero. Now the fetch requirement is
    keyed on transport USABILITY (same gate transport_metrics uses) and falls
    back to the cache-quote criterion, exactly like pof falls back to text_v1.
    """
    ev = load_run_evidence(_offshim_log(tmp_path))
    score, det = _score_comp(CACHE_FULL, evidence=ev)
    assert det["concept_transport_required"] is False
    assert det["covered"] == 3  # product + concept + forum, all earned
    assert det["forum_covered"] is True
    assert score == 1.0


def test_damaged_log_completeness_falls_back_instead_of_zeroing(tmp_path):
    """Same class, different blinding: a damaged log withholds pof, so the
    fetch requirement it feeds must not survive to zero completeness. Red on
    old code."""
    log = tmp_path / "r.jsonl"
    recs = _healthy_records()
    _write_log(log, recs[:2] + ["{torn write"] + recs[2:])
    ev = load_run_evidence(log)
    assert ev.available is True and ev.write_errors
    score, det = _score_comp(CACHE_FULL, evidence=ev)
    assert det["concept_transport_required"] is False
    assert score == 1.0


def test_unattributed_loss_completeness_falls_back_instead_of_zeroing(tmp_path):
    """Records lost to _unattributed.jsonl make fetched_ok incomplete; the
    concept/forum fetch requirement must fall back, not accuse. Red on old
    code."""
    log = tmp_path / "r.jsonl"
    _write_log(log, _healthy_records())
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 3.5, "run_id": None, "worker": "w0", "kind": "fetch",
         "url": WIKI, "status": 200},
    ])
    ev = load_run_evidence(log)
    score, det = _score_comp(CACHE_FULL, evidence=ev)
    assert det["concept_transport_required"] is False
    assert score == 1.0


def test_usable_transport_still_requires_the_fetch_not_weakened(tmp_path):
    """Guard against over-correction: with a HEALTHY, observable log whose
    fetched_ok lacks the concept and forum pages, the strict requirement must
    still apply. The agent really did not open them; those zeros are earned."""
    log = tmp_path / "r.jsonl"
    _write_log(log, [
        _mk(1.0, "mark", "start"),
        _mk(2.0, "search", urls_returned=[PRODUCT]),
        _mk(3.0, "mark", "end"),
    ])
    ev = load_run_evidence(log)
    assert ev.available is True and ev.fetch_observable is True
    score, det = _score_comp(CACHE_FULL, evidence=ev)
    assert det["concept_transport_required"] is True
    assert det["covered_by_predicate"].get("concept_coverage", 0) == 0
    assert det["forum_covered"] is False
    assert det["covered"] == 1  # only the product price nugget
    assert score == pytest.approx(1 / 3)


def test_fetched_via_shim_earns_the_slots_control_case(tmp_path):
    """Full-visibility control: healthy log, concept and forum pages actually
    served -> everything earns. Withhold logic must not leak into the happy
    path."""
    log = tmp_path / "r.jsonl"
    _write_log(log, [
        _mk(1.0, "mark", "start"),
        _mk(2.0, "fetch", url=WIKI, status=200, links=[]),
        _mk(3.0, "fetch", url=FORUM, status=200, links=[]),
        _mk(4.0, "mark", "end"),
    ])
    ev = load_run_evidence(log)
    score, det = _score_comp(CACHE_FULL, evidence=ev)
    assert det["concept_transport_required"] is True
    assert score == 1.0


# ===========================================================================
# WithholdReason: one enum, total over the live reason strings (G6 foundation)
# ===========================================================================

def test_every_live_withhold_reason_maps_to_a_code():
    live_strings = [
        "no evidence log",
        "empty evidence log",
        "evidence log mixes multiple run_id values",
        "evidence log missing start mark",
        "evidence log has 2 start marks",
        "evidence log missing end mark (possible shim restart or killed run)",
        "evidence log has 2 end marks",
        "evidence log has traffic after its end mark",
        "evidence bracket was orphaned and reclaimed",
        "evidence start mark has no valid timestamp",
        "evidence end mark has no valid timestamp",
        "evidence end mark precedes start mark",
        "evidence log damaged: 3 unparseable record(s)",
        "evidence log incomplete: 2 record(s) landed unattributed inside this "
        "run's window",
        "evidence isolation is ambiguous: 1 unattributed record(s) could not "
        "be assigned to a worker",
        "fetch_not_observable",
        # written by the board indexer when two workers share a run_id
        "evidence fragments for run 'r' disagree on worker",
    ]
    for s in live_strings:
        assert withhold_reason_code(s) is not WithholdReason.UNKNOWN, s


def test_unknown_strings_map_to_unknown_not_a_guess():
    assert withhold_reason_code("") is WithholdReason.UNKNOWN
    assert withhold_reason_code(None) is WithholdReason.UNKNOWN
    assert withhold_reason_code("the dog ate the log") is WithholdReason.UNKNOWN


def test_reason_codes_are_unique():
    values = [m.value for m in WithholdReason]
    assert len(values) == len(set(values))


# ===========================================================================
# kiwix double-spelling: /A/<id> and the 302 target /<id> are ONE page
# ===========================================================================

def test_kiwix_spellings_share_one_page_identity():
    """kiwix 302s /content/<book>/A/<id> to /content/<book>/<id>; answer keys
    use the /A/ form and models also write /wiki/<id>. If these were different
    identities, a lane that opened the page would be charged with never
    fetching it -- the double-spelling false-accusation class. Pinned merged."""
    ids = {ds._page_identity(u, REG)
           for u in (WIKI, WIKI_REDIRECT, WIKI_SHORT, WIKI_WIKI)}
    assert ids == {WIKI}


def test_concept_credit_survives_the_redirect_spelling():
    """Answer key says /A/Bluetooth; the agent fetched, cached and cited the
    302 target spelling. The concept must still be credited end to end."""
    report = (
        f"The Sony WH-1000 sells for $278.00 [spec]({PRODUCT}).\n\n"
        f"{WIKI_PAGE} [background]({WIKI_REDIRECT})\n\n"
        f"{FORUM_PAGE} [thread]({FORUM})"
    )
    cache = {
        WIKI_REDIRECT: {"status": 200, "text": WIKI_PAGE},
        FORUM: {"status": 200, "text": FORUM_PAGE},
    }
    ev = RunEvidence(available=True)
    ev.fetched[canonical(WIKI_REDIRECT)] = {"status": 200}
    ev.fetched[canonical(FORUM)] = {"status": 200}
    score, det = ds.score_completeness(report, three_source_key(), k_star=3,
                                       cache=cache, registry=REG, evidence=ev)
    assert det["covered_by_predicate"]["concept_coverage"] == 1
    assert det["concept_axis_withheld"] is False
    assert score == 1.0
