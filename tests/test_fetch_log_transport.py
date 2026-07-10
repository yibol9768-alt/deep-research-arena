"""Transport-metric derivations (src/eval/fetch_log.py).

Each test pins a property that, if it drifted, would let the old prose-matching
blindness back in:

  * `canonical()` collapses only the differences known to be meaningless in the
    sandbox and leaves a wrong PORT wrong (:9990 != :9999). Normalising the port
    would launder a real adapter typo into a perfect hit.
  * a zero-citation report scores 0.0, never 1.0. An unsourced essay must not
    read as maximally grounded.
  * `hallucinated_grounding` fires when a real page is cited but never fetched
    (answering from parametric memory).
  * a URL that was fetched immediately before being cited but was never searched
    or linked is still `guessed` (the fetch-then-fabricate attack).
  * `retrieval_utilization` never divides by zero.
  * no evidence log yields {"available": False}, never a text-match fallback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.fetch_log import (  # noqa: E402
    RunEvidence,
    canonical,
    classify_provenance,
    linked_urls,
    load_run_evidence,
    transport_metrics,
)

ALWAYS = lambda u: True  # noqa: E731  in_registry stub: every url "exists"
NEVER = lambda u: False  # noqa: E731


# --- canonical -------------------------------------------------------------

def test_canonical_strips_trailing_slash_and_punctuation():
    assert canonical("http://localhost:9999/a/") == "http://localhost:9999/a"
    assert canonical("http://localhost:8090/wiki/X.,") == "http://localhost:8090/wiki/X"


def test_canonical_unifies_loopback_spelling():
    assert canonical("http://127.0.0.1:9999/a") == canonical("http://localhost:9999/a")
    assert canonical("https://127.0.0.1:8090/x") == canonical("https://localhost:8090/x")


def test_canonical_keeps_wrong_port_wrong():
    # The whole point: :9990 was a real adapter defect. Collapsing it into :9999
    # would score the typo as a correct sandbox hit.
    assert canonical("http://localhost:9990/a") != canonical("http://localhost:9999/a")


def test_canonical_drops_dangling_close_paren_from_markdown():
    assert canonical("http://localhost:9999/a)") == "http://localhost:9999/a"
    # A balanced paren pair is content, not markdown punctuation, so it stays.
    assert canonical("http://localhost:9999/a(b)") == "http://localhost:9999/a(b)"


# --- zero-citation report --------------------------------------------------

def test_zero_citations_scores_zero_not_one():
    ev = RunEvidence(available=True)
    m = transport_metrics([], ev, in_registry=ALWAYS)
    assert m["available"] is True
    assert m["n_cited"] == 0
    for k in ("pof", "hallucinated_grounding", "fabrication", "retrieval_utilization"):
        assert m[k] == 0.0, f"{k} must be 0.0 for an unsourced report, got {m[k]}"


# --- hallucinated_grounding ------------------------------------------------

def test_hallucinated_grounding_counts_cited_real_but_unfetched():
    # Registry says the page exists, the report cites it, the shim never served
    # it: the agent answered from memory.
    ev = RunEvidence(available=True)  # nothing fetched
    m = transport_metrics(["http://localhost:9999/real"], ev, in_registry=ALWAYS)
    assert m["pof"] == 0.0
    assert m["hallucinated_grounding"] == 1.0
    assert m["fabrication"] == 0.0


def test_fetched_real_page_is_proven_not_hallucinated():
    ev = RunEvidence(available=True)
    url = canonical("http://localhost:9999/real")
    ev.fetched[url] = {"status": 200, "body_sha256": "abc"}
    m = transport_metrics([url], ev, in_registry=ALWAYS)
    assert m["pof"] == 1.0
    assert m["hallucinated_grounding"] == 0.0


def test_fabrication_counts_cited_urls_absent_from_registry():
    ev = RunEvidence(available=True)
    m = transport_metrics(["http://localhost:9999/ghost"], ev, in_registry=NEVER)
    assert m["fabrication"] == 1.0
    # A url that is not in the registry cannot also be "real but unfetched".
    assert m["hallucinated_grounding"] == 0.0


# --- url_provenance: fetch-then-fabricate ----------------------------------

def test_guessed_url_stays_guessed_even_after_fetch():
    # Fetch a url you never searched for and no read page linked, then cite it.
    # pof would read 1.0, but provenance must still say guessed: this is the
    # cheapest way to fake proof-of-fetch.
    ev = RunEvidence(available=True)
    url = canonical("http://localhost:9999/guessed")
    ev.fetched[url] = {"status": 200, "body_sha256": "abc"}
    prov = classify_provenance([url], ev)
    assert prov[url] == "guessed"


def test_searched_and_linked_provenance():
    ev = RunEvidence(available=True)
    searched = canonical("http://localhost:9999/from-search")
    linked = canonical("http://localhost:9999/from-page")
    ev.search_returned.add(searched)
    prov = classify_provenance([searched, linked], ev, linked={linked})
    assert prov[searched] == "searched"
    assert prov[linked] == "linked"


def test_provenance_counts_in_transport_metrics():
    ev = RunEvidence(available=True)
    s = canonical("http://localhost:9999/s")
    ev.search_returned.add(s)
    g = canonical("http://localhost:9999/g")
    m = transport_metrics([s, g], ev, in_registry=ALWAYS)
    assert m["provenance_counts"] == {"searched": 1, "linked": 0, "guessed": 1}


# --- retrieval_utilization -------------------------------------------------

def test_retrieval_utilization_denominator_is_search_returned():
    ev = RunEvidence(available=True)
    u1 = canonical("http://localhost:9999/a")
    u2 = canonical("http://localhost:9999/b")
    ev.search_returned.update({u1, u2})
    m = transport_metrics([u1], ev, in_registry=ALWAYS)
    # 1 of the 2 returned urls was cited.
    assert m["retrieval_utilization"] == 0.5


def test_retrieval_utilization_no_divide_by_zero():
    ev = RunEvidence(available=True)  # nothing returned by any search
    m = transport_metrics(["http://localhost:9999/a"], ev, in_registry=ALWAYS)
    assert m["retrieval_utilization"] == 0.0


# --- fail-closed: no log means no number -----------------------------------

def test_unavailable_returns_only_available_false():
    ev = RunEvidence()  # available defaults False
    m = transport_metrics(["http://localhost:9999/a"], ev, in_registry=ALWAYS)
    assert m["available"] is False
    # The invariant, not the dict shape: an unobserved run yields NO score,
    # never a zero. `reason` says which kind of unobserved it is.
    assert "pof" not in m and "hallucinated_grounding" not in m
    assert m.get("reason")
    # Crucially: no pof key to accidentally read as a real 0.0 or fall back on.
    assert "pof" not in m


def test_missing_log_file_is_unavailable(tmp_path):
    ev = load_run_evidence(tmp_path / "does_not_exist.jsonl")
    assert ev.available is False
    m = transport_metrics(["http://localhost:9999/a"], ev, in_registry=ALWAYS)
    assert m["available"] is False
    assert "pof" not in m
    assert m["reason"] == "no evidence log"


def _write_log(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.mark.parametrize("records, reason", [
    ([], "empty evidence log"),
    ([{"ts": 2.0, "run_id": "r", "kind": "mark", "phase": "end"}],
     "missing start"),
    ([{"ts": 1.0, "run_id": "r", "kind": "mark", "phase": "start"}],
     "missing end"),
])
def test_incomplete_brackets_are_unavailable(tmp_path, records, reason):
    log = tmp_path / "r.jsonl"
    if records:
        _write_log(log, records)
    else:
        log.write_text("")
    ev = load_run_evidence(log)
    assert ev.available is False
    assert reason in ev.unavailable_reason
    m = transport_metrics(["http://localhost:9999/a"], ev, in_registry=ALWAYS)
    assert m["available"] is False and "pof" not in m


def test_shim_restart_tail_is_unavailable_not_a_short_fetch_set(tmp_path):
    """A restart loses the process-local bracket, so the new shim cannot write
    this run's end mark and subsequent traffic lands unattributed after the last
    surviving record.  Missing the end is itself proof the log is incomplete;
    do not bound the damage by the truncated log's old t_end.
    """
    log = tmp_path / "r.jsonl"
    _write_log(log, [
        {"ts": 1.0, "run_id": "r", "worker": "w0", "kind": "mark", "phase": "start"},
        {"ts": 2.0, "run_id": "r", "worker": "w0", "kind": "fetch",
         "url": "http://localhost:9999/a", "status": 200},
    ])
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 3.0, "run_id": None, "worker": "w0", "kind": "fetch",
         "url": "http://localhost:9999/b", "status": 200},
    ])
    ev = load_run_evidence(log)
    assert ev.available is False
    assert "missing end" in ev.unavailable_reason


@pytest.mark.parametrize("statuses", [(200, 500), (500, 200)])
def test_fetch_ever_success_survives_retry_order(tmp_path, statuses):
    url = "http://localhost:9999/page"
    records = [
        {"ts": 1.0, "run_id": "r", "worker": "w0", "kind": "mark", "phase": "start"},
    ]
    for i, status in enumerate(statuses, 2):
        records.append({
            "ts": float(i), "run_id": "r", "worker": "w0", "kind": "fetch",
            "url": url, "status": status,
            "body_sha256": "success-blob" if status == 200 else "error-blob",
            "links": ["http://localhost:9999/from-success"] if status == 200
                     else ["http://localhost:9999/from-error"],
        })
    records.append({"ts": 9.0, "run_id": "r", "worker": "w0",
                    "kind": "mark", "phase": "end"})
    log = tmp_path / "r.jsonl"
    _write_log(log, records)

    ev = load_run_evidence(log)
    assert ev.available is True
    assert canonical(url) in ev.fetched_ok
    assert ev.blob_digest(url) == "success-blob"
    links = linked_urls(ev)
    assert canonical("http://localhost:9999/from-success") in links
    assert canonical("http://localhost:9999/from-error") not in links


def test_unattributed_records_are_worker_aware(tmp_path):
    log = tmp_path / "r.jsonl"
    _write_log(log, [
        {"ts": 1.0, "run_id": "r", "worker": "w0", "kind": "mark", "phase": "start"},
        {"ts": 4.0, "run_id": "r", "worker": "w0", "kind": "mark", "phase": "end"},
    ])
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 2.0, "run_id": None, "worker": "w1", "kind": "fetch"},
    ])
    ev = load_run_evidence(log)
    assert ev.available is True
    assert ev.unattributed_in_window == 0
    assert transport_metrics([], ev, in_registry=ALWAYS)["available"] is True


def test_unlabelled_unattributed_record_fails_closed_without_isolation(tmp_path):
    log = tmp_path / "r.jsonl"
    _write_log(log, [
        {"ts": 1.0, "run_id": "r", "kind": "mark", "phase": "start"},
        {"ts": 4.0, "run_id": "r", "kind": "mark", "phase": "end"},
    ])
    _write_log(tmp_path / "_unattributed.jsonl", [
        {"ts": 2.0, "run_id": None, "kind": "fetch"},
    ])
    ev = load_run_evidence(log)
    m = transport_metrics([], ev, in_registry=ALWAYS)
    assert m["available"] is False
    assert "isolation is ambiguous" in m["reason"]


# --- linked_urls uses served bytes -----------------------------------------

def test_linked_urls_reads_bodies_via_load_blob():
    ev = RunEvidence(available=True)
    ev.fetched[canonical("http://localhost:9999/page")] = {
        "status": 200,
        "body_sha256": "d1",
    }
    store = {"d1": b"see also http://localhost:9999/linked and http://localhost:9999/more"}
    out = linked_urls(ev, store.get)
    assert canonical("http://localhost:9999/linked") in out
    assert canonical("http://localhost:9999/more") in out


# --- linked_urls prefers the stamped `links` field (the /extract-strips-hrefs fix) -

def test_linked_urls_prefers_stored_links_over_blob():
    # /extract stores get_text() output, which has NO hrefs. The scorer must read
    # the `links` the shim captured before stripping, not regex the blob (which is
    # empty of URLs). Without this an on-page-link citation is false-accused as
    # hallucinated_grounding. Blob here is deliberately href-free stripped text.
    ev = RunEvidence(available=True)
    ev.fetched[canonical("http://localhost:8090/A/Sony")] = {
        "status": 200,
        "body_sha256": "d1",
        "links": [
            "http://localhost:8090/A/Walkman",
            "http://localhost:8090/A/Betamax",
        ],
    }
    store = {"d1": b"Sony is a company. It made the Walkman and Betamax."}
    out = linked_urls(ev, store.get)
    assert canonical("http://localhost:8090/A/Walkman") in out
    assert canonical("http://localhost:8090/A/Betamax") in out


def test_linked_urls_trusts_empty_stored_links_no_blob_fallback():
    # An explicit empty `links` means "parsed, nothing navigable" and must not
    # silently fall back to scraping absolute URLs out of the prose blob.
    ev = RunEvidence(available=True)
    ev.fetched[canonical("http://localhost:9999/page")] = {
        "status": 200, "body_sha256": "d1", "links": [],
    }
    store = {"d1": b"mentions http://localhost:9999/other in prose only"}
    assert linked_urls(ev, store.get) == set()


def test_linked_urls_works_without_load_blob():
    # The scorer can now resolve `linked` with no blob access at all, which is
    # what makes it independent of a SHIM_EVIDENCE_DIR/blob-dir mismatch.
    ev = RunEvidence(available=True)
    ev.fetched[canonical("http://localhost:7770/x.html")] = {
        "status": 200, "body_sha256": "d1", "links": ["http://localhost:7770/y.html"],
    }
    out = linked_urls(ev)
    assert canonical("http://localhost:7770/y.html") in out


# --- canonical agrees with the registry on decorative query params ----------

def test_canonical_strips_layered_nav_query_on_product_page():
    # A product cited with faceted params is the same source the shim searched.
    clean = canonical("http://localhost:7770/sony-wh1000.html")
    assert canonical("http://localhost:7770/sony-wh1000.html?p=2") == clean
    assert canonical("http://localhost:7770/sony-wh1000.html?product_list_order=price") == clean
    # Any query on a content .html page collapses to the clean page (the registry
    # keys identity on the url_key and ignores the query there).
    assert canonical("http://localhost:7770/sony-wh1000.html?utm_source=x") == clean


def test_canonical_keeps_non_layered_query_on_non_html_path():
    # A meaningful query on a non-content path must NOT be silently merged.
    u = canonical("http://localhost:9999/search?q_text=headphones")
    assert "q_text=headphones" in u


def test_layered_nav_params_match_registry():
    # Guard against the local copy drifting from the source of truth.
    from src.eval.url_registry import LAYERED_NAV_PARAMS
    from src.eval.fetch_log import _LAYERED_NAV_PARAMS
    assert _LAYERED_NAV_PARAMS == set(LAYERED_NAV_PARAMS)
