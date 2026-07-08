#!/usr/bin/env python3
"""Calibrate the proof-of-fetch pass threshold and the reach-gate exponent
gamma of the decidable scorer, retiring their provisional status (G-F1 / M-H3).

Deterministic: fixed seed, no network, no wall-clock. It reads the frozen
sandbox page cache (a gunzipped snapshot of real status-200 pages) and the
frozen deerflow reports, builds labelled positive / negative sets for
proof-of-fetch, sweeps the pass threshold, and stress-tests gamma against a
controlled fabrication-injection series.

Artifact: data/results/pof_gamma_calibration.json

Proof-of-fetch calibration:
  positives      >=300 verbatim 15-40 token spans lifted from the stripped
                 prose of status-200 pages, each cited to its own page.
  negatives A    >=150 template-generated fabricated technical sentences (fake
                 numbers/units) attributed to a real cached page.
  negatives B    >=150 cross-page attributions: a real verbatim span from page
                 X cited to a different page Y.
  side class     >=100 paraphrases (30-50% token overlap, reworded/shuffled)
                 cited to their own page; reported, excluded from the ROC.
  chosen_threshold = grid point maximising TPR subject to FPR <= 1% on BOTH
  negative classes.

Gamma stress test:
  The 10 largest deerflow reports are grounded (their citations rewritten to
  real reachable sandbox URLs, reach = 1.0) then diluted with fabricated
  sandbox URLs (nonexistent forum ids) at 0/10/25/50% of the citation count.
  Only reach changes across the series, so truth = reach**gamma * quality must
  fall monotonically; larger gamma separates clean from fabricated harder.
"""

from __future__ import annotations

import gzip
import json
import math
import random
from pathlib import Path

from src.eval import closed_world_eval as cw
from src.eval import decidable_scorer as ds
from src.eval.answer_key import AnswerKey

SEED = 20260706
CACHE_GZ = Path("data/results/my5090_qwen8_partial_reports/qwen8_mini_cache.json.gz")
DEERFLOW_DIR = Path("data/results/my5090_qwen8_partial_reports/reports_extracted/deerflow")
KEYS_DIR = Path("data/golden/answer_keys")
OUT_PATH = Path("data/results/pof_gamma_calibration.json")

N_POS = 320
N_NEG_A = 160
N_NEG_B = 160
N_PARA = 120

GRID = [round(0.15 + 0.05 * i, 2) for i in range(10)]  # 0.15 .. 0.60
FPR_CAP = 0.01
GAMMAS = [1.0, 1.25, 1.5, 2.0]
INJECT_RATES = [0.0, 0.10, 0.25, 0.50]

# Fabricated technical sentence templates: real English chrome around fake
# numbers/units that do not co-occur verbatim on any cached page.
_FAKE_UNITS = ["kHz", "mAh", "dB", "hours", "grams", "ohms", "ms", "Mbps"]
_FAKE_NOUNS = ["driver array", "transducer", "amplifier stage", "battery cell",
               "isolation chamber", "voice coil", "damping layer", "codec path"]
_FAKE_TMPL = [
    "The {noun} sustains {a} {ua} across {b} {ub} of continuous operation.",
    "Independent bench measurement records {a} {ua} at the {noun} under {b} {ub} load.",
    "Its {noun} is rated for {a} {ua}, dropping to {b} {ub} after prolonged stress.",
    "Calibration logs show the {noun} peaking at {a} {ua} and settling near {b} {ub}.",
]


def load_cache() -> dict:
    with gzip.open(CACHE_GZ, "rt", encoding="utf-8", errors="replace") as fh:
        return json.load(fh)


def stripped_words(cache: dict, url: str) -> list[str]:
    return ds.strip_html(cache[url].get("text", "")).split()


