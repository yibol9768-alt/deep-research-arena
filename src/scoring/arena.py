"""Arena-style Elo rating from per-task composite scores.

Chatbot Arena (lmsys, 2023) style:
  - Each task yields a set of (agent, composite_score) records.
  - Within a task we emit all C(N,2) pairwise battles.
  - Winner = higher composite. |Δ| below `tie_eps` → draw.
  - Elo updated per battle with K-factor (default 32).
  - Final rating across many tasks = Elo after all battles processed in
    stable shuffled order (multiple passes to reduce seed effect).

Inputs:
  records = list of dicts, each:
      {"task_id": ..., "agent": ..., "composite": float}

Outputs:
  {agent: {"elo": float, "wins": int, "losses": int, "draws": int}}

Stability:
  - Run N_passes = 20 passes with shuffled battle order, average Elo.
  - The default K=32 is safe for small N (we typically have < 200
    battles across all agents).
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field


START_RATING = 1000.0
DEFAULT_K = 32.0
DEFAULT_TIE_EPS = 0.005  # composites within 0.005 → draw (tight: forces decisive battles)
DEFAULT_PASSES = 20


@dataclass
class Record:
    task_id: str
    agent: str
    composite: float


@dataclass
class EloRow:
    agent: str
    elo: float = START_RATING
    wins: int = 0
    losses: int = 0
    draws: int = 0
    n_battles: int = 0

    def expected(self, opp_elo: float) -> float:
        return 1.0 / (1.0 + 10 ** ((opp_elo - self.elo) / 400))

    def update(self, score: float, opp_elo: float, k: float = DEFAULT_K) -> None:
        exp = self.expected(opp_elo)
        self.elo += k * (score - exp)


def _battles_for_task(task_records: list[Record], tie_eps: float) -> list[tuple[str, str, float]]:
    """Emit all unordered pairs within a task. score = 1.0 / 0.5 / 0.0 for a."""
    out: list[tuple[str, str, float]] = []
    for i in range(len(task_records)):
        for j in range(i + 1, len(task_records)):
            a, b = task_records[i], task_records[j]
            diff = a.composite - b.composite
            if abs(diff) < tie_eps:
                out.append((a.agent, b.agent, 0.5))
            elif diff > 0:
                out.append((a.agent, b.agent, 1.0))
            else:
                out.append((a.agent, b.agent, 0.0))
    return out


def compute_elo(
    records: list[dict],
    *,
    k: float = DEFAULT_K,
    tie_eps: float = DEFAULT_TIE_EPS,
    passes: int = DEFAULT_PASSES,
    seed: int = 42,
) -> dict[str, dict]:
    """Compute Elo ratings. Returns per-agent dict with final rating."""
    recs = [Record(**r) for r in records]
    by_task: dict[str, list[Record]] = defaultdict(list)
    for r in recs:
        by_task[r.task_id].append(r)

    all_battles: list[tuple[str, str, float]] = []
    for task_id, task_recs in by_task.items():
        all_battles.extend(_battles_for_task(task_recs, tie_eps))

    if not all_battles:
        return {}

    rng = random.Random(seed)
    agents = {r.agent for r in recs}

    # Multi-pass: for each pass shuffle battles, average final elos.
    elos_sum: dict[str, float] = defaultdict(float)
    rows_last: dict[str, EloRow] = {}
    for p in range(passes):
        order = list(all_battles)
        rng.shuffle(order)
        rows = {a: EloRow(agent=a) for a in agents}
        for a, b, sa in order:
            ra, rb = rows[a], rows[b]
            ra_elo, rb_elo = ra.elo, rb.elo
            ra.update(sa, rb_elo, k)
            rb.update(1.0 - sa, ra_elo, k)
            ra.n_battles += 1
            rb.n_battles += 1
            if sa == 1.0:
                ra.wins += 1
                rb.losses += 1
            elif sa == 0.0:
                ra.losses += 1
                rb.wins += 1
            else:
                ra.draws += 1
                rb.draws += 1
        for a, row in rows.items():
            elos_sum[a] += row.elo
        rows_last = rows

    out: dict[str, dict] = {}
    for a in agents:
        r = rows_last[a]
        # Battle counts/W/L/D come from the final pass (same per pass)
        out[a] = {
            "elo":       round(elos_sum[a] / passes, 1),
            "wins":      r.wins,
            "losses":    r.losses,
            "draws":     r.draws,
            "n_battles": r.n_battles,
        }
    return out


def render_elo_table(elos: dict[str, dict]) -> str:
    """Return a markdown leaderboard (highest Elo first)."""
    lines = ["| Rank | Agent | Elo | W | L | D | Battles |",
             "|---:|---|---:|---:|---:|---:|---:|"]
    ordered = sorted(elos.items(), key=lambda kv: -kv[1]["elo"])
    for i, (a, s) in enumerate(ordered, 1):
        lines.append(f"| {i} | {a} | **{s['elo']:.1f}** | {s['wins']} | {s['losses']} | {s['draws']} | {s['n_battles']} |")
    return "\n".join(lines)


def per_pillar_elo(per_run_results: list[dict]) -> dict[str, dict[str, float]]:
    """Compute Elo per pillar. Each agent gets a row of {pillar: elo}.

    `per_run_results` items: {"task_id", "agent", "pillars": {pillar_name: score, ...}}
    """
    pillars = set()
    for r in per_run_results:
        pillars.update(r["pillars"].keys())

    out: dict[str, dict[str, float]] = {}
    for pillar in sorted(pillars):
        recs = [
            {"task_id": r["task_id"], "agent": r["agent"], "composite": r["pillars"].get(pillar, 0.0)}
            for r in per_run_results
        ]
        elos = compute_elo(recs)
        for agent, info in elos.items():
            out.setdefault(agent, {})[pillar] = info["elo"]
    return out


def render_per_pillar_table(per_pillar: dict[str, dict[str, float]]) -> str:
    if not per_pillar:
        return "_(no data)_"
    pillars = sorted({p for v in per_pillar.values() for p in v.keys()})
    header = ["| Agent |"] + [f" {p[:4]} |" for p in pillars]
    align = ["|---|"] + ["---:|"] * len(pillars)
    lines = ["".join(header), "".join(align)]
    for agent in sorted(per_pillar.keys()):
        row = [f"| {agent} |"]
        for p in pillars:
            v = per_pillar[agent].get(p)
            row.append(f" {v:.0f} |" if v is not None else " — |")
        lines.append("".join(row))
    return "\n".join(lines)
