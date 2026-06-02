#!/usr/bin/env python3
"""DeepSeek-powered judge validity check.

We do not have human preference labels on disk yet (data/human_prefs is
empty). As an honest stand-in we measure whether the cheap PRODUCTION judge
(deepseek-v4-flash) agrees with a stronger REFERENCE judge (deepseek-v4-pro)
on real report pairs, per dimension, using the redesigned dimension-aware
pairwise judge. We also measure each judge's self-consistency.

This is a validity proxy, NOT human alignment. flash-vs-pro agreement shares
LLM biases, so high agreement is necessary but not sufficient for true human
alignment, which still needs human labels (pull from my5090 or collect fresh).

Run (after sourcing the judge backend):
    set -a; . /root/.config/dra/judge.env; set +a
    python3 scripts/judge_deepseek_alignment.py --limit 12 --dims depth,rigor,style,checklist
Writes docs/JUDGE_DEEPSEEK_ALIGNMENT.md.
"""

from __future__ import annotations

import argparse
import itertools
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring import pairwise_judge as pj

REPORTS_DIR = ROOT / "data" / "results" / "deep_reports"
OUT_MD = ROOT / "docs" / "JUDGE_DEEPSEEK_ALIGNMENT.md"
# Lite by default (project policy: use deepseek-v4-flash for everything).
# A stronger reference judge (deepseek-v4-pro) is opt-in via --reference-model;
# with the default, this measures cross-config consistency of the lite judge,
# which is a weaker validity signal than a stronger reference would give.
PRODUCTION_MODEL = "deepseek-v4-flash"
REFERENCE_MODEL = "deepseek-v4-flash"
ALL_DIMS = ["depth", "rigor", "style", "checklist"]


def _parse_name(path: Path) -> tuple[str, str] | None:
    # <agent>__<task_id>_matrix.md
    m = re.match(r"(.+?)__(.+?)_(matrix|smoke)\.md$", path.name)
    if not m:
        return None
    return m.group(1), m.group(2)


def _build_pairs(limit: int) -> list[dict]:
    by_task: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for p in sorted(REPORTS_DIR.glob("*.md")):
        parsed = _parse_name(p)
        if not parsed:
            continue
        agent, task_id = parsed
        by_task[task_id].append((agent, p))
    pairs: list[dict] = []
    for task_id, items in sorted(by_task.items()):
        for (a_agent, a_path), (b_agent, b_path) in itertools.combinations(items, 2):
            pairs.append({
                "task_id": task_id,
                "agent_a": a_agent, "path_a": a_path,
                "agent_b": b_agent, "path_b": b_path,
            })
    # Interleave across tasks so a small --limit still spans several tasks.
    pairs.sort(key=lambda d: (d["agent_a"], d["task_id"]))
    if limit and limit > 0:
        pairs = pairs[:limit]
    return pairs


def _verdict(model: str, intent: str, a_text: str, b_text: str, dim: str, n: int) -> str:
    r = pj.battle(
        task_intent=intent, agent_a="a", answer_a=a_text,
        agent_b="b", answer_b=b_text, dimension=dim,
        model=model, n_samples=n,
    )
    return r.get("winner", "tie")  # "a" | "b" | "tie"