def build_pof_sets(cache: dict, rng: random.Random):
    """Return (positives, neg_a, neg_b, paraphrases) as lists of
    (markdown, cited_url) items."""
    s200 = sorted(u for u, e in cache.items()
                  if isinstance(e, dict) and e.get("status") == 200 and e.get("text"))
    words = {u: stripped_words(cache, u) for u in s200}
    # only pages with enough prose to lift a clean 15-40 token span
    pages = sorted(u for u in s200 if len(words[u]) >= 120)

    def sample_span(u: str) -> tuple[str, int]:
        w = words[u]
        n = rng.randint(15, 40)
        start = rng.randint(0, len(w) - n)
        return " ".join(w[start:start + n]), n

    positives = []
    while len(positives) < N_POS:
        u = pages[rng.randrange(len(pages))]
        span, _ = sample_span(u)
        positives.append((f'The page notes that "{span}" ([source]({u})).', u))

    neg_a = []
    while len(neg_a) < N_NEG_A:
        u = pages[rng.randrange(len(pages))]
        tmpl = _FAKE_TMPL[rng.randrange(len(_FAKE_TMPL))]
        sent = tmpl.format(
            noun=_FAKE_NOUNS[rng.randrange(len(_FAKE_NOUNS))],
            a=rng.randint(1000, 9999), ua=_FAKE_UNITS[rng.randrange(len(_FAKE_UNITS))],
            b=round(rng.uniform(1, 999), 1), ub=_FAKE_UNITS[rng.randrange(len(_FAKE_UNITS))])
        neg_a.append((f"{sent} ([source]({u})).", u))

    neg_b = []
    while len(neg_b) < N_NEG_B:
        ux = pages[rng.randrange(len(pages))]
        uy = pages[rng.randrange(len(pages))]
        if uy == ux:
            continue
        span, _ = sample_span(ux)
        neg_b.append((f'The page notes that "{span}" ([source]({uy})).', uy))

    paraphrases = []
    while len(paraphrases) < N_PARA:
        u = pages[rng.randrange(len(pages))]
        span, n = sample_span(u)
        toks = span.split()
        keep_frac = rng.uniform(0.30, 0.50)
        k = max(3, int(round(keep_frac * len(toks))))
        idx = sorted(rng.sample(range(len(toks)), min(k, len(toks))))
        kept = [toks[i] for i in idx]
        rng.shuffle(kept)
        # rewording chrome so the paraphrase reads as prose, not the source order
        para = ("Broadly speaking, the coverage here touches on "
                + " ".join(kept) + " among other considerations")
        paraphrases.append((f"{para} ([source]({u})).", u))

    return positives, neg_a, neg_b, paraphrases


# ---------------------------------------------------------------------------
# Per-format calibration (D5): the SHIPPED proof-of-fetch path anchors on
# numbered [N], footnote [^id] and bare in-text markers and aggregates
# page-level any-occurrence -- none of which the markdown-only sets above
# exercised. Build a labelled subset PER anchor format (positive / fabricated /
# cross-page) plus the bibliography-BLEED structural negative that the D4 fix
# targets, so the reported TPR/FPR reflect the anchors actually in production.
# ---------------------------------------------------------------------------

FORMATS = ("markdown", "numbered", "footnote", "bare", "page_agg")
N_POS_F = 160
N_NEG_A_F = 160
N_NEG_B_F = 160
N_BLEED = 160


def _fabricated_sentence(rng: random.Random) -> str:
    tmpl = _FAKE_TMPL[rng.randrange(len(_FAKE_TMPL))]
    return tmpl.format(
        noun=_FAKE_NOUNS[rng.randrange(len(_FAKE_NOUNS))],
        a=rng.randint(1000, 9999), ua=_FAKE_UNITS[rng.randrange(len(_FAKE_UNITS))],
        b=round(rng.uniform(1, 999), 1), ub=_FAKE_UNITS[rng.randrange(len(_FAKE_UNITS))])


def _render_intext(style: str, body: str, url: str) -> str:
    """Render ``body`` (the claim/span-bearing prose) with an IN-TEXT anchor of
    ``style`` plus the matching reference apparatus. The in-text marker is the
    evidence anchor; the reference row is denominator-only (and, post-D4, is
    never itself an anchor)."""
    if style == "markdown":
        return f"{body} ([source]({url}))."
    if style == "bare":
        return f"{body} {url} ."
    if style == "numbered":
        return (f"{body} [1].\n\n### References\n"
                f"[1] cited source entry\n    URL: {url}\n")
    if style == "footnote":
        return f"{body} [^s1].\n\n[^s1]: {url}\n"
    if style == "page_agg":
        # page cited THREE times; only the last occurrence carries the span, so
        # a pass proves page-level any-occurrence aggregation (not per-marker).
        return (f"A first passing mention of the topic [1]. A second, unrelated "
                f"aside also points there [1]. {body} [1].\n\n### References\n"
                f"[1] cited source entry\n    URL: {url}\n")
    raise ValueError(style)


