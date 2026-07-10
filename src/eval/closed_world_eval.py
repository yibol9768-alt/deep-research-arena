"""Closed-world evaluation harness: report + answer key (+ URL registry +
page cache) -> per-axis decidable scores + composed truth score
(METHODOLOGY_REDESIGN_2026-07-03.md section 2).

Decidable axes computed here (no model):
  axis 1a reachability   UrlRegistry membership when data/golden/
                         url_registry.json exists (G-F2/F8/F10); HTTP-cache
                         status fallback otherwise, flagged registry_missing
  axis 1b proof-of-fetch label-stripped, IDF-weighted, span-checked context
                         containment (G-F1)
  axis 2  fact support   volume-aware F1 of the report's own structured
                         claims vs DB truth; zero claims scores zero (M-C3)
  axis 3  completeness   saturating recall over the ranked vital pool (T1/T2)
  axis 4  spec           output-shape requirements

Composition (see decidable_scorer.compose_truth; FORMULA_LOCK K6):
  quality = 0.39*fact + 0.28*pof + 0.33*completeness
            (three evidence axes only, no floor)
  truth   = gate**gamma * quality

For transport_v2 runs, gate is provenance: the fraction of cited in-corpus
pages whose URL was searched, fetched, or linked from a fetched page. Raw reach
remains a diagnostic. Legacy text_v1 runs cannot observe provenance and retain
the old reach gate; the output stamps the distinction so boards cannot mix it.

Spec (output shape) is NOT part of truth: it is reported as a separate
"compliance" column. Presentation (the LLM jury) is likewise separate. Both may
only break ties, never overturn the truth ordering (M-C1). This harness is
fully offline and replayable.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.eval.answer_key import AnswerKey
from src.eval import decidable_scorer as ds

DEFAULT_REGISTRY_PATH = Path("data/golden/url_registry.json")


def load_registry(registry_path=DEFAULT_REGISTRY_PATH):
    """UrlRegistry when the registry file exists, else None (the scorer then
    falls back to the HTTP-cache status path and flags registry_missing)."""
    rp = Path(registry_path) if registry_path else None
    if rp is None or not rp.exists():
        return None
    from src.eval.url_registry import UrlRegistry
    return UrlRegistry.load(rp)


def evaluate(report_md: str, answer_key: AnswerKey, cache: dict | None = None,
             registry=None, gamma: float = ds.GAMMA_DEFAULT, **kw) -> dict:
    """Score one report.

    Pass ``evidence=`` (a ``src.eval.fetch_log.RunEvidence``) to score
    ``grounding_proof_of_fetch`` from what the shim actually served this run.
    Without it the axis falls back to the textual measure, is stamped
    ``pof_semantics="text_v1"`` and emitted under the honest name
    ``grounding_quote_support`` (NOT ``grounding_proof_of_fetch``, which would
    assert a fetch nothing observed; see decidable_scorer._axis_key). Pass
    ``require_transport_pof=True`` to make the fallback an error instead of a
    silent change of meaning.
    """
    s = ds.score_report(report_md, answer_key, cache or {}, registry=registry,
                        gamma=gamma, **kw)
    pof_sem = s.detail["pof_semantics"]
    out = {
        "axes": {
            "grounding_reach": round(s.reach, 4),
            # KEY tracks the semantics (P1): transport_v2 witnesses a fetch and
            # keeps `grounding_proof_of_fetch`; text_v1 witnesses none and is
            # named `grounding_quote_support`. A text_v1 report NEVER emits the
            # proof_of_fetch key. See decidable_scorer._axis_key.
            ds._axis_key(pof_sem): round(s.proof_of_fetch, 4),
            "correctness_fact_support": round(s.fact_support, 4),
            "completeness": round(s.completeness, 4),
            "spec": round(s.spec, 4),
        },
        "pof_semantics": pof_sem,
        "gate_semantics": s.detail["gate_semantics"],
        "gate_value": s.detail["gate_value"],
        "quote_support": s.detail["quote_support"],
        "floors_applied": s.detail["floors_applied"],
        "reach_detail": s.detail["reach"],
        "pof_detail": s.detail["proof_of_fetch"],
        "fact_contradicted": s.fact_contradicted,
        "fact_absent": s.fact_absent,
        "quality": round(s.quality, 4),
        "truth": round(s.truth, 6),
        "detail": s.detail,
    }
    t = s.detail.get("transport")
    if t and t.get("available"):
        # Diagnostics, not truth components. `snippet_only` is a real page cited
        # off the search snippet; `hallucinated_grounding` is a real page cited
        # that was never searched and never opened, which only the model's
        # parameters could have supplied.
        out["transport"] = {
            k: t[k] for k in
            ("pof", "provenance", "snippet_only", "hallucinated_grounding", "fabrication",
             "retrieval_utilization", "provenance_counts",
             "n_cited", "n_fetched", "n_searches")
            if k in t
        }
    return out


def evaluate_task(report_md: str, task_id: str, cache: dict | None = None,
                  keys_dir="data/golden/answer_keys",
                  registry_path=DEFAULT_REGISTRY_PATH, **kw) -> dict:
    ak = AnswerKey.load(Path(keys_dir) / f"{task_id}.json")
    out = evaluate(report_md, ak, cache,
                   registry=load_registry(registry_path), **kw)
    out["task_id"] = task_id
    return out


if __name__ == "__main__":
    import sys
    # score a real report file against its task's answer key (grounding needs
    # a cache json unless the URL registry exists; without either, axis-1 is 0
    # but fact/coverage/spec are real)
    report_path = sys.argv[1]
    task_id = sys.argv[2]
    cache_path = sys.argv[3] if len(sys.argv) > 3 else None
    cache = json.loads(Path(cache_path).read_text()) if cache_path else {}
    md = Path(report_path).read_text(errors="replace")
    out = evaluate_task(md, task_id, cache)
    print(json.dumps({k: out[k] for k in
                      ("task_id", "axes", "floors_applied", "reach_detail",
                       "pof_detail", "fact_contradicted", "fact_absent",
                       "quality", "truth")},
                     indent=2, ensure_ascii=False))
