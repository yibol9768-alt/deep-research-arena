"""Four defects the suite could not see, and the tests that now see them."""

from __future__ import annotations

import glob
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.build_truth_board as btb                  # noqa: E402
import src.eval.decidable_scorer as ds                   # noqa: E402
from src.eval.answer_key import AnswerKey, Nugget        # noqa: E402
from src.eval.url_registry import UrlRegistry            # noqa: E402


# --- completeness had an unreachable ceiling -------------------------------

def test_every_task_pool_is_smaller_than_k_star():
    """The premise of the bug: `min(covered/20, 1)` never saturates."""
    sizes = {len(ds.build_vital_pool(AnswerKey.load(f)))
             for f in sorted(glob.glob(str(ROOT / "data/golden/answer_keys/*.json")))}
    assert max(sizes) < ds.K_STAR_DEFAULT, sizes


def test_a_report_that_conveys_every_vital_fact_can_score_one():
    """It could not. The ceiling was pool/20 in [0.70, 0.85], and it differed per
    task, so completeness was not comparable across tasks either."""
    for f in sorted(glob.glob(str(ROOT / "data/golden/answer_keys/*.json")))[:12]:
        ak = AnswerKey.load(f)
        pool = ds.build_vital_pool(ak)
        denom = min(ds.K_STAR_DEFAULT, len(pool))
        assert min(len(pool) / denom, 1.0) == 1.0, f


# --- the board must not lend one attempt's evidence to another -------------

def _log(path, run_id, lane, task, t0, urls):
    recs = [{"ts": t0, "run_id": run_id, "lane": lane, "task": task,
             "kind": "mark", "phase": "start"}]
    for i, u in enumerate(urls):
        recs.append({"ts": t0 + 1 + i, "run_id": run_id, "kind": "fetch",
                     "url": u, "status": 200})
    recs.append({"ts": t0 + 10, "run_id": run_id, "kind": "mark", "phase": "end"})
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def test_a_rerun_is_scored_against_its_own_evidence(tmp_path):
    """The stalled attempt fetched one page before the watchdog killed it. The
    rerun fetched three. Keyed on (lane, task), glob order decided which log the
    rerun's report was scored against, and the lane could be charged with citing
    pages it never opened."""
    _log(tmp_path / "aaa_stalled.jsonl", "aaa_stalled", "flowsearcher-ds", "t3",
         100.0, ["http://localhost:8090/A/One"])
    _log(tmp_path / "zzz_rerun.jsonl", "zzz_rerun", "flowsearcher-ds", "t3",
         900.0, ["http://localhost:8090/A/One",
                 "http://localhost:8090/A/Two",
                 "http://localhost:8090/A/Three"])

    by_key, by_run = btb._index_evidence(tmp_path)

    assert set(by_run) == {"aaa_stalled", "zzz_rerun"}
    assert len(by_run["zzz_rerun"].fetched) == 3
    # Without a run_id the fallback must still pick the LAST attempt, not the
    # alphabetically last filename.
    assert len(by_key[("flowsearcher-ds", "t3")].fetched) == 3


# --- an abort before the agent ran is not a framework that produced nothing --

def test_infra_abort_is_rerunnable_not_a_delivered_zero(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    (reports / "gpt-researcher").mkdir(parents=True)
    (tmp_path / "gpt-researcher__dr_cross_deep_0007_matrix.meta.json").write_text(
        json.dumps({"status": "infra_abort", "attempts": 1,
                    "error": "sandbox source(s) down"}))

    st = btb._run_status(reports / "gpt-researcher", "dr_cross_deep_0007", tmp_path)
    assert st["status"] == "infra_abort"
    assert st["status"] in ("stalled", "infra_abort"), \
        "the board must treat it as our fault, not the lane's"


# --- the wiki rescue must not come back a fourth time ----------------------

def test_no_live_code_rewrites_public_wikipedia_into_the_corpus():
    """It was deleted from ldr and local_deep_researcher, and survived in
    `src/shim_intercept.py`, in the driver string `run_deep_task` injects, and in
    `ldr_runner`'s OWN driver string. Comments explaining the deletion are fine;
    code that performs it is not."""
    import re

    from scripts.check_parity import RULES, _strip_prose
    pat = dict((r[0], r[1]) for r in RULES)["wiki_url_rewrite"]

    offenders = []
    for f in list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "src").rglob("*.py")) \
            + list((ROOT / "integrations").rglob("*.py")):
        if "check_parity" in f.name:
            continue        # it necessarily contains the pattern
        if re.search(pat, _strip_prose(f.read_text(errors="replace")), re.I):
            offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, offenders


# --- two more, found by the audit round that was stopped -------------------

def test_concept_coverage_is_not_scheme_sensitive():
    """`extract_citations` canonicalises the PATH but keeps the scheme and the
    `127.0.0.1` spelling. Models write `https://` constantly. Comparing raw
    strings zeroed concept coverage for every lane that cited the wiki over
    https -- the same mismatch that made `pof` read 0 before `fetch_log.canonical`
    normalised scheme and host, reintroduced one axis over."""
    source = ("http://localhost:8090/content/wikipedia_en_all_nopic/"
              "A/Bluetooth")
    ak = AnswerKey(task_id="scheme", vital_nuggets=[Nugget(
        text="Explains Bluetooth", subject="Bluetooth",
        predicate="concept_coverage", object="Bluetooth",
        source_url=source, importance="vital")])
    body = ("Bluetooth is a short-range wireless technology standard used for "
            "exchanging data between fixed and mobile devices.")
    cache = {source: {"status": 200, "text": body}}
    registry = UrlRegistry.load(ROOT / "data/golden/url_registry.json")
    spellings = [
        "http://localhost:8090/wiki/Bluetooth",
        "https://localhost:8090/wiki/Bluetooth",
        "http://127.0.0.1:8090/content/wikipedia_en_all_nopic/A/Bluetooth",
        "http://localhost:8090/wiki/Bluetooth#History",
    ]
    covered = {ds.score_completeness(
        f"{body} [w]({u})", ak, k_star=1, cache=cache,
        registry=registry)[1]["covered"]
               for u in spellings}
    assert covered == {1}, covered
    assert ds.score_completeness(
        body, ak, k_star=1, cache=cache, registry=registry)[1]["covered"] == 0, \
        "a concept must still require citing its wiki article"


def test_ambiguous_sidecars_fail_loud_instead_of_picking_one(tmp_path):
    """The meta filename is `<agent>__<task><suffix>.meta.json` and carries no
    backbone. One meta-dir holding two backbones offered several sidecars for the
    same (agent, task), and rc=4, rc=6 and the run_id used to pin transport
    evidence could all read another run's meta."""
    reports = tmp_path / "reports"
    (reports / "storm").mkdir(parents=True)
    meta = tmp_path / "m"
    meta.mkdir()
    (meta / "storm__t1_matrix.meta.json").write_text(
        json.dumps({"backbone": "qwen3-8b", "run_id": "A", "status": "ok"}))
    (meta / "storm__t1_smoke.meta.json").write_text(
        json.dumps({"backbone": "deepseek-v4", "run_id": "B", "status": "stalled"}))

    with pytest.raises(ValueError, match="cannot tell which run"):
        btb._run_status(reports / "storm", "t1", meta)

    assert btb._run_status(reports / "storm", "t1", meta, "qwen3-8b")["run_id"] == "A"
    assert btb._run_status(reports / "storm", "t1", meta, "deepseek-v4")["status"] == "stalled"
