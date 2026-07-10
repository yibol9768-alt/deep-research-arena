"""Read the shim's transport-level evidence and derive grounding quantities.

Why this module exists
----------------------
`reach` answers "does this URL string exist". `proof_of_fetch`, as implemented
before 2026-07-08, answered "does the report's prose resemble a page the
EVALUATOR fetched after the fact". Neither observes the agent. A model that
guesses a URL that happens to exist and paraphrases a page it never opened is
indistinguishable from one that retrieved and read it. That is exactly the
behaviour the benchmark set out to detect.

With `logs/fetch/<run_id>.jsonl` (written by `integrations.search_shim.evidence`)
the following become decidable, per run:

    FETCHED          urls the shim actually served with status 200
    SEARCH_RETURNED  urls the shim handed back from a search call
    LINKED           urls appearing in the body of some fetched page
    CITED            urls appearing in the report (from the citation extractor)

Definitions
-----------
    pof                    |CITED n FETCHED| / |CITED|
    snippet_only           |(CITED n REGISTRY \\ FETCHED) n SEARCH_RETURNED| / |CITED|
    hallucinated_grounding |(CITED n REGISTRY \\ FETCHED) \\ SEARCH_RETURNED| / |CITED|
    fabrication            |CITED \\ REGISTRY| / |CITED|
    retrieval_utilization  |CITED n SEARCH_RETURNED| / |SEARCH_RETURNED|
    url_provenance         per cited url: searched | linked | guessed

`hallucinated_grounding` is the direct evidence of answering from parametric
memory: the page is real, the agent cited it, never opened it, and never even
searched for it. If a search DID return the URL with a snippet, the citation is
`snippet_only` instead: shallow, but not invented. Frameworks with no page-read
step (storm, langchain-odr) can only ever produce `snippet_only`, and charging
them with parametric recall would be a false accusation.
`guessed` provenance is the direct evidence of the fetch-then-fabricate attack
(fetch everything you intend to cite so `pof` reads 1.0): a guessed url was
never returned by a search and never linked from a page that was read.

Fail-closed
-----------
There is no fallback to text matching. A run with no evidence log yields
`available=False`, and the caller must refuse to report `pof` rather than
silently substituting the old prose-similarity number. Boards produced from
runs without an evidence log are not comparable to boards produced with one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

_URL_IN_BODY = re.compile(r"https?://[^\s\"'<>)\]]+")

# Faceted sort/limit/page params Magento layered navigation appends. The
# registry (src/eval/url_registry.LAYERED_NAV_PARAMS) treats these as
# non-identifying: a product page cited with `?p=2` or `?product_list_order=`
# is the SAME source. `canonical` must strip them or a real, opened page splits
# off `search_returned`/`fetched` and is charged hallucinated_grounding (or, on
# a non-layered query, fabrication). Kept in sync with url_registry by
# test_fetch_log_transport.test_layered_nav_params_match_registry rather than
# importing it, so this module's import graph stays free of the registry.
_LAYERED_NAV_PARAMS = {
    "product_list_limit", "product_list_order", "product_list_mode",
    "product_list_dir", "price", "cat", "p", "q",
}


def canonical(url: str) -> str:
    """Normalise a URL for set membership.

    Only the differences that are known to be meaningless in the sandbox are
    collapsed: trailing punctuation left by prose extraction, a trailing slash,
    and the `localhost` / `127.0.0.1` spelling of the same origin. Nothing else
    is rewritten. In particular a wrong PORT stays wrong: `:9990` is not
    `:9999`, because that was a real adapter defect and hiding it would make the
    instrument lie in the lane's favour.
    """
    u = (url or "").strip().rstrip(".,;:")
    if u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1]
    # A fragment is client-side and never a distinct server resource: a page
    # fetched (recorded without #anchor) but cited with #section is the SAME
    # page. Kiwix wiki citations frequently carry a section anchor, so leaving
    # the fragment in would drop those out of the fetched/searched buckets and
    # mislabel an opened page as `guessed`.
    hash_i = u.find("#")
    if hash_i != -1:
        u = u[:hash_i]
    # Query handling, kept in agreement with url_registry (see _LAYERED_NAV_PARAMS).
    # The registry ignores the query entirely on content pages (`/<key>.html`,
    # where identity is the url_key) and treats layered-nav params as decorative
    # everywhere. Mirroring that here keeps `search_returned`/`fetched` (clean
    # forms the shim served) matching a cite that carries `?p=2` etc., instead of
    # dropping the opened page into hallucinated_grounding. A non-layered query on
    # a non-.html path is preserved: it may distinguish a real nav/search path we
    # must not silently merge.
    q_i = u.find("?")
    if q_i != -1:
        base, query = u[:q_i], u[q_i + 1:]
        if base.rstrip("/").lower().endswith(".html"):
            u = base
        else:
            kept = [kv for kv in query.split("&")
                    if kv and kv.split("=", 1)[0].lower() not in _LAYERED_NAV_PARAMS]
            u = base if not kept else base + "?" + "&".join(kept)
    # The three sandbox origins speak http only, and the registry's own parser
    # keys on host+port and ignores the scheme. A model that writes
    # `https://localhost:8090/...` (LLMs do this constantly) therefore lands
    # `in_corpus=True` on the reach axis and, before this line, in a DIFFERENT
    # canonical bucket from the `http://` URL the shim actually served. The
    # result was `reach` high, `pof` 0, `hallucinated_grounding` 1.0: the
    # instrument told the agent it had cited from memory a page it had opened.
    # Reproduced 2026-07-09. Scheme is normalised here so the two axes cannot
    # disagree about the identity of a page.
    for host in ("localhost", "127.0.0.1"):
        if u.startswith(f"https://{host}"):
            u = "http://" + u[len("https://"):]
    u = u.replace("http://127.0.0.1:", "http://localhost:")
    # Host is case-insensitive (LOCALHOST == localhost); the PATH is not (Kiwix
    # article paths are case-sensitive), so only the scheme+authority is lowered.
    m = re.match(r"^(https?://[^/]+)(.*)$", u, re.I)
    if m:
        u = m.group(1).lower() + m.group(2)
    if u.endswith("/"):
        u = u[:-1]
    return u


@dataclass
class RunEvidence:
    """What one run's shim traffic proves."""

    run_id: Optional[str] = None
    lane: Optional[str] = None
    task: Optional[str] = None
    backbone: Optional[str] = None
    available: bool = False
    # Whether this lane's page reads went through the shim (declared by the
    # harness, stamped on the records). Defaults True: a log that never mentions
    # the field predates this feature or was written directly by the recorder
    # (canary, unit tests), and those must keep computing transport metrics.
    # Only an EXPLICIT false in the log flips this, which is exactly what the
    # harness writes for a lane that fetches off-shim (direct requests/aiohttp/
    # curl). When false, `transport_metrics` withholds pof instead of scoring it
    # 0, so a lane that really opened pages off-shim is never accused of
    # fabricating grounding. See FETCH_PATH_AUDIT_2026-07-08.md.
    fetch_observable: bool = True
    unavailable_reason: Optional[str] = None
    # Bracket window, and the count of records the recorder could not attribute
    # to any run inside it. Non-zero means this run silently lost evidence.
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    unattributed_in_window: int = 0
    unattributed_ambiguous: int = 0
    worker: Optional[str] = None

    searches: list[dict] = field(default_factory=list)
    # canonical url -> authoritative record.  Once a URL has returned 200 we
    # retain the most recent successful record even if a later retry fails.  A
    # page that was served once remains proof of fetch, and its successful
    # response is the only record whose blob/links may license provenance.
    fetched: dict[str, dict] = field(default_factory=dict)
    search_returned: set[str] = field(default_factory=set)
    blocked: list[dict] = field(default_factory=list)
    write_errors: int = 0

    @property
    def fetched_ok(self) -> set[str]:
        return {u for u, r in self.fetched.items() if int(r.get("status") or 0) == 200}

    def blob_digest(self, url: str) -> Optional[str]:
        rec = self.fetched.get(canonical(url))
        return rec.get("body_sha256") if rec else None


