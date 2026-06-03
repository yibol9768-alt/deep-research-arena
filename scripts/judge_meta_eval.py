#!/usr/bin/env python3
"""Label-free human-alignment validation for the Deep Research pairwise judge.

We have NO local human preference labels. This harness produces a defensible
"our judge tracks human judgment" number via three label-free methods, run
against the CONFIGURED judge model (e.g. GLM-5.1). The judge model is resolved
from --judge-model, then PAIRWISE_JUDGE_MODEL / JUDGE_MODEL env, then a lite
fallback, and the resolved model is threaded into every battle and stamped into
the output JSON (and any --doc), so the validation always describes the judge
we actually use:

  1. Synthetic-gold perturbation accuracy (PRIMARY, fully offline + lite judge).
     Take real report .md files, build programmatically DEGRADED variants
     (drop citations / inject false claims / truncate / shuffle paragraphs),
     then ask the judge to pick between (original, degraded). Any human prefers
     the original, so judge-accuracy here is an unambiguous human-agreement
     proxy. Reported per perturbation type and overall.

  2. Grounding correlation (offline, deterministic). Correlate the judge's
     per-report quality probe (round-robin pairwise win-rate over a small set)
     with the deterministic grounding signals already stored in
     data/results/deep_v3/*.score.json (must_cite_recall, quote_match). A judge
     that rates ungrounded reports highly is broken; positive Spearman is
     evidence of validity.

  3. Public judge-benchmark agreement (borrowed human labels) IF reachable.
     Try to fetch a small slice of LLMBar; run our judge on the pairs and
     report agreement with the human-labeled winner. Skipped with a clear note
     and a ready-to-run command when the network is unavailable.

The judge is sourced at runtime from /root/.config/dra/judge.env (or the
--judge-model flag). Project policy still forbids the pro tier; pass the
configured non-pro judge.

Usage:
    set -a; . /root/.config/dra/judge.env; set +a
    python3 scripts/judge_meta_eval.py --run synth grounding llmbar
    python3 scripts/judge_meta_eval.py --judge-model glm-5.1 --run synth
    python3 scripts/judge_meta_eval.py --dry-run            # plan only, no judge
    python3 scripts/judge_meta_eval.py --limit 4 --run synth

Outputs JSON to data/judge_gold/meta_eval_results.json and prints a summary.
The resolved judge model is stamped into that JSON and, when --doc is given,
into a delimited marker block of the named doc.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEEP_DIR = ROOT / "data" / "results" / "deep"
SCORE_DIR = ROOT / "data" / "results" / "deep_v3"
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
GOLD_DIR = ROOT / "data" / "judge_gold"
# Fallback judge model when neither --judge-model nor any env override is set.
# Kept as a module constant for backward compatibility; the actual model used
# is resolved at runtime by resolve_judge_model() and threaded into every
# battle() call (so the GLM-5.1 judge we will actually use is validated and
# stamped, not a hardwired default).
LITE_MODEL = "deepseek-v4-flash"


def resolve_judge_model(cli_model: str | None = None) -> str:
    """Resolve the judge model actually used for validation.

    Precedence (highest first): explicit --judge-model CLI value, then the
    PAIRWISE_JUDGE_MODEL env, then the shared JUDGE_MODEL env, then the lite
    fallback. This mirrors pairwise_judge._default_judge_model so the model we
    validate, run, and stamp is exactly the configured judge.
    """
    return (
        (cli_model or "").strip()
        or os.environ.get("PAIRWISE_JUDGE_MODEL")
        or os.environ.get("JUDGE_MODEL")
        or LITE_MODEL
    )

# Preferred (better) reports for the synthetic-gold set. We pick the larger,
# higher-grounding agents so the ORIGINAL is unambiguously a strong report.
PREFERRED_AGENTS = ("claude-code", "camel-ai", "smolagents")


# ---------------------------------------------------------------------------
# Report selection + task intent
# ---------------------------------------------------------------------------
def _task_id_from_name(name: str) -> str:
    m = re.search(r"(dr_cross_deep_\d+)", name)
    return m.group(1) if m else ""


def load_task_intent(task_id: str) -> str:
    p = TASKS_DIR / f"{task_id}.json"
    try:
        d = json.loads(p.read_text())
        return d.get("intent", "") or f"Deep research task {task_id}."
    except Exception:
        return f"Deep research task {task_id}."


def pick_reports(limit: int) -> list[Path]:
    """Pick up to `limit` strong real reports, biased to preferred agents and
    larger files (more citations / structure to degrade meaningfully)."""
    cands: list[Path] = []
    for agent in PREFERRED_AGENTS:
        cands.extend(sorted(DEEP_DIR.glob(f"{agent}__*_matrix.md")))
    # Deduplicate, drop tiny reports, sort by size desc for the strongest.
    uniq = {p.resolve(): p for p in cands if p.is_file()}
    sized = sorted(uniq.values(), key=lambda p: p.stat().st_size, reverse=True)
    sized = [p for p in sized if p.stat().st_size > 8000]
    # Spread across tasks: avoid picking 8 reports of the same task_id.
    seen_tasks: set[str] = set()
    chosen: list[Path] = []
    for p in sized:
        tid = _task_id_from_name(p.name)
        if tid in seen_tasks:
            continue
        seen_tasks.add(tid)
        chosen.append(p)
        if len(chosen) >= limit:
            break
    # Top up if we ran out of distinct tasks.
    if len(chosen) < limit:
        for p in sized:
            if p not in chosen:
                chosen.append(p)
            if len(chosen) >= limit:
                break
    return chosen[:limit]


# ---------------------------------------------------------------------------
# Perturbations: each takes the original markdown, returns a degraded variant.
# Any reasonable human prefers the ORIGINAL over each of these.
# ---------------------------------------------------------------------------
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

# The pairwise judge only ever sees the first JUDGE_VISIBLE_CHARS of each
# report (hard slice in pairwise_judge._judge_once: `(ans or '')[:5000]`).
# A perturbation that only changes text BEYOND this window is invisible to the
# judge and produces a spurious TIE, which is a property of the deployed judge,
# not a judge failure. To measure the judge as it is actually deployed, we
# clip the original to this window FIRST, then degrade within it, so every
# perturbation bites on content the judge can see.
JUDGE_VISIBLE_CHARS = 5000


def clip_to_visible(text: str) -> str:
    """Clip a report to the judge-visible prefix, on a clean boundary."""
    if len(text) <= JUDGE_VISIBLE_CHARS:
        return text
    cut = text[:JUDGE_VISIBLE_CHARS]
    # Prefer a paragraph boundary so we do not cut mid-sentence.
    nl = cut.rfind("\n\n")
    if nl > JUDGE_VISIBLE_CHARS * 0.6:
        cut = cut[:nl]
    return cut.rstrip()


FALSE_CLAIMS = [
    "All headphones reviewed here are waterproof to a depth of 50 meters, per the manufacturer.",
    "Bluetooth headphones cause permanent hearing loss in 90% of users within one month.",
    "Every product listed retails for exactly $9.99 with free lifetime replacement.",
    "Noise-cancelling technology was invented in 2021 and is banned in the European Union.",
    "The Wikipedia source confirms that all wireless earbuds emit dangerous levels of radiation.",
]


def perturb_drop_citations(text: str, rng: random.Random) -> str:
    """Drop ~70% of markdown citations, leaving the prose ungrounded."""
    links = list(_LINK_RE.finditer(text))
    if not links:
        # No markdown links: strip bare URLs instead.
        return re.sub(r"(?<!\()https?://\S+", "", text)
    drop_idx = set(rng.sample(range(len(links)), k=max(1, int(len(links) * 0.7))))
    out, last = [], 0
    for i, m in enumerate(links):
        out.append(text[last:m.start()])
        if i in drop_idx:
            out.append(m.group(1))  # keep anchor text, drop the URL
        else:
            out.append(m.group(0))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def perturb_inject_false_claims(text: str, rng: random.Random) -> str:
    """Inject 2-3 unsupported / false claims near the TOP of the body.

    We insert into the first few paragraphs so the claims fall inside the
    judge-visible window even for very long reports."""
    paras = text.split("\n\n")
    n = min(3, max(2, len(FALSE_CLAIMS)))
    claims = rng.sample(FALSE_CLAIMS, k=min(n, len(FALSE_CLAIMS)))
    if len(paras) < 4:
        return text + "\n\n" + "\n\n".join(claims)
    upper = max(2, min(len(paras) - 1, 6))  # within the first ~6 paragraphs
    for c in claims:
        pos = rng.randint(1, upper)
        paras.insert(pos, c)
    return "\n\n".join(paras)


def perturb_truncate(text: str, rng: random.Random) -> str:
    """Truncate to ~40% of the (visible) length, dropping later analysis.

    Because the harness clips reports to the judge-visible window before
    perturbing, 40% of that window is well inside what the judge reads, so the
    judge genuinely sees a shorter, less complete report."""
    cut = max(200, int(len(text) * 0.40))
    return text[:cut].rstrip() + "\n\n[report ends abruptly]"


def perturb_shuffle_paragraphs(text: str, rng: random.Random) -> str:
    """Shuffle paragraph order, destroying logical flow and signposting."""
    paras = [p for p in text.split("\n\n") if p.strip()]
    if len(paras) < 3:
        return text
    # Keep the title line in place, shuffle the rest.
    head, body = paras[0], paras[1:]
    rng.shuffle(body)
    return "\n\n".join([head] + body)


PERTURBATIONS: dict[str, Callable[[str, random.Random], str]] = {
    "drop_citations": perturb_drop_citations,
    "inject_false_claims": perturb_inject_false_claims,
    "truncate": perturb_truncate,
    "shuffle_paragraphs": perturb_shuffle_paragraphs,
}


# ---------------------------------------------------------------------------
# Method 1: synthetic-gold perturbation accuracy
# ---------------------------------------------------------------------------
def run_synthetic_gold(
    battle_fn, reports: list[Path], *, n_samples: int, seed: int, dry_run: bool,
    judge_model: str = LITE_MODEL,
) -> dict[str, Any]:
    rng = random.Random(seed)
    per_type: dict[str, dict[str, Any]] = {
        k: {"correct": 0, "total": 0, "ties": 0, "trials": []}
        for k in PERTURBATIONS
    }
    plan = []
    for rp in reports:
        # Clip to the judge-visible window first: the judge only ever reads
        # this prefix, so this is the fair comparison surface. Perturbations
        # then degrade content the judge can actually see.
        original = clip_to_visible(rp.read_text(errors="ignore"))
        task_id = _task_id_from_name(rp.name)
        intent = load_task_intent(task_id)
        for ptype, fn in PERTURBATIONS.items():
            degraded = fn(original, random.Random(rng.randint(0, 1_000_000)))
            plan.append((rp.name, ptype, len(original), len(degraded)))
            if dry_run:
                continue
            # Original is agent_a, degraded is agent_b. battle() runs its own
            # internal position swap, so labels here do not bias the verdict.
            res = battle_fn(
                task_intent=intent,
                agent_a="original",
                answer_a=original,
                agent_b="degraded",
                answer_b=degraded,
                dimension=None,
                n_samples=n_samples,
                model=judge_model,
            )
            winner = (res.get("agent_winner") or "tie")
            rec = per_type[ptype]
            rec["total"] += 1
            if winner == "original":
                rec["correct"] += 1
            elif winner == "tie":
                rec["ties"] += 1
            rec["trials"].append(
                {"report": rp.name, "winner": winner,
                 "verdicts": res.get("verdicts_raw"), "error": res.get("error")}
            )

    if dry_run:
        return {"dry_run": True, "planned_battles": len(plan), "plan": plan[:40]}

    overall_correct = sum(v["correct"] for v in per_type.values())
    overall_total = sum(v["total"] for v in per_type.values())
    summary = {}
    for k, v in per_type.items():
        summary[k] = {
            "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else None,
            "correct": v["correct"], "total": v["total"], "ties": v["ties"],
        }
    return {
        "n_reports": len(reports),
        "n_samples": n_samples,
        "per_type": summary,
        "overall_accuracy": round(overall_correct / overall_total, 4) if overall_total else None,
        "overall_correct": overall_correct,
        "overall_total": overall_total,
        "trials": {k: v["trials"] for k, v in per_type.items()},
    }


# ---------------------------------------------------------------------------
# Method 2: grounding correlation
# ---------------------------------------------------------------------------
def load_grounding_signal(report_path: Path) -> dict[str, float] | None:
    score_path = SCORE_DIR / (report_path.stem + ".score.json")
    if not score_path.is_file():
        return None
    try:
        d = json.loads(score_path.read_text())
    except Exception:
        return None
    mcr = (
        d.get("url_coverage", {}).get("details", {}).get("must_cite_recall")
    )
    qm = d.get("quote_match", {}).get("score")
    if mcr is None and qm is None:
        return None
    # Composite grounding signal: average of the two deterministic signals.
    parts = [x for x in (mcr, qm) if x is not None]
    return {
        "must_cite_recall": mcr,
        "quote_match": qm,
        "grounding": sum(parts) / len(parts) if parts else None,
    }


def run_grounding_correlation(
    battle_fn, reports: list[Path], *, n_samples: int, dry_run: bool,
    judge_model: str = LITE_MODEL,
) -> dict[str, Any]:
    # Keep reports that have a deterministic grounding signal.
    items = []
    for rp in reports:
        sig = load_grounding_signal(rp)
        if sig and sig.get("grounding") is not None:
            items.append((rp, sig))
    if len(items) < 3:
        return {"skipped": True, "reason": f"only {len(items)} reports have grounding signals; need >=3"}

    if dry_run:
        n = len(items)
        return {"dry_run": True, "n_reports": n, "planned_battles": n * (n - 1) // 2 * 1}

    # Judge quality probe = round-robin pairwise win-rate. We use a single
    # debiased round (n_samples) per pair; win=1, tie=0.5, loss=0.
    n = len(items)
    wins = [0.0] * n
    games = [0] * n
    pair_log = []
    for i in range(n):
        for j in range(i + 1, n):
            rp_i, _ = items[i]
            rp_j, _ = items[j]
            # Same-task comparison is most meaningful, but cross-task is still a
            # valid global-quality probe; intents differ so we pass i's intent
            # plus j's intent context-free by using a generic quality framing.
            intent_i = load_task_intent(_task_id_from_name(rp_i.name))
            res = battle_fn(
                task_intent=intent_i,
                agent_a=rp_i.name,
                answer_a=rp_i.read_text(errors="ignore"),
                agent_b=rp_j.name,
                answer_b=rp_j.read_text(errors="ignore"),
                dimension=None,
                n_samples=n_samples,
                model=judge_model,
            )
            w = res.get("agent_winner")
            games[i] += 1
            games[j] += 1
            if w == rp_i.name:
                wins[i] += 1.0
            elif w == rp_j.name:
                wins[j] += 1.0
            else:
                wins[i] += 0.5
                wins[j] += 0.5
            pair_log.append({"a": rp_i.name, "b": rp_j.name, "winner": w})

    judge_winrate = [wins[k] / games[k] if games[k] else 0.0 for k in range(n)]
    grounding = [items[k][1]["grounding"] for k in range(n)]
    mcr = [items[k][1]["must_cite_recall"] for k in range(n)]
    qm = [items[k][1]["quote_match"] for k in range(n)]

    out: dict[str, Any] = {
        "n_reports": n,
        "reports": [items[k][0].name for k in range(n)],
        "judge_winrate": [round(x, 4) for x in judge_winrate],
        "grounding": grounding,
        "must_cite_recall": mcr,
        "quote_match": qm,
        "pair_log": pair_log,
    }
    try:
        from scipy.stats import spearmanr  # type: ignore
        for label, signal in (("grounding", grounding), ("must_cite_recall", mcr), ("quote_match", qm)):
            clean = [(jw, s) for jw, s in zip(judge_winrate, signal) if s is not None]
            if len(clean) >= 3 and len({s for _, s in clean}) > 1:
                rho, p = spearmanr([c[0] for c in clean], [c[1] for c in clean])
                out[f"spearman_{label}"] = {"rho": round(float(rho), 4), "p": round(float(p), 4), "n": len(clean)}
            else:
                out[f"spearman_{label}"] = {"skipped": "insufficient variance/points"}
    except Exception as e:
        out["spearman_error"] = f"{type(e).__name__}: {e}"
    return out


# ---------------------------------------------------------------------------
# Method 3: public judge-benchmark agreement (LLMBar) IF reachable
# ---------------------------------------------------------------------------
LLMBAR_URL = (
    "https://raw.githubusercontent.com/princeton-nlp/LLMBar/main/"
    "Dataset/LLMBar/Natural/dataset.json"
)
LLMBAR_LOCAL = GOLD_DIR / "llmbar_natural.json"


def _try_download_llmbar() -> tuple[list | None, str]:
    # Use a cached local copy if present.
    if LLMBAR_LOCAL.is_file():
        try:
            return json.loads(LLMBAR_LOCAL.read_text()), "cached"
        except Exception:
            pass
    proxies = {}
    if os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY"):
        pass  # urllib honors env proxies automatically
    try:
        import urllib.request
        req = urllib.request.Request(LLMBAR_URL, headers={"User-Agent": "dra-meta-eval"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
        data = json.loads(raw)
        GOLD_DIR.mkdir(parents=True, exist_ok=True)
        LLMBAR_LOCAL.write_text(json.dumps(data))
        return data, "downloaded"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def run_llmbar(battle_fn, *, limit: int, n_samples: int, dry_run: bool,
               judge_model: str = LITE_MODEL) -> dict[str, Any]:
    ready_cmd = (
        "  # Run on a box with network/proxy:\n"
        "  set -a; . /root/.config/dra/judge.env; set +a\n"
        "  HTTPS_PROXY=http://172.30.48.1:7890 python3 scripts/judge_meta_eval.py --run llmbar --limit 80"
    )
    if dry_run:
        return {"dry_run": True, "note": "would attempt LLMBar download then judge"}
    data, status = _try_download_llmbar()
    if data is None:
        return {
            "skipped": True,
            "reason": f"LLMBar download failed ({status}); no local human labels available",
            "ready_to_run": ready_cmd,
        }
    # LLMBar Natural schema: each item has input, output_1, output_2, label
    # (1 or 2 = the human-preferred output).
    pairs = data[:limit] if isinstance(data, list) else []
    correct = total = ties = 0
    trials = []
    for it in pairs:
        gold = it.get("label")
        if gold not in (1, 2):
            continue
        res = battle_fn(
            task_intent=it.get("input", ""),
            agent_a="out1",
            answer_a=it.get("output_1", ""),
            agent_b="out2",
            answer_b=it.get("output_2", ""),
            dimension=None,
            n_samples=n_samples,
            model=judge_model,
        )
        w = res.get("agent_winner")
        judged = 1 if w == "out1" else (2 if w == "out2" else 0)
        total += 1
        if judged == 0:
            ties += 1
        elif judged == gold:
            correct += 1
        trials.append({"gold": gold, "judged": judged})
    return {
        "source": "LLMBar Natural",
        "status": status,
        "n_pairs": total,
        "agreement": round(correct / total, 4) if total else None,
        "correct": correct,
        "ties": ties,
        "trials": trials,
    }


# ---------------------------------------------------------------------------
# Doc stamping: record the REAL judge model that produced the validation run
# ---------------------------------------------------------------------------
DOC_STAMP_BEGIN = "<!-- JUDGE_META_EVAL_STAMP:BEGIN -->"
DOC_STAMP_END = "<!-- JUDGE_META_EVAL_STAMP:END -->"


def stamp_doc(doc_path: Path, judge_model: str) -> bool:
    """Stamp the REAL judge model into a markdown doc, idempotently.

    Replaces (or inserts at the top, after a leading H1 if present) a clearly
    delimited marker block recording the judge model that produced the latest
    validation run. Everything outside the marker block is left untouched, so
    re-stamping with a new model only updates the one block. Returns True when
    the doc was written.
    """
    block = (
        f"{DOC_STAMP_BEGIN}\n"
        f"Validated judge model: `{judge_model}`\n"
        f"{DOC_STAMP_END}"
    )
    try:
        text = doc_path.read_text()
    except FileNotFoundError:
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(block + "\n")
        return True

    begin = text.find(DOC_STAMP_BEGIN)
    end = text.find(DOC_STAMP_END)
    if begin != -1 and end != -1 and end > begin:
        new_text = text[:begin] + block + text[end + len(DOC_STAMP_END):]
        doc_path.write_text(new_text)
        return True

    # No existing block: insert after a leading H1 title if one exists, else
    # prepend to the top of the doc.
    lines = text.splitlines(keepends=True)
    if lines and lines[0].lstrip().startswith("# "):
        head = lines[0]
        rest = "".join(lines[1:])
        doc_path.write_text(head + "\n" + block + "\n\n" + rest.lstrip("\n"))
    else:
        doc_path.write_text(block + "\n\n" + text)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _get_battle_fn():
    from src.scoring.pairwise_judge import battle
    return battle


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", nargs="+", default=["synth", "grounding", "llmbar"],
                    choices=["synth", "grounding", "llmbar"],
                    help="which methods to run")
    ap.add_argument("--limit", type=int, default=8,
                    help="max reports (synth/grounding) or LLMBar pairs cap base")
    ap.add_argument("--llmbar-pairs", type=int, default=60, help="max LLMBar pairs to judge")
    ap.add_argument("--n-samples", type=int, default=3, help="judge debiased rounds per battle")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--dry-run", action="store_true", help="plan only; do not call the judge")
    ap.add_argument("--out", default=str(GOLD_DIR / "meta_eval_results.json"))
    ap.add_argument(
        "--judge-model", default=None,
        help="judge model to validate (overrides PAIRWISE_JUDGE_MODEL / "
             "JUDGE_MODEL env). The resolved model is stamped into the output "
             "JSON and any --doc.",
    )
    ap.add_argument(
        "--doc", default=None,
        help="markdown doc to stamp the REAL validated judge model into "
             "(idempotent; updates a delimited marker block only).",
    )
    args = ap.parse_args(argv)

    # Resolve the judge model that we actually validate / run / stamp, so the
    # configured judge (e.g. GLM-5.1) is what gets measured, not a hardwired
    # default. CLI flag wins, then PAIRWISE_JUDGE_MODEL / JUDGE_MODEL env.
    judge_model = resolve_judge_model(args.judge_model)

    battle_fn = None if args.dry_run else _get_battle_fn()

    reports = pick_reports(args.limit)
    results: dict[str, Any] = {
        "judge_model": judge_model,
        "dry_run": args.dry_run,
        "n_samples": args.n_samples,
        "reports_selected": [p.name for p in reports],
    }

    print(f"[judge] validating judge_model={judge_model!r}", file=sys.stderr)

    if "synth" in args.run:
        print(f"[synth] {len(reports)} reports x {len(PERTURBATIONS)} perturbations ...", file=sys.stderr)
        results["synthetic_gold"] = run_synthetic_gold(
            battle_fn, reports, n_samples=args.n_samples, seed=args.seed,
            dry_run=args.dry_run, judge_model=judge_model,
        )
    if "grounding" in args.run:
        print("[grounding] correlating judge win-rate with deterministic signals ...", file=sys.stderr)
        results["grounding_correlation"] = run_grounding_correlation(
            battle_fn, reports, n_samples=args.n_samples, dry_run=args.dry_run,
            judge_model=judge_model,
        )
    if "llmbar" in args.run:
        print("[llmbar] attempting public judge-benchmark slice ...", file=sys.stderr)
        results["llmbar_agreement"] = run_llmbar(
            battle_fn, limit=args.llmbar_pairs, n_samples=args.n_samples,
            dry_run=args.dry_run, judge_model=judge_model,
        )

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))
    if args.doc:
        stamp_doc(Path(args.doc), judge_model)
        print(f"Stamped judge_model into doc -> {args.doc}", file=sys.stderr)
    print(json.dumps(_compact_summary(results), indent=2))
    print(f"\nFull results -> {args.out}", file=sys.stderr)
    return 0


def _compact_summary(results: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"judge_model": results.get("judge_model"), "dry_run": results.get("dry_run")}
    sg = results.get("synthetic_gold")
    if sg and not sg.get("dry_run"):
        out["synthetic_gold"] = {
            "overall_accuracy": sg.get("overall_accuracy"),
            "per_type": {k: v.get("accuracy") for k, v in sg.get("per_type", {}).items()},
        }
    elif sg:
        out["synthetic_gold"] = {"planned_battles": sg.get("planned_battles")}
    gc = results.get("grounding_correlation")
    if gc:
        out["grounding_correlation"] = {
            k: gc.get(k) for k in ("spearman_grounding", "spearman_must_cite_recall",
                                   "spearman_quote_match", "skipped", "dry_run", "planned_battles")
            if k in gc
        }
    lb = results.get("llmbar_agreement")
    if lb:
        out["llmbar_agreement"] = {k: lb.get(k) for k in ("agreement", "n_pairs", "skipped", "reason", "dry_run") if k in lb}
    return out


if __name__ == "__main__":
    raise SystemExit(main())