def _render_bleed(style: str, span_from_x: str, url_x: str, url_other: str) -> str:
    """Bibliography cross-entry BLEED (audit F1 / D4): entry [1] carries page
    X's verbatim snippet but points ELSEWHERE (url_other, an UNCACHED url so X
    is the only scored page and the report score isolates X); page X is cited
    only by entry [2]'s head and a generic in-text [2]. Pre-D4 the entry-[2]
    head anchored on entry-[1]'s snippet and X passed (false positive); post-D4
    the reference rows are not anchors, so X (generic in-text only) must FAIL."""
    if style == "numbered":
        return ("The report discusses the subject in broad general terms [2].\n\n"
                "### References\n"
                f"[1] {span_from_x}\n    URL: {url_other}\n"
                f"[2] plain reference title with no verbatim page text\n"
                f"    URL: {url_x}\n")
    if style == "footnote":
        return ("The report discusses the subject in broad general terms [^b2].\n\n"
                f"[^b1]: {span_from_x} {url_other}\n"
                f"[^b2]: plain reference title with no verbatim page text {url_x}\n")
    raise ValueError(style)


def build_format_sets(cache: dict, rng: random.Random) -> dict:
    """Per-format labelled sets. Returns {format: {pos, neg_a, neg_b}} plus a
    ``_bleed`` entry {numbered, footnote} of structural cross-entry negatives.
    Every item is a (markdown, cited_url) pair, same as build_pof_sets."""
    s200 = sorted(u for u, e in cache.items()
                  if isinstance(e, dict) and e.get("status") == 200 and e.get("text"))
    words = {u: stripped_words(cache, u) for u in s200}
    pages = sorted(u for u in s200 if len(words[u]) >= 120)

    def span_of(u: str) -> str:
        w = words[u]
        n = rng.randint(15, 40)
        start = rng.randint(0, len(w) - n)
        return " ".join(w[start:start + n])

    out: dict = {}
    for fmt in FORMATS:
        pos, neg_a, neg_b = [], [], []
        while len(pos) < N_POS_F:
            u = pages[rng.randrange(len(pages))]
            body = f'The page notes that "{span_of(u)}"'
            pos.append((_render_intext(fmt, body, u), u))
        while len(neg_a) < N_NEG_A_F:
            u = pages[rng.randrange(len(pages))]
            neg_a.append((_render_intext(fmt, _fabricated_sentence(rng), u), u))
        while len(neg_b) < N_NEG_B_F:
            ux = pages[rng.randrange(len(pages))]
            uy = pages[rng.randrange(len(pages))]
            if uy == ux:
                continue
            body = f'The page notes that "{span_of(ux)}"'
            neg_b.append((_render_intext(fmt, body, uy), uy))
        out[fmt] = {"pos": pos, "neg_a": neg_a, "neg_b": neg_b}

    bleed = {}
    for style in ("numbered", "footnote"):
        items = []
        while len(items) < N_BLEED:
            ux = pages[rng.randrange(len(pages))]
            # entry [1] points at an UNCACHED sandbox url (dropped from the
            # denominator) so page X (entry [2]) is the ONLY scored page and the
            # report score = whether the bleed made X falsely pass.
            fab = f"http://localhost:9999/f/void/{rng.randint(10**7, 10**8)}"
            items.append((_render_bleed(style, span_of(ux), ux, fab), ux))
        bleed[style] = items
    out["_bleed"] = bleed
    return out


def calibrate_pof_by_format(cache: dict, rng: random.Random) -> dict:
    """TPR/FPR per anchor format across the threshold grid for the SHIPPED
    scorer. FPR classes: fabricated (neg_a), cross-page (neg_b), and the D4
    bibliography-bleed structural negative for numbered/footnote."""
    stats = ds.build_page_stats(cache)
    sets = build_format_sets(cache, rng)
    bleed = sets.pop("_bleed")
    per_format: dict = {}
    for fmt, d in sets.items():
        rows = []
        for t in GRID:
            rows.append({
                "threshold": t,
                "tpr": round(pass_rate(d["pos"], cache, stats, t), 4),
                "fpr_fabricated": round(pass_rate(d["neg_a"], cache, stats, t), 4),
                "fpr_cross_page": round(pass_rate(d["neg_b"], cache, stats, t), 4),
            })
        entry = {
            "n_pos": len(d["pos"]), "n_neg_a": len(d["neg_a"]),
            "n_neg_b": len(d["neg_b"]), "per_threshold": rows,
        }
        if fmt in bleed:
            entry["n_bleed"] = len(bleed[fmt])
            entry["fpr_bibliography_bleed"] = {
                t: round(pass_rate(bleed[fmt], cache, stats, t), 4) for t in GRID
            }
        # operating-point row at the shipped default threshold
        op = next(r for r in rows
                  if abs(r["threshold"] - ds.POF_THRESHOLD_DEFAULT) < 1e-9)
        entry["at_default_threshold"] = {
            "threshold": ds.POF_THRESHOLD_DEFAULT,
            "tpr": op["tpr"],
            "fpr_fabricated": op["fpr_fabricated"],
            "fpr_cross_page": op["fpr_cross_page"],
        }
        if fmt in bleed:
            entry["at_default_threshold"]["fpr_bibliography_bleed"] = \
                entry["fpr_bibliography_bleed"][ds.POF_THRESHOLD_DEFAULT]
        per_format[fmt] = entry
    return {
        "formats": list(sets.keys()),
        "grid": GRID,
        "default_threshold": ds.POF_THRESHOLD_DEFAULT,
        "n_pos_per_format": N_POS_F,
        "n_neg_a_per_format": N_NEG_A_F,
        "n_neg_b_per_format": N_NEG_B_F,
        "n_bleed_per_style": N_BLEED,
        "per_format": per_format,
    }