def load_run_evidence(path: str | Path) -> RunEvidence:
    p = Path(path)
    ev = RunEvidence()
    if not p.exists():
        ev.unavailable_reason = "no evidence log"
        return ev
    parsed_records = 0
    start_records: list[dict] = []
    end_records: list[dict] = []
    saw_end = False
    record_after_end = False
    inconsistent_run_id = False
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                ev.write_errors += 1
                continue
            if not isinstance(rec, dict):
                ev.write_errors += 1
                continue
            parsed_records += 1
            rec_run_id = rec.get("run_id")
            if ev.run_id and rec_run_id and rec_run_id != ev.run_id:
                inconsistent_run_id = True
            ev.run_id = ev.run_id or rec_run_id
            ev.lane = ev.lane or rec.get("lane")
            ev.task = ev.task or rec.get("task")
            ev.backbone = ev.backbone or rec.get("backbone")
            ev.worker = ev.worker or rec.get("worker")
            # Any line may carry the declaration; the recorder stamps it onto
            # every record from the same bracket, so they agree. Only an explicit
            # value overrides the observable-by-default; an absent field leaves
            # the backward-compatible True in place.
            fo = rec.get("fetch_observable")
            if fo is not None:
                ev.fetch_observable = bool(fo)
            kind = rec.get("kind")
            if kind == "mark":
                phase = rec.get("phase")
                if phase == "start":
                    start_records.append(rec)
                elif phase == "end":
                    end_records.append(rec)
                    saw_end = True
                else:
                    ev.write_errors += 1
                continue
            if saw_end and kind in ("search", "fetch", "block"):
                record_after_end = True
            if kind == "search":
                ev.searches.append(rec)
                for u in rec.get("urls_returned") or []:
                    ev.search_returned.add(canonical(u))
            elif kind == "fetch":
                key = canonical(rec.get("url", ""))
                if key:
                    prior = ev.fetched.get(key)
                    status = int(rec.get("status") or 0)
                    prior_ok = bool(prior and int(prior.get("status") or 0) == 200)
                    # A failed retry cannot erase an earlier successful serve.
                    # Conversely, a success after a failure replaces it and
                    # preserves the successful body digest and parsed links.
                    if status == 200 or not prior_ok:
                        ev.fetched[key] = rec
            elif kind == "block":
                ev.blocked.append(rec)
    if parsed_records == 0:
        ev.unavailable_reason = "empty evidence log"
        return ev
    if inconsistent_run_id:
        ev.unavailable_reason = "evidence log mixes multiple run_id values"
        return ev
    if len(start_records) != 1:
        ev.unavailable_reason = (
            "evidence log missing start mark" if not start_records
            else f"evidence log has {len(start_records)} start marks")
        return ev
    if len(end_records) != 1:
        ev.unavailable_reason = (
            "evidence log missing end mark (possible shim restart or killed run)"
            if not end_records else f"evidence log has {len(end_records)} end marks")
        return ev
    if record_after_end:
        ev.unavailable_reason = "evidence log has traffic after its end mark"
        return ev
    if end_records[0].get("orphaned"):
        ev.unavailable_reason = "evidence bracket was orphaned and reclaimed"
        return ev

    ev.t_start = start_records[0].get("ts")
    ev.t_end = end_records[0].get("ts")
    if not isinstance(ev.t_start, (int, float)):
        ev.unavailable_reason = "evidence start mark has no valid timestamp"
        return ev
    if not isinstance(ev.t_end, (int, float)):
        ev.unavailable_reason = "evidence end mark has no valid timestamp"
        return ev
    if ev.t_end < ev.t_start:
        ev.unavailable_reason = "evidence end mark precedes start mark"
        return ev

    (ev.unattributed_in_window,
     ev.unattributed_ambiguous) = _unattributed_in_window(
         p, ev.t_start, ev.t_end, ev.worker)
    ev.available = True
    return ev


