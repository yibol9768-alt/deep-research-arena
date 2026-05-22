#!/usr/bin/env python3
"""Compute and report Arena-Hard-style top-player separability.

Reads:
    data/results/deep_v3/leaderboard_deep.json   (preferred)
    data/results/deep_v2/leaderboard_deep.json   (fallback)

Calls `src.scoring.arena.compute_separability` and writes:
    docs/SEPARABILITY_REPORT.md   (also echoed to stdout)

Falls back to a synthetic mini-leaderboard when no real data file is
found, logs a WARNING to stderr, and still produces the report (so this
script never silently no-ops in CI).

Usage:
    python scripts/report_separability.py
        [--leaderboard data/results/deep_v3/leaderboard_deep.json]
        [--out docs/SEPARABILITY_REPORT.md]
        [--target 65.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.arena import compute_separability  # noqa: E402

DEFAULT_LB_PATHS = [
    ROOT / "data" / "results" / "deep_v3" / "leaderboard_deep.json",
    ROOT / "data" / "results" / "deep_v2" / "leaderboard_deep.json",
]
DEFAULT_OUT = ROOT / "docs" / "SEPARABILITY_REPORT.md"
TARGET_DEFAULT = 65.0


# -----------------------------------------------------------------------------
# Synthetic fallback — only used when no real leaderboard exists.
# -----------------------------------------------------------------------------

def _synthetic_leaderboard() -> tuple[dict, str]:
    """Return a small mock CI table matching the documented top-cluster.

    Numbers come from `ELO_PLAN_2026-04-27.md` section "2026-04-28 30-task
    pipeline". Use this only as a fallback so the script always produces
    output.
    """
    elo_v2_ci = {
        "camel-ai":        {"elo": 1274.2, "elo_lo": 1202, "elo_hi": 1346},
        "smolagents":      {"elo": 1155.1, "elo_lo": 1084, "elo_hi": 1226},
        "gpt-researcher":  {"elo":  863.8, "elo_lo":  826, "elo_hi":  902},
        "langchain-odr":   {"elo":  853.7, "elo_lo":  817, "elo_hi":  891},
        "storm":           {"elo":  853.3, "elo_lo":  817, "elo_hi":  890},
    }
    return ({"elo_v2_ci": elo_v2_ci}, "synthetic-30task-snapshot")


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------

def _load_leaderboard(explicit_path: Path | None) -> tuple[dict, str]:
    candidates = [explicit_path] if explicit_path else DEFAULT_LB_PATHS
    for p in candidates:
        if p is None:
            continue
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")), str(p)
            except Exception as e:
                print(f"[warn] failed to parse {p}: {e}", file=sys.stderr)
    print(
        "[warn] no leaderboard found — falling back to synthetic snapshot. "
        "Real numbers will diverge.",
        file=sys.stderr,
    )
    return _synthetic_leaderboard()


def _pick_elo_table(leaderboard: dict) -> tuple[dict, str]:
    """Prefer v2 truthful CI table; fall back to v1 or v2 point estimate."""
    for key in ("elo_v2_ci", "elo_v2", "elo_v1_ci", "elo_v1"):
        if key in leaderboard and leaderboard[key]:
            return leaderboard[key], key
    return {}, "<none>"


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------

def _render_markdown(
    *,
    result: dict,
    table_key: str,
    source: str,
    target: float,
) -> str:
    pct = result["separability_pct"]
    delta_target = pct - target
    pass_mark = "PASS" if pct >= target else "BELOW TARGET"

    lines = []
    lines.append("# Top-Player Separability Report")
    lines.append("")
    lines.append(f"- **Source**: `{source}`")
    lines.append(f"- **Elo table key**: `{table_key}`")
    lines.append(f"- **Pairs evaluated**: {result['n_pairs']}")
    lines.append(
        f"- **Non-overlapping CI pairs**: {result['n_non_overlapping']}"
    )
    lines.append(
        f"- **Separability**: **{pct:.2f}%** "
        f"(target >= {target:.1f}% — {pass_mark}, "
        f"{delta_target:+.2f} pp vs target)"
    )
    lines.append("")
    lines.append("## Reference points")
    lines.append("")
    lines.append("| Benchmark | Separability % |")
    lines.append("|---|---:|")
    lines.append("| MT-Bench (Zheng et al. 2023) | 22.6 |")
    lines.append("| Chatbot Arena (general) | ~70 |")
    lines.append("| Arena-Hard-Auto (Li et al. 2024) | 87.4 |")
    lines.append(f"| **Deep Research Arena (this run)** | **{pct:.2f}** |")
    lines.append(f"| **Target after v2 + densify** | **>= {target:.1f}** |")
    lines.append("")
    lines.append("## Per-pair CI overlap")
    lines.append("")
    lines.append(
        "Sorted by |Elo gap| descending. `overlap=False` rows are the "
        "separable pairs — those that survive bootstrap noise."
    )
    lines.append("")
    lines.append(
        "| Pair | A Elo | A CI | B Elo | B CI | |gap| | Overlap? |"
    )
    lines.append("|---|---:|---|---:|---|---:|:---:|")
    for row in result["pair_breakdown"]:
        a_ci = f"[{row['a_ci'][0]}, {row['a_ci'][1]}]"
        b_ci = f"[{row['b_ci'][0]}, {row['b_ci'][1]}]"
        overlap_mark = "yes" if row["ci_overlap"] else "**no**"
        lines.append(
            f"| {row['a']} vs {row['b']} | "
            f"{row['a_elo']:.1f} | {a_ci} | "
            f"{row['b_elo']:.1f} | {b_ci} | "
            f"{row['gap_elo']:.1f} | {overlap_mark} |"
        )
    lines.append("")
    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "An `overlap=no` row means the bootstrap 95% Elo CIs of the two "
        "agents do not overlap, so the benchmark distinguishes them with "
        "high confidence. The separability % is the fraction of all C(n, 2) "
        "agent pairs in that state."
    )
    lines.append("")
    lines.append(
        "The three levers we are pulling to lift this number:"
    )
    lines.append("")
    lines.append(
        "1. **Adversarial tasks** (v2 — 20 specs in "
        "`configs/deep_topics/V2_ADVERSARIAL_TASKS.json`) — splits the top "
        "cluster by stressing depth / rigor / coverage individually."
    )
    lines.append(
        "2. **Top-pair densification** "
        "(`scripts/run_pairwise_battles.py --strategy top-pair-densify`) — "
        "shrinks bootstrap CIs by adding battles where the gap is smallest."
    )
    lines.append(
        "3. **Composite dynamic-range widening** (Workstream A's v3 "
        "composite) — undoes the saturation that pins top agents to the "
        "same per-pillar Elo."
    )
    lines.append("")
    lines.append(
        "See `docs/SEPARABILITY_PLAN.md` for the staged validation protocol."
    )
    lines.append("")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leaderboard", default="",
                    help="Path to leaderboard JSON (default: search "
                         "deep_v3 then deep_v2).")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="Output markdown path (default: docs/SEPARABILITY_REPORT.md).")
    ap.add_argument("--target", type=float, default=TARGET_DEFAULT,
                    help="Target separability percentage (default: 65.0).")
    args = ap.parse_args()

    explicit = Path(args.leaderboard) if args.leaderboard else None
    leaderboard, source = _load_leaderboard(explicit)
    elo_table, key = _pick_elo_table(leaderboard)
    if not elo_table:
        print("[error] leaderboard has no Elo table.", file=sys.stderr)
        return 2

    result = compute_separability(elo_table)
    md = _render_markdown(
        result=result, table_key=key, source=source, target=args.target,
    )

    print(md)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\n[ok] Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