def _cohen_kappa(labels_x: list[str], labels_y: list[str]) -> float | None:
    n = len(labels_x)
    if n == 0:
        return None
    cats = ["a", "b", "tie"]
    po = sum(1 for x, y in zip(labels_x, labels_y) if x == y) / n
    px = {c: labels_x.count(c) / n for c in cats}
    py = {c: labels_y.count(c) / n for c in cats}
    pe = sum(px[c] * py[c] for c in cats)
    if abs(1 - pe) < 1e-9:
        return 1.0 if abs(po - 1.0) < 1e-9 else 0.0
    return (po - pe) / (1 - pe)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=12, help="max report pairs (0 = all)")
    ap.add_argument("--dims", default="depth,rigor,style,checklist")
    ap.add_argument("--samples", type=int, default=2, help="debiased rounds per judge")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--production-model", default=PRODUCTION_MODEL,
                    help="judge under test (default lite deepseek-v4-flash)")
    ap.add_argument("--reference-model", default=REFERENCE_MODEL,
                    help="reference judge (default lite; pass deepseek-v4-pro to opt into "
                         "a stronger reference, which is slower and costlier)")
    args = ap.parse_args(argv)

    production_model = args.production_model
    reference_model = args.reference_model
    dims = [d.strip() for d in args.dims.split(",") if d.strip() in ALL_DIMS]
    pairs = _build_pairs(args.limit)
    print(f"[align] pairs={len(pairs)} dims={','.join(dims)} samples={args.samples} "
          f"production={production_model} reference={reference_model}", flush=True)
    if args.dry_run:
        for p in pairs:
            print(f"  {p['task_id']}: {p['agent_a']} vs {p['agent_b']}", flush=True)
        calls = len(pairs) * len(dims) * args.samples * 2 * 2
        print(f"[align] --dry-run: ~{calls} judge calls would be made.", flush=True)
        return 0

    if not os.environ.get("JUDGE_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        print("[align] ERROR: no judge backend configured. Source judge.env first.", flush=True)
        return 2

    intent = ("Compare options across the sandbox sources (shopping, forum, wiki) "
              "and produce a grounded comparative report.")
    per_dim: dict[str, dict[str, list[str]]] = {d: {"prod": [], "ref": []} for d in dims}
    rows: list[dict] = []
    for i, p in enumerate(pairs, 1):
        a_text = p["path_a"].read_text(encoding="utf-8", errors="ignore")
        b_text = p["path_b"].read_text(encoding="utf-8", errors="ignore")
        row = {"pair": f"{p['agent_a']} vs {p['agent_b']}", "task": p["task_id"]}
        for d in dims:
            ref = _verdict(reference_model, intent, a_text, b_text, d, args.samples)
            prod = _verdict(production_model, intent, a_text, b_text, d, args.samples)
            per_dim[d]["ref"].append(ref)
            per_dim[d]["prod"].append(prod)
            row[d] = f"{prod}/{ref}{'=' if prod == ref else 'x'}"
        rows.append(row)
        print(f"[align] {i}/{len(pairs)} {row['pair']} ({row['task']}): "
              + " ".join(f"{d}={row[d]}" for d in dims), flush=True)

    same_model = production_model == reference_model
    lines = ["# DeepSeek judge validity: production vs reference", ""]
    lines.append(f"- pairs: {len(pairs)} | dims: {', '.join(dims)} | rounds/judge: {args.samples}")
    lines.append(f"- production judge: `{production_model}` | reference judge: `{reference_model}`")
    lines.append("")
    if same_model:
        lines.append("Production and reference are the SAME model, so this measures the")
        lines.append("judge's cross-config CONSISTENCY, not agreement with a stronger judge.")
    else:
        lines.append("This is a VALIDITY PROXY (cheap judge tracks a stronger judge), NOT human")
        lines.append("alignment.")
    lines.append("True human kappa needs human labels (my5090 pull or fresh collection).")
    lines.append("")
    lines.append("## Per-dimension agreement (production vs reference)")
    lines.append("")
    lines.append("| dim | n | raw agreement | Cohen kappa |")
    lines.append("| --- | - | ------------- | ----------- |")
    overall_x: list[str] = []
    overall_y: list[str] = []
    for d in dims:
        x, y = per_dim[d]["prod"], per_dim[d]["ref"]
        overall_x += x
        overall_y += y
        n = len(x)
        raw = sum(1 for a, b in zip(x, y) if a == b) / n if n else 0.0
        k = _cohen_kappa(x, y)
        lines.append(f"| {d} | {n} | {raw:.2f} | {('%.3f' % k) if k is not None else 'n/a'} |")
    n_all = len(overall_x)
    raw_all = sum(1 for a, b in zip(overall_x, overall_y) if a == b) / n_all if n_all else 0.0
    k_all = _cohen_kappa(overall_x, overall_y)
    lines.append(f"| **overall** | {n_all} | {raw_all:.2f} | "
                 f"{('%.3f' % k_all) if k_all is not None else 'n/a'} |")
    lines.append("")
    lines.append("## Per-pair verdicts (production/reference, x = disagree)")
    lines.append("")
    lines.append("| pair | task | " + " | ".join(dims) + " |")
    lines.append("| ---- | ---- | " + " | ".join("---" for _ in dims) + " |")
    for r in rows:
        lines.append(f"| {r['pair']} | {r['task']} | " + " | ".join(r[d] for d in dims) + " |")
    lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[align] wrote {OUT_MD}", flush=True)
    print(f"[align] OVERALL raw={raw_all:.2f} kappa="
          f"{('%.3f' % k_all) if k_all is not None else 'n/a'} over n={n_all}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