def _unattributed_in_window(run_log: Path, t_start, t_end,
                            run_worker: Optional[str]) -> tuple[int, int]:
    """Records the recorder could not attribute to any run, inside this window.

    A record only reaches `_unattributed.jsonl` when it arrived with no open
    bracket: the shim restarted mid-run, a `/_mark` start was lost, an orphan
    bracket was reclaimed. Those records are gone from the run's own log, and
    what remains parses perfectly. So `write_errors` stays 0, the log looks
    healthy, `fetched` is short, and the lane is charged with citing pages it
    never opened. Damage and fabrication produce identical data again, one level
    down from the corrupted-line case this file already refuses to score.

    Multiple shim processes may share one evidence directory.  The 409 guard is
    process-local, not directory-wide, so timestamps alone cannot identify an
    orphan.  Match the worker stamped by the recorder.  If either side lacks a
    worker label, the deployment did not provide enough isolation to attribute
    the orphan safely and the caller fails closed via ``ambiguous``.
    """
    if t_start is None or t_end is None:
        return 0, 0
    p = run_log.parent / "_unattributed.jsonl"
    if not p.exists():
        return 0, 0
    n = 0
    ambiguous = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                # With neither timestamp nor worker this cannot be assigned to
                # one run.  Treat it as an isolation failure, not as evidence
                # against every sibling worker in the shared directory.
                ambiguous += 1
                continue
            if not isinstance(rec, dict):
                ambiguous += 1
                continue
            if rec.get("kind") not in ("fetch", "search"):
                continue
            ts = rec.get("ts")
            if not (isinstance(ts, (int, float)) and t_start <= ts <= t_end):
                continue
            orphan_worker = rec.get("worker")
            if run_worker and orphan_worker:
                if str(orphan_worker) == str(run_worker):
                    n += 1
                # A labelled sibling worker must not poison this run.
                continue
            ambiguous += 1
    return n, ambiguous