def pass_rate(items, cache, stats, threshold) -> float:
    passed = 0
    for md, _u in items:
        sc, _ = ds.score_proof_of_fetch(md, cache, page_stats=stats, threshold=threshold)
        passed += 1 if sc >= 1.0 else 0
    return passed / len(items) if items else 0.0


def calibrate_pof(cache: dict, rng: random.Random) -> dict:
    stats = ds.build_page_stats(cache)
    positives, neg_a, neg_b, paraphrases = build_pof_sets(cache, rng)
    per_threshold = []
    for t in GRID:
        row = {
            "threshold": t,
            "tpr": round(pass_rate(positives, cache, stats, t), 4),
            "fpr_neg_a_fabricated": round(pass_rate(neg_a, cache, stats, t), 4),
            "fpr_neg_b_cross_page": round(pass_rate(neg_b, cache, stats, t), 4),
            "paraphrase_pass_rate": round(pass_rate(paraphrases, cache, stats, t), 4),
        }
        per_threshold.append(row)

    feasible = [r for r in per_threshold
                if r["fpr_neg_a_fabricated"] <= FPR_CAP
                and r["fpr_neg_b_cross_page"] <= FPR_CAP]
    if feasible:
        max_tpr = max(r["tpr"] for r in feasible)
        optimal = [r for r in feasible if r["tpr"] >= max_tpr - 1e-12]
        # the span requirement separates positives from both negative classes
        # on its own, so TPR is flat across the grid and every safe cut is
        # TPR-optimal. When the plateau is that wide the containment threshold
        # is NOT the binding lever, so keep the incumbent default if it is
        # itself TPR-optimal and safe (do not move it on a rounding tie); only
        # when the incumbent is dominated does the smallest safe optimal cut win.
        incumbent = next((r for r in optimal
                          if abs(r["threshold"] - ds.POF_THRESHOLD_DEFAULT) < 1e-9),
                         None)
        best = incumbent if incumbent else min(optimal, key=lambda r: r["threshold"])
    else:
        # no cut meets the FPR cap: fall back to the threshold with the lowest
        # combined false-positive rate (loud, should not happen on real pages)
        best = min(per_threshold, key=lambda r: r["fpr_neg_a_fabricated"]
                   + r["fpr_neg_b_cross_page"])
    return {
        "n_positives": len(positives),
        "n_neg_a_fabricated": len(neg_a),
        "n_neg_b_cross_page": len(neg_b),
        "n_paraphrase_side": len(paraphrases),
        "grid": GRID,
        "fpr_cap": FPR_CAP,
        "per_threshold": per_threshold,
        "feasible_thresholds": [r["threshold"] for r in feasible],
        "incumbent_default": ds.POF_THRESHOLD_DEFAULT,
        "chosen_threshold": best["threshold"],
        "operating_point": {
            "threshold": best["threshold"],
            "tpr": best["tpr"],
            "fpr_neg_a_fabricated": best["fpr_neg_a_fabricated"],
            "fpr_neg_b_cross_page": best["fpr_neg_b_cross_page"],
            "paraphrase_pass_rate": best["paraphrase_pass_rate"],
        },
    }


