"""Judge-vs-human alignment validation harness.

Measures how closely the LLM judges agree with HUMAN preference judgments,
per dimension, so we can verify and iterate toward "close to human".

Two modes:

  (default) human-aligned mode
    For each labeled pair in data/human_prefs/*.jsonl, load report A and
    report B, compute the JUDGE verdict per dimension via the redesigned
    dimension-aware pairwise judge, and compare against the human label.
    Writes per-dimension Cohen kappa + raw agreement + n to
    docs/JUDGE_HUMAN_ALIGNMENT_V2.md, with a before/after column if a prior
    docs/JUDGE_HUMAN_KAPPA.md is found and parseable.

  --proxy mode (no human labels needed)
    Reports two measurable proxies on a sample of report pairs:
      - judge self-consistency: agreement across N repeated judge samples
        of the same pair.
      - inter-judge agreement: agreement between two judge families if two
        are configured in the env, else a clear note that only one is.
    Proxies are necessary-but-not-sufficient for human alignment.

The judge interface is detected at RUNTIME (try/except) because a sibling
change may expose either a dimension-aware `src.scoring.pairwise_judge.battle`
or a per-dim `verify_pairwise` on `src.verifiers.*`. Tests mock this; the
real run is done by the operator after sourcing the judge env:

    set -a; . /root/.config/dra/judge.env; set +a
    python3 scripts/validate_judge_alignment.py

Constraints: never crash on missing data; report what is missing.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PREFS_DIR = ROOT / "data" / "human_prefs"
REPORT_DIRS = [
    ROOT / "data" / "results" / "deep_reports",
    ROOT / "data" / "results" / "deep",
]
TASK_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
OUT_MD = ROOT / "docs" / "JUDGE_HUMAN_ALIGNMENT_V2.md"
PRIOR_MD = ROOT / "docs" / "JUDGE_HUMAN_KAPPA.md"

ALL_DIMS = ["coverage", "depth", "rigor", "style", "checklist", "spec"]
DEFAULT_DIMS = ["depth", "rigor", "style", "checklist"]


# ---------------------------------------------------------------------------
# Data loading (robust; never raises on missing files)
# ---------------------------------------------------------------------------

def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def load_prefs(prefs_dir: Path) -> list[dict]:
    if not prefs_dir.exists():
        return []
    out: list[dict] = []
    for p in sorted(prefs_dir.glob("*.jsonl")):
        try:
            text = p.read_text()
        except OSError:
            continue
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def cited_dims(rec: dict) -> set[str]:
    """Union of the legacy `dims_cited` and the new `dims` field."""
    return set(rec.get("dims_cited") or []) | set(rec.get("dims") or [])


def find_report(agent: str, task_id: str, report_dirs: list[Path]) -> Path | None:
    """Locate a report .md deterministically. Tries the canonical name and
    the `_matrix` / `_smoke` suffixes, in each report dir in order."""
    suffixes = ["", "_matrix", "_smoke"]
    for d in report_dirs:
        for suf in suffixes:
            cand = d / f"{agent}__{task_id}{suf}.md"
            if cand.exists():
                return cand
    return None


def load_report_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def load_task_intent(task_id: str, task_dir: Path) -> str:
    p = task_dir / f"{task_id}.json"
    if not p.exists():
        return ""
    try:
        tj = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    return str(tj.get("intent") or tj.get("question") or "") or ""


# ---------------------------------------------------------------------------
# Runtime judge-interface detection
# ---------------------------------------------------------------------------

class JudgeUnavailable(RuntimeError):
    pass


def make_judge():
    """Return a callable judge(dim, task_intent, agent_a, ans_a, agent_b, ans_b)
    -> 'a' | 'b' | 'tie', detecting at runtime which interface Job A exposed.

    Tries, in order:
      1. src.scoring.pairwise_judge.battle(..., dimension=dim)   (dimension-aware)
      2. src.scoring.pairwise_judge.battle(...)                  (overall, dim-blind)
      3. src.verifiers.* verify_pairwise(dim=...)                (per-dim verifier)
    Raises JudgeUnavailable with a clear message if none is callable.
    """
    # Option 1 / 2: pairwise_judge.battle
    battle = None
    try:
        from src.scoring.pairwise_judge import battle as _battle  # type: ignore
        battle = _battle
    except Exception:
        battle = None

    if battle is not None:
        import inspect
        try:
            sig = inspect.signature(battle)
            has_dim = "dimension" in sig.parameters
        except (TypeError, ValueError):
            has_dim = False

        def _judge_battle(dim, task_intent, agent_a, ans_a, agent_b, ans_b):
            kwargs = dict(
                task_intent=task_intent,
                agent_a=agent_a, answer_a=ans_a,
                agent_b=agent_b, answer_b=ans_b,
            )
            if has_dim:
                kwargs["dimension"] = dim
            res = battle(**kwargs)
            w = (res or {}).get("winner", "tie")
            w = str(w).lower()
            return w if w in ("a", "b") else "tie"

        return _judge_battle, ("pairwise_judge.battle(dimension=...)"
                               if has_dim else "pairwise_judge.battle(overall)")

    # Option 3: a per-dim verify_pairwise exposed somewhere under src.verifiers
    verify_pairwise = None
    try:
        import importlib
        vmod = importlib.import_module("src.verifiers")
        verify_pairwise = getattr(vmod, "verify_pairwise", None)
        if verify_pairwise is None:
            # Common module names a sibling might use.
            for name in ("pairwise", "pairwise_verifier", "verify_pairwise"):
                try:
                    sub = importlib.import_module(f"src.verifiers.{name}")
                except Exception:
                    continue
                verify_pairwise = getattr(sub, "verify_pairwise", None)
                if verify_pairwise is not None:
                    break
    except Exception:
        verify_pairwise = None

    if verify_pairwise is not None:
        def _judge_verify(dim, task_intent, agent_a, ans_a, agent_b, ans_b):
            try:
                res = verify_pairwise(
                    answer_a=ans_a, answer_b=ans_b,
                    dimension=dim, task_intent=task_intent,
                )
            except TypeError:
                # Positional fallback.
                res = verify_pairwise(ans_a, ans_b, dim)
            if isinstance(res, dict):
                w = str(res.get("winner", "tie")).lower()
            else:
                w = str(res).lower()
            return w if w in ("a", "b") else "tie"

        return _judge_verify, "verifiers.verify_pairwise(dimension=...)"

    raise JudgeUnavailable(
        "No judge interface available: neither "
        "`src.scoring.pairwise_judge.battle` nor a `verify_pairwise` on "
        "`src.verifiers.*` could be imported. The dimension-aware judge "
        "from the eval-redesign work is required to measure alignment."
    )


# ---------------------------------------------------------------------------
# Cohen kappa over binary {a, b}
# ---------------------------------------------------------------------------

def cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float, int, float]:
    """Return (kappa, n_used, raw_agreement) over binary labels in {a, b}.
    'tie' on either side is dropped. kappa is nan when undefined."""
    labels = ["a", "b"]
    counts = {l: defaultdict(int) for l in labels}
    for h, j in pairs:
        if h not in labels or j not in labels:
            continue
        counts[h][j] += 1
    n_used = sum(counts[l][m] for l in labels for m in labels)
    if n_used == 0:
        return float("nan"), 0, float("nan")
    po = sum(counts[l][l] for l in labels) / n_used
    pa = {l: sum(counts[l][m] for m in labels) / n_used for l in labels}
    pj = {l: sum(counts[m][l] for m in labels) / n_used for l in labels}
    pe = sum(pa[l] * pj[l] for l in labels)
    if abs(1 - pe) < 1e-12:
        return float("nan"), n_used, po
    return float((po - pe) / (1 - pe)), n_used, po


def _interp(k: float, n: int) -> str:
    if n < 10:
        return "(too few rows)"
    if k != k:
        return "undefined"
    if k < 0.20:
        return "near-chance"
    if k < 0.40:
        return "fair"
    if k < 0.60:
        return "moderate"
    if k < 0.80:
        return "substantial"
    return "almost perfect"


def parse_prior_kappa(path: Path) -> dict[str, float]:
    """Best-effort parse of the prior docs/JUDGE_HUMAN_KAPPA.md table.
    Returns {dim: kappa}. Never raises."""
    out: dict[str, float] = {}
    if not path.exists():
        return out
    try:
        text = path.read_text()
    except OSError:
        return out
    # Rows look like: | depth | 29 | 0.246 | fair |
    row_re = re.compile(r"^\|\s*([a-z]+)\s*\|\s*\d+\s*\|\s*(nan|-?\d+\.\d+)\s*\|", re.I)
    for ln in text.splitlines():
        m = row_re.match(ln.strip())
        if not m:
            continue
        dim = m.group(1).lower()
        if dim not in ALL_DIMS:
            continue
        raw = m.group(2).lower()
        try:
            out[dim] = float("nan") if raw == "nan" else float(raw)
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# Work-list build
# ---------------------------------------------------------------------------

def build_worklist(prefs, dims, report_dirs, limit):
    """Return (rows, missing_reports). Each row is a dict with the resolved
    report paths and the human verdict. Rows whose reports cannot both be
    found are skipped (counted in missing_reports)."""
    rows = []
    missing = 0
    for rec in prefs:
        a = rec.get("agent_a")
        b = rec.get("agent_b")
        tid = rec.get("task_id")
        w = str(rec.get("winner", "")).lower()
        if not (a and b and tid):
            continue
        pa = find_report(a, tid, report_dirs)
        pb = find_report(b, tid, report_dirs)
        if pa is None or pb is None:
            missing += 1
            continue
        rows.append({
            "task_id": tid, "agent_a": a, "agent_b": b,
            "winner": w, "dims": cited_dims(rec),
            "path_a": pa, "path_b": pb,
        })
        if limit and len(rows) >= limit:
            break
    return rows, missing


# ---------------------------------------------------------------------------
# Human-aligned mode
# ---------------------------------------------------------------------------

def run_alignment(args, judge_factory=make_judge):
    dims = args.dims
    prefs = load_prefs(PREFS_DIR)
    if not prefs:
        print("no human labels found at data/human_prefs/*.jsonl; "
              "nothing to align. Use --proxy for offline proxy metrics.")
        return 0

    rows, missing = build_worklist(prefs, dims, REPORT_DIRS, args.limit)
    print(f"[align] labeled prefs={len(prefs)} usable pairs={len(rows)} "
          f"missing-reports={missing} dims={','.join(dims)}")

    if args.dry_run:
        print(f"[align] --dry-run: {len(rows)} pairs would be judged "
              f"across {len(dims)} dim(s) (no judge calls made).")
        return 0

    if not rows:
        print("[align] no usable pairs (reports missing); nothing to judge.")
        return 0

    try:
        judge, iface = judge_factory()
    except JudgeUnavailable as e:
        print(f"[align] ERROR: {e}", file=sys.stderr)
        return 2
    print(f"[align] judge interface: {iface}")

    per_dim: dict[str, list[tuple[str, str]]] = {d: [] for d in dims}
    for row in rows:
        if row["winner"] not in ("a", "b", "tie"):
            continue
        intent = load_task_intent(row["task_id"], TASK_DIR)
        ans_a = load_report_text(row["path_a"])
        ans_b = load_report_text(row["path_b"])
        # Only score dims the annotator cited (matching the kappa method);
        # if none cited, fall back to all requested dims.
        target_dims = [d for d in dims if d in row["dims"]] or list(dims)
        for d in target_dims:
            j = judge(d, intent, row["agent_a"], ans_a, row["agent_b"], ans_b)
            per_dim[d].append((row["winner"], j))

    prior = parse_prior_kappa(PRIOR_MD)
    results = {d: cohen_kappa(per_dim[d]) for d in dims}

    eligible = [(d, k) for d, (k, n, _) in results.items() if n >= 10 and k == k]
    if eligible:
        weakest_dim, weakest_k = min(eligible, key=lambda kv: kv[1])
    else:
        weakest_dim, weakest_k = "(insufficient data)", float("nan")

    # Overall: pool all (human, judge) pairs across dims.
    overall_pairs = [p for d in dims for p in per_dim[d]]
    ok, on, oagree = cohen_kappa(overall_pairs)

    write_alignment_md(OUT_MD, results, prior, overall=(ok, on, oagree),
                       weakest=(weakest_dim, weakest_k), iface=iface,
                       n_prefs=len(prefs), n_pairs=len(rows), missing=missing,
                       dims=dims)
    print(f"[align] wrote {_rel(OUT_MD)}; overall kappa="
          f"{'nan' if ok != ok else f'{ok:.3f}'} weakest={weakest_dim}")
    return 0


def write_alignment_md(path, results, prior, *, overall, weakest, iface,
                       n_prefs, n_pairs, missing, dims):
    ok, on, oagree = overall
    weakest_dim, weakest_k = weakest
    lines = []
    lines.append("# Judge / Human alignment (V2)")
    lines.append("")
    lines.append(f"_Generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append(f"_Judge interface: `{iface}`_")
    lines.append(f"_Labeled prefs={n_prefs}, usable pairs={n_pairs}, "
                 f"missing-reports={missing}_")
    lines.append("")
    has_prior = bool(prior)
    if has_prior:
        lines.append("| dim | n | raw agreement | kappa (V2) | kappa (prior) | delta | interpretation |")
        lines.append("|-----|---|---------------|------------|---------------|-------|----------------|")
    else:
        lines.append("| dim | n | raw agreement | kappa | interpretation |")
        lines.append("|-----|---|---------------|-------|----------------|")
    for d in dims:
        k, n, agree = results[d]
        ks = "nan" if k != k else f"{k:.3f}"
        ag = "nan" if agree != agree else f"{agree:.3f}"
        interp = _interp(k, n)
        if has_prior:
            pk = prior.get(d, float("nan"))
            pks = "nan" if pk != pk else f"{pk:.3f}"
            if k == k and pk == pk:
                ds = f"{k - pk:+.3f}"
            else:
                ds = "n/a"
            lines.append(f"| {d} | {n} | {ag} | {ks} | {pks} | {ds} | {interp} |")
        else:
            lines.append(f"| {d} | {n} | {ag} | {ks} | {interp} |")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    oks = "nan" if ok != ok else f"{ok:.3f}"
    oag = "nan" if oagree != oagree else f"{oagree:.3f}"
    lines.append(f"Pooled across dims: kappa={oks}, raw agreement={oag}, n={on}.")
    lines.append("")
    lines.append("## Weakest dimension")
    lines.append("")
    if weakest_dim == "(insufficient data)":
        lines.append("Not enough dim-cited prefs (>= 10 per dim) to choose a "
                     "weakest dimension yet. Collect more human labels.")
    else:
        lines.append(f"The lowest-kappa dimension is **{weakest_dim}** "
                     f"(kappa={weakest_k:.3f}). Iterate this rubric next: "
                     "tighten the criterion, add few-shot exemplars.")
    lines.append("")
    lines.append("## Method note")
    lines.append("")
    lines.append("For each labeled pair `(A, B)`, the JUDGE verdict is computed "
                 "per dimension via the dimension-aware pairwise judge and "
                 "compared to the human `winner`. Where the annotator cited "
                 "specific dims, only those dims are scored for that pair; "
                 "otherwise all requested dims are scored. 'Tie' verdicts on "
                 "either side are dropped from the binary {A, B} kappa.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Proxy mode
# ---------------------------------------------------------------------------

def discover_corpus_pairs(report_dirs, limit):
    """Build report pairs from the corpus by grouping <agent>__<task_id> files
    by task_id and pairing distinct agents. Deterministic ordering."""
    by_task: dict[str, dict[str, Path]] = defaultdict(dict)
    name_re = re.compile(r"^(?P<agent>.+?)__(?P<task>.+?)(?:_matrix|_smoke)?\.md$")
    for d in report_dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            m = name_re.match(p.name)
            if not m:
                continue
            agent, task = m.group("agent"), m.group("task")
            by_task[task].setdefault(agent, p)
    pairs = []
    for task in sorted(by_task):
        agents = sorted(by_task[task])
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                pairs.append({
                    "task_id": task,
                    "agent_a": agents[i], "path_a": by_task[task][agents[i]],
                    "agent_b": agents[j], "path_b": by_task[task][agents[j]],
                })
                if limit and len(pairs) >= limit:
                    return pairs
    return pairs


def detect_judge_families():
    """Return a list of (label, env-overrides) describing distinct judge
    families configured in the env. Currently one provider/model is set per
    process; we report what is configured rather than forcibly running two."""
    import os
    fams = []
    primary_model = (os.environ.get("PAIRWISE_JUDGE_MODEL")
                     or os.environ.get("JUDGE_MODEL")
                     or os.environ.get("CHECKLIST_JUDGE_MODEL"))
    primary_provider = os.environ.get("JUDGE_PROVIDER", "anthropic")
    if primary_model:
        fams.append((f"{primary_provider}:{primary_model}", {}))
    secondary = os.environ.get("JUDGE_MODEL_SECONDARY") or os.environ.get("JUDGE_MODEL_B")
    if secondary:
        fams.append((f"{primary_provider}:{secondary}",
                     {"JUDGE_MODEL": secondary, "PAIRWISE_JUDGE_MODEL": secondary}))
    return fams


def run_proxy(args, judge_factory=make_judge):
    pairs = discover_corpus_pairs(REPORT_DIRS, args.limit)
    dims = args.dims
    print(f"[proxy] corpus pairs={len(pairs)} samples={args.samples} "
          f"dims={','.join(dims)}")
    if args.dry_run:
        print(f"[proxy] --dry-run: {len(pairs)} corpus pairs x {args.samples} "
              f"samples x {len(dims)} dim(s) would be judged (no judge calls).")
        return 0
    if not pairs:
        print("[proxy] no corpus report pairs found; nothing to measure.")
        return 0

    try:
        judge, iface = judge_factory()
    except JudgeUnavailable as e:
        print(f"[proxy] ERROR: {e}", file=sys.stderr)
        return 2
    print(f"[proxy] judge interface: {iface}")

    # Self-consistency: repeat the SAME pair `samples` times per dim.
    sc_agreements = []   # fraction of modal verdict per (pair, dim)
    for row in pairs:
        intent = load_task_intent(row["task_id"], TASK_DIR)
        ans_a = load_report_text(row["path_a"])
        ans_b = load_report_text(row["path_b"])
        for d in dims:
            verdicts = [judge(d, intent, row["agent_a"], ans_a,
                              row["agent_b"], ans_b)
                        for _ in range(max(1, args.samples))]
            modal = statistics.mode(verdicts) if verdicts else "tie"
            agree = verdicts.count(modal) / len(verdicts) if verdicts else float("nan")
            sc_agreements.append(agree)
    self_consistency = (sum(sc_agreements) / len(sc_agreements)
                        if sc_agreements else float("nan"))

    # Inter-judge agreement across families, if two are configured.
    fams = detect_judge_families()
    inter_note = ""
    inter_agree = float("nan")
    if len(fams) >= 2:
        import os
        (_, ov_a), (_, ov_b) = fams[0], fams[1]
        agreements = []
        for row in pairs:
            intent = load_task_intent(row["task_id"], TASK_DIR)
            ans_a = load_report_text(row["path_a"])
            ans_b = load_report_text(row["path_b"])
            for d in dims:
                old = {k: os.environ.get(k) for k in set(ov_a) | set(ov_b)}
                try:
                    os.environ.update({k: str(v) for k, v in ov_a.items()})
                    ja = judge(d, intent, row["agent_a"], ans_a,
                               row["agent_b"], ans_b)
                    for k, v in ov_b.items():
                        os.environ[k] = str(v)
                    jb = judge(d, intent, row["agent_a"], ans_a,
                               row["agent_b"], ans_b)
                finally:
                    for k, v in old.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v
                agreements.append(1.0 if ja == jb else 0.0)
        inter_agree = (sum(agreements) / len(agreements)
                       if agreements else float("nan"))
        inter_note = f"two families configured: {fams[0][0]} vs {fams[1][0]}"
    else:
        only = fams[0][0] if fams else "(none configured)"
        inter_note = (f"only one judge family configured ({only}); "
                      "inter-judge agreement not measurable. Set "
                      "JUDGE_MODEL_SECONDARY to enable.")

    _print_proxy_summary(self_consistency, inter_agree, inter_note,
                         len(pairs), args.samples, iface)
    return 0


def _print_proxy_summary(self_consistency, inter_agree, inter_note,
                         n_pairs, samples, iface):
    sc = "nan" if self_consistency != self_consistency else f"{self_consistency:.3f}"
    ia = "nan" if inter_agree != inter_agree else f"{inter_agree:.3f}"
    print("[proxy] === offline proxy metrics ===")
    print(f"[proxy] judge interface     : {iface}")
    print(f"[proxy] corpus pairs        : {n_pairs}")
    print(f"[proxy] samples per pair    : {samples}")
    print(f"[proxy] self-consistency    : {sc}  "
          "(mean fraction of modal verdict across repeated samples)")
    print(f"[proxy] inter-judge agreement: {ia}  ({inter_note})")
    print("[proxy] NOTE: these proxies are NECESSARY BUT NOT SUFFICIENT for "
          "human alignment. High self-consistency or inter-judge agreement "
          "means the judge is stable, NOT that it agrees with humans. Collect "
          "human labels in data/human_prefs/ and run the default mode for the "
          "real alignment measurement.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_dims(s: str) -> list[str]:
    out = []
    for tok in (s or "").split(","):
        tok = tok.strip().lower()
        if tok and tok in ALL_DIMS and tok not in out:
            out.append(tok)
    return out or list(DEFAULT_DIMS)


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="validate_judge_alignment.py",
        description="Measure LLM-judge vs human alignment per dimension.",
    )
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap the number of pairs (cheap smoke run). 0 = all.")
    ap.add_argument("--dims", type=_parse_dims, default=list(DEFAULT_DIMS),
                    help="Comma-separated dims to score (subset of "
                         f"{','.join(ALL_DIMS)}). Default: {','.join(DEFAULT_DIMS)}.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the work list and print counts without "
                         "calling the judge.")
    ap.add_argument("--proxy", action="store_true",
                    help="Offline proxy mode: report judge self-consistency "
                         "and inter-judge agreement on corpus pairs (no human "
                         "labels required).")
    ap.add_argument("--samples", type=int, default=3,
                    help="Proxy mode only: repeated judge samples per pair "
                         "for self-consistency. Default 3.")
    return ap


def main(argv=None):
    args = build_argparser().parse_args(argv)
    if args.proxy:
        return run_proxy(args)
    return run_alignment(args)


if __name__ == "__main__":
    raise SystemExit(main())
