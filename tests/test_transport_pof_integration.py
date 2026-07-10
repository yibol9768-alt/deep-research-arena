"""proof_of_fetch must mean "the agent opened this page", or refuse to answer.

The axis used to be computed by matching the report's prose against a copy of
the page that the EVALUATOR fetched after the run. It could not see whether the
agent opened anything, so a model that guessed a URL which happened to exist and
paraphrased a page it never read scored exactly like one that retrieved and read
it. These tests pin the three behaviours that fix requires:

  1. with an evidence log, `pof` counts pages the shim actually served;
  2. without one, the axis is stamped `text_v1` and never silently upgraded;
  3. `require_transport_pof` refuses to score at all rather than fall back,
     because both fallbacks are wrong: the textual measure answers a different
     question, and scoring 0 accuses an unobserved lane of fabricating.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval import decidable_scorer as ds            # noqa: E402
from src.eval.answer_key import AnswerKey              # noqa: E402
from src.eval.closed_world_eval import evaluate        # noqa: E402
from src.eval.fetch_log import load_run_evidence       # noqa: E402


def test_recording_shim_image_is_single_process():
    """The active evidence bracket is process-local.

    With two Uvicorn workers, ``/_mark`` can open in worker A while the next
    ``/search`` or ``/fetch`` lands in worker B and is written unattributed.
    A benchmark worker therefore gets exactly one shim process.
    """
    dockerfile = (ROOT / "infra" / "Dockerfile.gateway").read_text()
    assert '\"--workers\", \"1\"' in dockerfile
    assert '\"--workers\", \"2\"' not in dockerfile


def test_ds_proxy_image_contains_shared_sampling_contract():
    dockerfile = (ROOT / "infra" / "Dockerfile.ds_proxy").read_text()
    assert "integrations/sampling_policy.py" in dockerfile
    assert "config/lane_protocol.yaml" in dockerfile
    assert "integrations.ds_proxy.app:app" in dockerfile
    assert "pyyaml" in dockerfile.lower()

U_WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/Coffee"
U_SHOP = "http://localhost:7770/p/12345"
U_FAKE = "http://localhost:7770/p/does-not-exist"

REPORT = f"""# Report

