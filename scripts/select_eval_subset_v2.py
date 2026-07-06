#!/usr/bin/env python3
"""Select the v2 small evaluation subset (eval_small_v2), properly.

Replaces the v1 rl_small selection (scripts/select_rl_subset.py), which was
battle/Elo-based and selected on the retired v1 task set. The v2 headline is
the decidable truth score, so subset quality means: ranking agents by macro
truth over the subset reproduces the full-board ranking.

Two modes:

--provisional  (no run data needed; TODAY's mode)
    Deterministic stratified pick of one task per tri-source cluster
    (13 tasks): maximize archetype diversity, prefer tasks carrying
    adjudicated gold contradictions (so the semi-decidable axis is
    exercised) and richer spec contracts. Ships with provisional=true and
    is meant for smoke runs and cheap iteration only; it claims NO
    replication power because no run data exists to validate it.

--board <truth_board.json>  (after the #39 full run; the REAL mode)
    Greedy forward selection maximizing Spearman(subset macro-truth
    ranking, full-board ranking), with the methodological hardening the
    v1 version lacked:
      * held-out validation: repeated agent splits, subset selected on
        the selection half only, rho reported on the held-out half;
      * task bootstrap CI on the final subset's rho;
      * hard cluster-coverage constraint (every cluster represented)
        unless --no-cluster-constraint.
    Only a manifest whose holdout_rho_mean clears --target-rho should be
    quoted anywhere (the paper appendix included).

Output: data/tasks/deep_research/eval_small_v2/manifest.json
Self-test: --demo (synthetic board; asserts selection + holdout machinery).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KEYS = REPO / "data/golden/answer_keys"
OUT_DIR = REPO / "data/tasks/deep_research/eval_small_v2"

ARCHETYPE_ALIASES = {"durability/BIFL": "durability-bifl",
                     "evolution/explainer": "evolution-explainer"}


# ---------------------------------------------------------------------------
# shared
# ---------------------------------------------------------------------------

def load_task_meta() -> dict[str, dict]:
    meta = {}
    for p in sorted(KEYS.glob("dr_cross_deep_*.json")):
        k = json.loads(p.read_text())
        md = k.get("metadata", {})
        arch = md.get("archetype", "")
        meta[k["task_id"]] = {
            "cluster": md.get("cluster"),
            "archetype": ARCHETYPE_ALIASES.get(arch, arch),
            "n_gold_contradictions": len(k.get("gold_contradictions") or []),
            "n_specs": len(k.get("spec_requirements") or []),
        }
    return meta


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: -v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k2 in range(i, j + 1):
                r[order[k2]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def write_manifest(doc: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "manifest.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(doc['tasks'])} tasks, mode={doc['mode']})")
    return out


# ---------------------------------------------------------------------------
# provisional mode (no run data)
# ---------------------------------------------------------------------------

def select_provisional(meta: dict[str, dict]) -> dict:
    by_cluster: dict[str, list[str]] = {}
    for tid, m in meta.items():
        by_cluster.setdefault(m["cluster"], []).append(tid)
    chosen, arch_seen = [], set()
    # deterministic cluster order; inside a cluster prefer an archetype not
    # yet covered, then gold-contradiction presence, then spec richness
    for cl in sorted(by_cluster):
        def rank_key(tid):
            m = meta[tid]
            return (m["archetype"] in arch_seen,          # new archetype first
                    -min(m["n_gold_contradictions"], 1),  # has gold first
                    -m["n_specs"], tid)
        pick = sorted(by_cluster[cl], key=rank_key)[0]
        chosen.append(pick)
        arch_seen.add(meta[pick]["archetype"])
    return {
        "subset": "eval_small_v2",
        "mode": "provisional-stratified",
        "provisional": True,
        "warning": ("selected WITHOUT run data (one task per cluster, "
                    "archetype-diverse, gold-contradiction preferred); "
                    "carries NO validated replication power; re-select with "
                    "--board after the v2 full run and only then quote it"),
        "tasks": sorted(chosen),
        "n_tasks": len(chosen),
        "coverage": {
            "clusters": len(by_cluster),
            "archetypes": len({meta[t]["archetype"] for t in chosen}),
            "tasks_with_gold_contradictions":
                sum(1 for t in chosen if meta[t]["n_gold_contradictions"]),
        },
        "selected_from": "data/golden/answer_keys metadata (no scores)",
    }


# ---------------------------------------------------------------------------
# board mode (after the full run)
# ---------------------------------------------------------------------------

def load_board(path: Path) -> dict[str, dict[str, float]]:
    """agent -> {task_id -> truth} from a build_truth_board.py output."""
    doc = json.loads(path.read_text())
    rows = doc.get("agents") or doc.get("rows") or doc
    out = {}
    for name, rec in (rows.items() if isinstance(rows, dict) else
                      ((r["agent"], r) for r in rows)):
        pt = rec.get("per_task") or {}
        out[name] = {t: d["truth"] for t, d in pt.items()}
    return out


def macro(agent_tasks: dict[str, float], tasks) -> float:
    vals = [agent_tasks[t] for t in tasks if t in agent_tasks]
    return st.mean(vals) if vals else 0.0


def greedy_select(board, agents, tasks, ref_rank, target_rho, max_size,
                  meta=None, cluster_constraint=True):
    chosen: list[str] = []
    need_clusters = ({meta[t]["cluster"] for t in tasks if t in meta}
                     if (cluster_constraint and meta) else set())
    while len(chosen) < max_size:
        best_t, best_rho = None, -2.0
        have_cl = {meta[t]["cluster"] for t in chosen} if meta else set()
        missing = need_clusters - have_cl
        for t in tasks:
            if t in chosen:
                continue
            # while clusters are missing, only consider tasks that add one
            if missing and meta and meta[t]["cluster"] not in missing:
                continue
            cand = chosen + [t]
            rho = spearman([macro(board[a], cand) for a in agents], ref_rank)
            if rho > best_rho:
                best_t, best_rho = t, rho
        if best_t is None:
            break
        chosen.append(best_t)
        if best_rho >= target_rho and not (need_clusters -
                                           ({meta[t]["cluster"] for t in chosen}
                                            if meta else set())):
            return chosen, best_rho
    final = spearman([macro(board[a], chosen) for a in agents], ref_rank)
    return chosen, final


def select_from_board(board_path: Path, meta, target_rho, max_size,
                      n_splits, n_boot, seed, cluster_constraint):
    board = load_board(board_path)
    agents = sorted(board)
    if len(agents) < 4:
        raise SystemExit(f"only {len(agents)} agents on the board; "
                         "holdout validation needs at least 4")
    tasks = sorted(set.intersection(*(set(v) for v in board.values())))
    ref = [macro(board[a], tasks) for a in agents]

    # full-data selection (the shipped subset)
    chosen, rho_insample = greedy_select(
        board, agents, tasks, ref, target_rho, max_size, meta,
        cluster_constraint)

    # held-out validation: select on half the agents, score on the rest
    rng = random.Random(seed)
    holdout_rhos = []
    for _ in range(n_splits):
        pool = agents[:]
        rng.shuffle(pool)
        half = len(pool) // 2
        sel_a, held_a = pool[:half], pool[half:]
        ref_sel = [macro(board[a], tasks) for a in sel_a]
        sub, _ = greedy_select(board, sel_a, tasks, ref_sel, target_rho,
                               max_size, meta, cluster_constraint)
        held_ref = [macro(board[a], tasks) for a in held_a]
        held_sub = [macro(board[a], sub) for a in held_a]
        holdout_rhos.append(spearman(held_sub, held_ref))

    # task bootstrap on the shipped subset
    boot = []
    for _ in range(n_boot):
        samp = [chosen[rng.randrange(len(chosen))] for _ in chosen]
        boot.append(spearman([macro(board[a], samp) for a in agents], ref))
    boot.sort()
    lo, hi = boot[int(0.025 * n_boot)], boot[int(0.975 * n_boot) - 1]

    return {
        "subset": "eval_small_v2",
        "mode": "board-greedy",
        "provisional": False,
        "tasks": sorted(chosen),
        "n_tasks": len(chosen),
        "selection": {
            "board": str(board_path),
            "board_sha256": hashlib.sha256(
                board_path.read_bytes()).hexdigest()[:16],
            "n_agents": len(agents),
            "n_tasks_full": len(tasks),
            "target_rho": target_rho,
            "rho_insample": round(rho_insample, 4),
        },
        "validation": {
            "holdout_splits": n_splits,
            "holdout_rho_mean": round(st.mean(holdout_rhos), 4),
            "holdout_rho_min": round(min(holdout_rhos), 4),
            "task_bootstrap_rho_ci95": [round(lo, 4), round(hi, 4)],
            "note": ("holdout: subset re-selected on half the agents, rho "
                     "scored on the unseen half; quote holdout_rho_mean, "
                     "never rho_insample"),
        },
        "coverage": {
            "clusters": len({meta[t]["cluster"] for t in chosen if t in meta}),
        },
    }


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------

def run_demo() -> int:
    rng = random.Random(7)
    agents = [f"ag{i}" for i in range(8)]
    skill = {a: i / 8 for i, a in enumerate(agents)}
    tasks = [f"t{i:03d}" for i in range(60)]
    board = {a: {t: max(0.0, min(1.0, skill[a] + rng.gauss(0, 0.08)))
                 for t in tasks} for a in agents}
    tmp = Path("/tmp") / "demo_truth_board.json"
    tmp.write_text(json.dumps(
        {"agents": {a: {"per_task": {t: {"truth": v} for t, v in pt.items()}}
                    for a, pt in board.items()}}))
    meta = {t: {"cluster": f"c{int(t[1:]) % 5}", "archetype": "x",
                "n_gold_contradictions": 0, "n_specs": 1} for t in tasks}
    doc = select_from_board(tmp, meta, target_rho=0.95, max_size=15,
                            n_splits=6, n_boot=200, seed=1,
                            cluster_constraint=True)
    checks = [
        ("selection reaches target in-sample",
         doc["selection"]["rho_insample"] >= 0.95),
        ("subset much smaller than full", doc["n_tasks"] <= 15),
        ("all 5 demo clusters covered", doc["coverage"]["clusters"] == 5),
        ("holdout reported and sane",
         -1 <= doc["validation"]["holdout_rho_min"]
         <= doc["validation"]["holdout_rho_mean"] <= 1),
        ("holdout positive on clean synthetic signal",
         doc["validation"]["holdout_rho_mean"] > 0.8),
    ]
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--provisional", action="store_true")
    ap.add_argument("--board", help="truth board JSON from build_truth_board.py")
    ap.add_argument("--target-rho", type=float, default=0.95)
    ap.add_argument("--max-size", type=int, default=15)
    ap.add_argument("--holdout-splits", type=int, default=20)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-cluster-constraint", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.demo:
        return run_demo()
    meta = load_task_meta()
    if args.provisional:
        write_manifest(select_provisional(meta))
        return 0
    if args.board:
        doc = select_from_board(Path(args.board), meta, args.target_rho,
                                args.max_size, args.holdout_splits,
                                args.bootstrap, args.seed,
                                not args.no_cluster_constraint)
        write_manifest(doc)
        if doc["validation"]["holdout_rho_mean"] < args.target_rho:
            print(f"warning: holdout rho "
                  f"{doc['validation']['holdout_rho_mean']} below target "
                  f"{args.target_rho}; do not quote this subset as a "
                  "validated replication set")
        return 0
    ap.error("pick a mode: --provisional | --board <file> | --demo")


if __name__ == "__main__":
    sys.exit(main())