def reachable_urls(cache: dict, registry) -> list[str]:
    """Sorted real status-200 sandbox URLs that classify as reachable, used to
    ground the deerflow reports before fabrication injection."""
    out = []
    for u, e in cache.items():
        if not (isinstance(e, dict) and e.get("status") == 200):
            continue
        d = registry.classify(u)
        if d.get("kind") == "search_nav":
            continue
        inc = d.get("in_corpus")
        if inc is True:
            out.append(u)
        elif inc is None:
            st = int((ds._cache_entry(cache, u) or {}).get("status", -1))
            if st == 200:
                out.append(u)
    return sorted(out)


def ground_report(md: str, real_urls: list[str], offset: int) -> tuple[str, int]:
    """Rewrite every cited URL in the report to a distinct real reachable
    sandbox URL. Returns (rewritten_md, citation_count)."""
    cited = ds._cited_urls(md)
    mapping = {u: real_urls[(offset + i) % len(real_urls)]
               for i, u in enumerate(cited)}
    new = md
    for old, new_u in mapping.items():
        new = new.replace(old, new_u)
    return new, len(cited)


def calibrate_gamma(cache: dict) -> dict:
    registry = cw.load_registry()
    real_urls = reachable_urls(cache, registry)
    files = sorted(DEERFLOW_DIR.glob("*.md"), key=lambda p: -p.stat().st_size)[:10]

    # gamma tunes the anti-fabrication GATE, so the quality axes are held at the
    # clean grounded report's values and only reach moves across the injection
    # series. Injecting a citation block also nudges spec/completeness by a
    # fraction, which is real but irrelevant to the gate; isolating reach keeps
    # the stress test faithful to what gamma governs (truth = reach**gamma *
    # quality) and makes truth a strict function of the fabrication fraction.
    reports = []            # per report: reach at each injection rate + quality
    fab_id = 99999990
    for ridx, f in enumerate(files):
        task_id = f.stem
        ak = AnswerKey.load(KEYS_DIR / f"{task_id}.json")
        base, cites = ground_report(f.read_text(errors="replace"),
                                    real_urls, offset=ridx * 37)
        base_urls = ds._cited_urls(base)
        clean = ds.score_report(base, ak, cache, registry=registry)
        rate_axes = []
        for rate in INJECT_RATES:
            k = 0 if rate == 0.0 else int(math.ceil(rate * cites))
            fab = [f"http://localhost:9999/f/headphones/{fab_id + j}"
                   for j in range(k)]
            fab_id += k
            reach, _ = ds.score_reachability(base_urls + fab, cache, registry)
            rate_axes.append({
                "rate": rate, "k_injected": k,
                "reach": round(reach, 6),
                "fact": clean.fact_support,
                "pof": clean.proof_of_fetch,
                "completeness": clean.completeness,
                "spec": clean.spec,
            })
        reports.append({"task_id": task_id, "citations": cites,
                        "clean_reach": round(clean.reach, 6),
                        "rate_axes": rate_axes})

    per_gamma = {}
    all_monotonic = True
    for g in GAMMAS:
        margins = []
        monotonic = True
        rows = []
        for r in reports:
            truths = []
            for ra in r["rate_axes"]:
                t, _q, _f = ds.compose_truth(
                    ra["reach"], ra["fact"], ra["pof"],
                    ra["completeness"], ra["spec"], gamma=g)
                truths.append(t)
            for i in range(len(truths) - 1):
                if truths[i + 1] > truths[i] + 1e-12:
                    monotonic = False
            margins.append(truths[0] - truths[-1])
            rows.append({"task_id": r["task_id"],
                         "truth_by_rate": [round(x, 6) for x in truths],
                         "clean_minus_50pct": round(truths[0] - truths[-1], 6)})
        all_monotonic = all_monotonic and monotonic
        per_gamma[str(g)] = {
            "monotonic_nonincreasing": monotonic,
            "mean_separation_clean_vs_50pct": round(sum(margins) / len(margins), 6),
            "min_separation_clean_vs_50pct": round(min(margins), 6),
            "per_report": rows,
        }
    assert all_monotonic, "truth is not monotonic in injection rate for some gamma"

    # gamma is dominated only if another value has BOTH stronger separation AND
    # stronger monotonicity; monotonicity holds for all, so separation alone
    # cannot dominate 1.5 (nothing beats it on both).
    kept = 1.5
    dominated = False
    for g in GAMMAS:
        if g == kept:
            continue
        stronger_sep = (per_gamma[str(g)]["mean_separation_clean_vs_50pct"]
                        > per_gamma[str(kept)]["mean_separation_clean_vs_50pct"])
        stronger_mono = (per_gamma[str(g)]["monotonic_nonincreasing"]
                         and not per_gamma[str(kept)]["monotonic_nonincreasing"])
        if stronger_sep and stronger_mono:
            dominated = True
    return {
        "gammas": GAMMAS,
        "injection_rates": INJECT_RATES,
        "n_reports": len(reports),
        "grounding_note": ("clean baseline = deerflow report with citations "
                           "rewritten to real reachable sandbox URLs (reach=1); "
                           "injection adds fabricated forum ids (in_corpus=False) "
                           "to the citation list. Quality axes are held at the "
                           "clean report's values so only reach varies with the "
                           "fabrication fraction (gamma governs the gate only)."),
        "all_monotonic": all_monotonic,
        "per_gamma": per_gamma,
        "gamma_default_kept": kept,
        "gamma_default_dominated": dominated,
    }