def linked_urls(ev: RunEvidence, load_blob=None) -> set[str]:
    """URLs discoverable from the pages the agent was actually served.

    A cited URL the agent never searched for but which appears on a page it did
    read is honest navigation, not a guess, so it must be subtracted from the
    hallucinated numerator.

    Primary source is the ``links`` field the shim now stamps on each fetch
    record: the absolute, urljoin-resolved hrefs it parsed from the served HTML
    at fetch time. This is authoritative and blob-independent. It exists because
    the /extract chokepoint stores ``get_text()`` output (hrefs already gone) and
    /fetch pages carry RELATIVE Kiwix/Postmill links; a regex over either blob
    misses them, and the missed link becomes a false ``hallucinated_grounding``.

    ``load_blob`` is the back-compat path for logs written before ``links`` was
    captured: it regexes ABSOLUTE http(s) URLs out of the stored bytes. It is
    only consulted for records that carry no ``links`` field. Relative hrefs are
    unrecoverable from the old stripped-text blobs, which is precisely the defect
    the stored ``links`` field fixes.
    """
    out: set[str] = set()
    for rec in ev.fetched.values():
        stored = rec.get("links")
        if stored is not None:
            # Parsed at fetch time (may be empty: a page with no navigable
            # links). Trust it and do not fall back to the blob regex.
            for u in stored:
                cu = canonical(u)
                if cu:
                    out.add(cu)
            continue
        if load_blob is None:
            continue
        digest = rec.get("body_sha256")
        if not digest:
            continue
        body = load_blob(digest)
        if not body:
            continue
        try:
            text = body.decode("utf-8", "replace")
        except Exception:
            continue
        for u in _URL_IN_BODY.findall(text):
            out.add(canonical(u))
    return out


def classify_provenance(cited: Iterable[str], ev: RunEvidence,
                        linked: Optional[set[str]] = None,
                        identify=None) -> dict[str, str]:
    """searched | linked | guessed, per cited URL.

    `guessed` means the agent produced a URL that no search returned and no page
    it read contained. Whether it later fetched that URL is irrelevant to the
    classification, which is the point: fetching a guessed URL right before
    citing it is the cheapest way to fake `pof`.

    `identify` maps a URL to the page it names. Without it, set membership uses
    `canonical`, which is a weaker identity than the one `reach` uses: the
    registry knows `/wiki/Bluetooth` and `/content/<book>/A/Bluetooth` are one
    page, and that a forum thread's identity is its id. The shim serves one
    spelling and models cite the other, so a page the agent really opened landed
    outside FETCHED and was charged as parametric recall.
    """
    ident = identify or (lambda u: u)
    linked = {ident(u) for u in (linked or set())}
    searched = {ident(u) for u in ev.search_returned}
    out: dict[str, str] = {}
    for raw in cited:
        u = ident(canonical(raw))
        if u in searched:
            out[u] = "searched"
        elif u in linked:
            out[u] = "linked"
        else:
            out[u] = "guessed"
    return out