Coffee is a beverage ([wiki]({U_WIKI})).
It costs $12 ([shop]({U_SHOP})).
Also see ([other]({U_FAKE})).
"""

CACHE = {
    U_WIKI: {"status": 200, "text": "Coffee is a beverage."},
    U_SHOP: {"status": 200, "text": "Price $12"},
}


class _Registry:
    """Same predicate the reachability axis uses."""

    def classify(self, url: str) -> dict:
        return {"in_corpus": url in CACHE}


@pytest.fixture
def answer_key() -> AnswerKey:
    return AnswerKey.load(ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0001.json")


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    """A run that searched once, and opened only ONE of the pages it cites."""
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SHIM_EVIDENCE", "1")
    from integrations.search_shim import evidence as ev

    ev.reset_for_tests()
    ev.mark_start({"run_id": "r1", "lane": "demo", "task": "t0", "backbone": "b"})
    ev.record_search("coffee", [U_WIKI, U_SHOP], endpoint="/search")
    ev.record_fetch(U_WIKI, 200, b"Coffee is a beverage.", endpoint="/fetch")
    ev.mark_end({"run_id": "r1"})
    return load_run_evidence(tmp_path / "r1.jsonl")


def test_without_evidence_axis_is_stamped_text_v1(answer_key):
    out = evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5)
    assert out["pof_semantics"] == "text_v1"
    assert "transport" not in out
    # P1: a text_v1 report observed no fetch, so it MUST NOT wear the
    # proof_of_fetch name. It is emitted as grounding_quote_support instead.
    assert "grounding_proof_of_fetch" not in out["axes"]
    assert "grounding_quote_support" in out["axes"]


def test_with_evidence_pof_counts_only_opened_pages(answer_key, evidence):
    out = evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5,
                   evidence=evidence)
    assert out["pof_semantics"] == "transport_v2"
    # P1: transport_v2 witnessed a fetch, so it keeps the proof_of_fetch name and
    # never the quote_support name.
    assert "grounding_quote_support" not in out["axes"]
    # Three cited URLs, one of them opened. `axes` values are rounded to 4dp for
    # the board; `transport` carries the unrounded number, so compare with an
    # absolute tolerance rather than pretending they are bit-identical.
    assert out["axes"]["grounding_proof_of_fetch"] == pytest.approx(1 / 3, abs=1e-4)
    t = out["transport"]
    # The shop page is real, cited, never opened, but a search DID return it.
    # That is a shallow citation off a snippet, not parametric recall.
    assert t["snippet_only"] == pytest.approx(1 / 3)
    assert t["hallucinated_grounding"] == pytest.approx(0.0)
    # The third URL does not exist at all.
    assert t["fabrication"] == pytest.approx(1 / 3)
    # It was never returned by a search and never linked from a page that was
    # read, so fetching it later could not have laundered it into "searched".
    assert t["provenance_counts"] == {"searched": 2, "linked": 0, "guessed": 1}


def test_old_textual_measure_is_kept_as_quote_support(answer_key, evidence):
    """The textual number is not thrown away; it answers a different question.

    `pof` = did you open it. `quote_support` = having opened it, does what you
    wrote match. Collapsing the two is what made the axis unfalsifiable.
    """
    with_ev = evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5,
                       evidence=evidence)
    without = evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5)
    # The text_v1 number is preserved: as the transport report's `quote_support`
    # sidecar, and as the no-evidence report's honestly-named axis (P1). Both
    # equal the same underlying textual measure.
    assert with_ev["quote_support"] == without["axes"]["grounding_quote_support"]
    assert without["quote_support"] == without["axes"]["grounding_quote_support"]


def test_require_transport_pof_refuses_rather_than_falls_back(answer_key):
    """Neither fallback is acceptable, so there must not be one.

    Falling back to `text_v1` changes the axis's meaning without changing its
    name. Falling back to 0 accuses a lane whose fetches were never observed of
    citing pages it never read. Refuse.
    """
    with pytest.raises(ds.MissingEvidenceLog):
        evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5,
                 require_transport_pof=True)


def test_unavailable_evidence_never_scores_as_zero(answer_key, tmp_path):
    """An empty/absent log means "not observed", not "opened nothing"."""
    from src.eval.fetch_log import RunEvidence, transport_metrics

    m = transport_metrics([U_WIKI], RunEvidence(available=False),
                          in_registry=lambda u: True)
    assert m["available"] is False
    # The invariant, not the dict shape: an unobserved run yields NO score,
    # never a zero. `reason` says which kind of unobserved it is.
    assert "pof" not in m and "hallucinated_grounding" not in m
    assert m.get("reason")
    assert "pof" not in m

    out = evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5,
                   evidence=load_run_evidence(tmp_path / "missing.jsonl"))
    assert out["pof_semantics"] == "text_v1"


def test_fabrication_agrees_with_reach_by_construction(answer_key, evidence):
    """`fabrication` and `1 - reach` must use the same registry predicate.

    They are the same claim ("this URL is not in the frozen corpus") measured by
    two code paths. If they can disagree, one of them is lying.
    """
    out = evaluate(REPORT, answer_key, CACHE, registry=_Registry(), gamma=1.5,
                   evidence=evidence)
    assert out["transport"]["fabrication"] == pytest.approx(
        1.0 - out["axes"]["grounding_reach"], abs=1e-4)


def test_snippet_only_never_becomes_a_memory_accusation(tmp_path, monkeypatch):
    """A framework with no page-read step must not be charged with recall.

    storm and langchain-odr consume search snippets and never open a page
    (audit 2026-07-08). Under the merged definition every citation they make
    landed in `hallucinated_grounding`, i.e. the instrument said they answered
    from parametric memory. They did not: the shim handed them the URL and a
    snippet. `snippet_only` is the honest name for that, and it is what the
    board must show.
    """
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(tmp_path))
    from integrations.search_shim import evidence as ev
    from src.eval.fetch_log import transport_metrics

    ev.reset_for_tests()
    ev.mark_start({"run_id": "storm-like", "lane": "storm", "task": "t", "backbone": "b"})
    ev.record_search("coffee", [U_WIKI, U_SHOP], endpoint="/search")
    ev.mark_end({"run_id": "storm-like"})
    run_ev = load_run_evidence(tmp_path / "storm-like.jsonl")

    m = transport_metrics([U_WIKI, U_SHOP], run_ev, in_registry=lambda u: True)
    assert m["pof"] == 0.0                      # it opened nothing, truthfully
    assert m["snippet_only"] == 1.0             # it cited what search showed it
    assert m["hallucinated_grounding"] == 0.0   # and invented nothing