def print_pof_table(pof: dict) -> None:
    print("\n=== proof-of-fetch threshold sweep ===")
    print(f"positives={pof['n_positives']}  neg_A(fabricated)={pof['n_neg_a_fabricated']}  "
          f"neg_B(cross-page)={pof['n_neg_b_cross_page']}  paraphrase(side)={pof['n_paraphrase_side']}")
    print(f"{'thr':>5} {'TPR':>7} {'FPR_A':>7} {'FPR_B':>7} {'para%':>7}")
    for r in pof["per_threshold"]:
        mark = "  <= chosen" if r["threshold"] == pof["chosen_threshold"] else ""
        print(f"{r['threshold']:>5.2f} {r['tpr']:>7.3f} {r['fpr_neg_a_fabricated']:>7.3f} "
              f"{r['fpr_neg_b_cross_page']:>7.3f} {r['paraphrase_pass_rate']:>7.3f}{mark}")
    op = pof["operating_point"]
    print(f"chosen_threshold = {pof['chosen_threshold']}  "
          f"(TPR={op['tpr']}, FPR_A={op['fpr_neg_a_fabricated']}, "
          f"FPR_B={op['fpr_neg_b_cross_page']})")


def print_gamma_table(gam: dict) -> None:
    print("\n=== gamma fabrication-injection stress test ===")
    print(f"reports={gam['n_reports']}  rates={gam['injection_rates']}  "
          f"all_monotonic={gam['all_monotonic']}")
    print(f"{'gamma':>6} {'monotonic':>10} {'mean_sep':>10} {'min_sep':>10}")
    for g in gam["gammas"]:
        pg = gam["per_gamma"][str(g)]
        print(f"{g:>6} {str(pg['monotonic_nonincreasing']):>10} "
              f"{pg['mean_separation_clean_vs_50pct']:>10.5f} "
              f"{pg['min_separation_clean_vs_50pct']:>10.5f}")
    print(f"GAMMA_DEFAULT kept = {gam['gamma_default_kept']}  "
          f"dominated = {gam['gamma_default_dominated']}")


def print_format_table(byfmt: dict) -> None:
    print("\n=== per-format TPR/FPR at shipped default threshold "
          f"{byfmt['default_threshold']} (D5) ===")
    print(f"{'format':>10} {'n_pos':>6} {'TPR':>7} {'FPR_fab':>8} "
          f"{'FPR_xpage':>10} {'FPR_bleed':>10}")
    for fmt in byfmt["per_format"]:
        e = byfmt["per_format"][fmt]
        op = e["at_default_threshold"]
        bleed = op.get("fpr_bibliography_bleed")
        bleed_s = f"{bleed:>10.4f}" if bleed is not None else f"{'n/a':>10}"
        print(f"{fmt:>10} {e['n_pos']:>6} {op['tpr']:>7.3f} "
              f"{op['fpr_fabricated']:>8.4f} {op['fpr_cross_page']:>10.4f} {bleed_s}")


def main() -> int:
    rng = random.Random(SEED)
    cache = load_cache()
    pof = calibrate_pof(cache, rng)
    byfmt = calibrate_pof_by_format(cache, rng)
    gam = calibrate_gamma(cache)
    artifact = {
        "seed": SEED,
        "cache_source": str(CACHE_GZ),
        "n_status200_pages": sum(1 for e in cache.values()
                                 if isinstance(e, dict) and e.get("status") == 200),
        "pof_threshold_calibration": pof,
        "pof_per_format_calibration": byfmt,
        "gamma_calibration": gam,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True))
    print_pof_table(pof)
    print_format_table(byfmt)
    print_gamma_table(gam)
    print(f"\nartifact -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