def transport_metrics(cited: Iterable[str], ev: RunEvidence, *,
                      in_registry, linked: Optional[set[str]] = None,
                      identify=None, is_nav=None) -> dict:
    """The transport-level grounding block for one report.

    `in_registry(url) -> bool` decides existence in the frozen corpus; it stays
    the caller's business so this module never touches the registry or network.
    `identify(url) -> str` collapses the spellings of one page, and must be the
    SAME identity `reach` uses, or the two axes disagree about what a page is and
    a lane is accused of recalling from memory a page it opened.
    """
    if not ev.available:
        return {"available": False, "reason": getattr(ev, "unavailable_reason", None)
                or "no evidence log"}

    if ev.write_errors:
        # A line that would not parse means the log lost records: a kill during
        # flush, a full disk, a half-written blob. The missing record is almost
        # always a `fetch`, so the run reads as an agent that cited pages it
        # never opened. Instrument damage and fabrication produce identical data,
        # which is this project's recurring failure. A damaged log is unscorable.
        return {"available": False,
                "reason": f"evidence log damaged: {ev.write_errors} unparseable record(s)"}

    if ev.unattributed_in_window:
        # The log parses cleanly and is still incomplete: these records arrived
        # with no open bracket and went to `_unattributed.jsonl`. Scoring what
        # survived would read a short FETCHED set as fabrication.
        return {"available": False,
                "reason": f"evidence log incomplete: {ev.unattributed_in_window} "
                          "record(s) landed unattributed inside this run's window"}

    if ev.unattributed_ambiguous:
        return {"available": False,
                "reason": f"evidence isolation is ambiguous: "
                          f"{ev.unattributed_ambiguous} unattributed record(s) "
                          "could not be assigned to a worker"}

    # The run was bracketed and logged, but this lane's page reads bypass the
    # shim (declared fetch_observable=false). FETCHED would be empty for a reason
    # that has nothing to do with what the agent did, so pof would read 0 and
    # accuse a lane that may well have opened every page it cites, just off-shim.
    # Withhold the transport block entirely rather than emit a false 0. The
    # caller then falls back to text_v1 or, under require_transport_pof, raises;
    # either way it never records pof=0 here. See FETCH_PATH_AUDIT_2026-07-08.md.
    if not ev.fetch_observable:
        return {"available": False, "reason": "fetch_not_observable"}

    ident = identify or (lambda u: u)
    # A search/nav URL (`catalogsearch/result/?q=`, a forum listing) is a real,
    # reachable page that carries no claim. `score_reachability` skips it: "not
    # evidence, but neither fabrication". This function counted it in the `pof`
    # denominator AND in the fabricated set, so citing one real navigation page
    # cut `pof`, raised `fabrication` above `1 - reach`, and broke both
    # invariants this module states. The two grounding axes must exclude the same
    # URLs, or they are not measuring the same report.
    nav = is_nav or (lambda u: False)
    cited_set = {ident(canonical(u)) for u in cited
                 if canonical(u) and not nav(u)}
    n = len(cited_set)
    fetched = {ident(u) for u in ev.fetched_ok}
    searched = {ident(u) for u in ev.search_returned}
    prov = classify_provenance(cited_set, ev, linked=linked, identify=ident)

    if n == 0:
        # No citations at all: reach's denominator is zero elsewhere, and there
        # is nothing to prove fetched. Report zeros, not 1.0. An unsourced essay
        # must never look maximally grounded.
        return {
            "available": True,
            "n_cited": 0,
            "pof": 0.0,
            "provenance": 0.0,
            "snippet_only": 0.0,
            "hallucinated_grounding": 0.0,
            "fabrication": 0.0,
            "retrieval_utilization": 0.0,
            "n_fetched": len(fetched),
            "n_search_returned": len(ev.search_returned),
            "n_searches": len(ev.searches),
            "url_provenance": {},
            "provenance_counts": {"searched": 0, "linked": 0, "guessed": 0},
        }

    real = {u for u in cited_set if in_registry(u)}
    cited_and_fetched = cited_set & fetched
    fabricated = cited_set - real

    # A real page, cited, not opened, splits into two very different failures.
    #
    #   snippet_only  the search endpoint handed the agent this URL together
    #                 with a snippet. It cited the page on the strength of the
    #                 snippet. Some frameworks (storm, langchain-odr) have no
    #                 page-read step at all and can only ever do this.
    #
    #   hallucinated  the agent never searched for it and never read it, yet
    #                 cited it, and the page happens to exist. There is nowhere
    #                 the URL or its content could have come from except the
    #                 model's parameters.
    #
    # Collapsing them, as an earlier version of this module did, charges a
    # fetch-less framework with answering from memory. It did not: we handed it
    # a snippet. Only the second class is evidence of parametric recall.
    # `linked` (URLs the agent could have found by following a link on a page it
    # actually read) is honest navigation, not a guess. Charging a real page
    # reached via an on-page link as parametric recall would be a false
    # accusation, so it is subtracted from the hallucinated numerator here just
    # as it is excluded from `guessed` in classify_provenance.
    linked = {ident(u) for u in (linked or set())}
    unopened_real = real - fetched
    snippet_only = unopened_real & searched
    hallucinated = unopened_real - searched - linked

    denom_ret = len(searched)
    counts = {"searched": 0, "linked": 0, "guessed": 0}
    for v in prov.values():
        counts[v] = counts.get(v, 0) + 1

    # The gate question, made decidable.
    #
    # `reach` asks "does this URL exist in the frozen corpus". A model that
    # never searched, and wrote `localhost:8090/content/.../Coffee` from its
    # memory of the real Wikipedia, satisfies it. Measured on the 13-task
    # subset: HALF of every in-corpus citation points at the wiki, whose article
    # names are real and therefore guessable, while the store and forum slugs
    # are synthetic and are not. So the existence gate rewards precisely the
    # behaviour the benchmark exists to catch.
    #
    # `provenance` asks the question the closed world actually licenses: could
    # this agent have learned this URL from anything we handed it? A citation
    # counts when the URL was returned by a search, or served as a page, or
    # appeared in the body of a page it read. Everything else is either
    # fabricated (not in the corpus) or recalled (in the corpus, never served).
    #
    # provenance == reach - hallucinated_grounding, by construction. It is
    # reported as a diagnostic; whether it should replace `reach` as the gate in
    # `truth` is a methodology decision, not this module's to make.
    # `served` is everything this run could have learned a URL from. But a page
    # in the corpus may link OFF the corpus (a wiki article citing the real web).
    # Counting such a citation as `provenance` while `fabrication` also counts it
    # made both read 1.0 at once, and broke the stated invariant
    # `provenance == reach - hallucinated_grounding`. In a closed world a
    # citation is only licensed when the URL was served AND exists in the frozen
    # corpus, so the numerator intersects the registry too.
    # `searched`, not `ev.search_returned`: every other set here is mapped through
    # `identify`, and mixing the raw form back in silently excludes any page whose
    # registry canonical differs from the spelling the shim served -- that is every
    # wiki article and every forum thread. A fetch-less framework citing three wiki
    # pages it got from search read `provenance = 0` while the same call reported
    # `url_provenance = "searched"` for all three, and the stated invariant
    # `provenance == reach - hallucinated_grounding` was false. Product pages were
    # spared (served form == registry canonical), so the axis also treated sources
    # unequally. Introduced by the `identify` fix itself.
    served = searched | fetched | (linked or set())
    provenance = len(cited_set & served & real) / n

    return {
        "available": True,
        "n_cited": n,
        "pof": len(cited_and_fetched) / n,
        "provenance": provenance,
        "snippet_only": len(snippet_only) / n,
        "hallucinated_grounding": len(hallucinated) / n,
        "fabrication": len(fabricated) / n,
        "retrieval_utilization": (len(cited_set & searched) / denom_ret) if denom_ret else 0.0,
        "n_fetched": len(fetched),
        "n_search_returned": denom_ret,
        "n_searches": len(ev.searches),
        "url_provenance": prov,
        "provenance_counts": counts,
    }
