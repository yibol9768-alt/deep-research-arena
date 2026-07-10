"""reach / provenance / guessed columns + the provenance gate (ruling #8, revised).

The maintainer's revised ruling: the headline gate STAYS provenance under
transport_v2 (a cited URL is credited only when the run could have learned it),
it is NOT rolled back to reach, and the board publishes reach / provenance /
guessed side by side as diagnostics so the fetch-then-fabricate laundering the
provenance gate defends against is visible.

These pins:
  1. the board aggregation exposes the three fractions per lane and withholds
     provenance/guessed (None) on a text_v1 lane rather than fabricating them;
  2. under transport_v2 the truth gate_value IS transport['provenance'] and the
     gate_semantics stamp travels out of the scorer;
  3. a lane mixing gate semantics is flagged, never silently averaged.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_truth_board import _provenance_columns  # noqa: E402
from src.eval.answer_key import AnswerKey                   # noqa: E402
from src.eval.closed_world_eval import evaluate             # noqa: E402
from src.eval.fetch_log import load_run_evidence            # noqa: E402


# --- 1. board aggregation helper -------------------------------------------

def _text_v1_cell(reach: float):
    """An evaluate() output with no transport observation (text_v1)."""
    return {
        "axes": {"grounding_reach": reach},
        "gate_semantics": "reach_v1",
        "gate_value": reach,
    }


def _transport_cell(reach, provenance, n_cited, guessed):
    return {
        "axes": {"grounding_reach": reach},
        "gate_semantics": "provenance_v2",
        "gate_value": provenance,
        "transport": {
            "available": True,
            "provenance": provenance,
            "n_cited": n_cited,
            "provenance_counts": {"searched": n_cited - guessed, "linked": 0,
                                  "guessed": guessed},
        },
    }


def test_text_v1_lane_withholds_provenance_and_guessed():
    cols = _provenance_columns([_text_v1_cell(1.0), _text_v1_cell(0.0)])
    assert cols["reach_frac"] == 0.5
    assert cols["provenance_frac"] is None
    assert cols["guessed_frac"] is None
    assert cols["n_reports_with_transport"] == 0
    assert cols["gate_semantics"] == "reach_v1"


def test_transport_lane_reports_reach_provenance_guessed_side_by_side():
    cols = _provenance_columns([
        _transport_cell(reach=1.0, provenance=1.0, n_cited=3, guessed=0),
        _transport_cell(reach=1.0, provenance=1 / 3, n_cited=3, guessed=2),
    ])
    assert cols["reach_frac"] == 1.0            # membership: both fully in corpus
    assert cols["provenance_frac"] == pytest.approx((1.0 + 1 / 3) / 2, abs=1e-4)
    assert cols["guessed_frac"] == pytest.approx((0 / 3 + 2 / 3) / 2, abs=1e-4)
    assert cols["gate_semantics"] == "provenance_v2"
    # The gate the truth used is provenance, NOT reach: they differ here.
    assert cols["gate_value_mean"] != cols["reach_frac"]
    assert cols["gate_value_mean"] == cols["provenance_frac"]


def test_mixed_gate_within_a_lane_is_flagged_not_averaged_away():
    cols = _provenance_columns([
        _text_v1_cell(1.0),
        _transport_cell(reach=1.0, provenance=0.5, n_cited=2, guessed=1),
    ])
    assert cols["gate_semantics"] == "mixed"


# --- 2/3. the scorer's gate is provenance under transport -------------------

U_WIKI = "http://localhost:8090/content/wikipedia_en_all_nopic/Coffee"
U_SHOP = "http://localhost:7770/p/12345"
# In corpus (so reach counts it) but never searched/linked/fetched: a real URL
# recalled from parametric memory. provenance must NOT credit it; reach does.
U_GUESS = "http://localhost:8090/content/wikipedia_en_all_nopic/Espresso"
REPORT = (f"# Report\n\nCoffee is a beverage ([wiki]({U_WIKI})).\n"
          f"It costs $12 ([shop]({U_SHOP})).\nEspresso too ([guess]({U_GUESS})).\n")
CACHE = {U_WIKI: {"status": 200, "text": "Coffee is a beverage."},
         U_SHOP: {"status": 200, "text": "Price $12"},
         U_GUESS: {"status": 200, "text": "Espresso is a coffee."}}


class _Registry:
    def classify(self, url: str) -> dict:
        return {"in_corpus": url in CACHE}


def _answer_key() -> AnswerKey:
    return AnswerKey.load(
        ROOT / "data" / "golden" / "answer_keys" / "dr_cross_deep_0001.json")


def _evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIM_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("SHIM_EVIDENCE", "1")
    from integrations.search_shim import evidence as ev
    ev.reset_for_tests()
    ev.mark_start({"run_id": "r1", "lane": "demo", "task": "t0", "backbone": "b"})
    ev.record_search("coffee", [U_WIKI, U_SHOP], endpoint="/search")
    ev.record_fetch(U_WIKI, 200, b"Coffee is a beverage.", endpoint="/fetch")
    ev.mark_end({"run_id": "r1"})
    return load_run_evidence(tmp_path / "r1.jsonl")


def test_truth_gate_value_is_transport_provenance_under_transport(tmp_path, monkeypatch):
    ev = _evidence(tmp_path, monkeypatch)
    out = evaluate(REPORT, _answer_key(), CACHE, registry=_Registry(), gamma=1.5,
                   evidence=ev)
    assert out["pof_semantics"] == "transport_v2"
    assert out["gate_semantics"] == "provenance_v2"
    # The gate the truth number used is the provenance fraction, not reach.
    assert out["gate_value"] == pytest.approx(out["transport"]["provenance"], abs=1e-4)
    # And reach (membership) is strictly higher here: one guessed-real URL is in
    # corpus (reach counts it) but was never served (provenance does not).
    assert out["axes"]["grounding_reach"] > out["gate_value"]


def test_text_v1_gate_is_reach_when_no_transport(monkeypatch):
    out = evaluate(REPORT, _answer_key(), CACHE, registry=_Registry(), gamma=1.5)
    assert out["pof_semantics"] == "text_v1"
    assert out["gate_semantics"] == "reach_v1"
    assert out["gate_value"] == pytest.approx(out["axes"]["grounding_reach"], abs=1e-4)
