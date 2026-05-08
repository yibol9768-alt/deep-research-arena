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
DEFAULT_TIE_EPS = 0.005  # composites within this → draw. Suitable for V2 truthful
# scale where reach=0 collapses many agents to identical 0; loose ties (eps=0.02)
# would let those zero-cluster agents draw with each other instead of being
# decided arbitrarily by the order battles are processed.
# NOTE: build_deep_leaderboard intentionally passes tie_eps=0.005; if you call
# arena from a different surface and your composite is on a wider scale, raise
# it to ~0.02. Past audits flagged this as too tight; we keep it as the V2
# default and document it here.
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


def _run_elo(
    battles: list[tuple[str, str, float]],
    agents: set[str],
    k: float,
    passes: int,
    seed: int,
) -> dict[str, dict]:
    """Multi-pass Elo averaging over a fixed list of (a, b, score_a) battles."""
    if not battles:
        return {}
    rng = random.Random(seed)
    elos_sum: dict[str, float] = defaultdict(float)
    rows_last: dict[str, EloRow] = {}
    for _ in range(passes):
        order = list(battles)
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
        out[a] = {
            "elo":       round(elos_sum[a] / passes, 1),
            "wins":      r.wins,
            "losses":    r.losses,
            "draws":     r.draws,
            "n_battles": r.n_battles,
        }
    return out


def compute_elo(
    records: list[dict],
    *,
    k: float = DEFAULT_K,
    tie_eps: float = DEFAULT_TIE_EPS,
    passes: int = DEFAULT_PASSES,
    seed: int = 42,
) -> dict[str, dict]:
    """Composite-proxy Elo: synthesise battles from composite scores.

    Backward-compatible. For true pairwise-judge Elo, use
    `compute_elo_from_battles`.
    """
    recs = [Record(**r) for r in records]
    by_task: dict[str, list[Record]] = defaultdict(list)
    for r in recs:
        by_task[r.task_id].append(r)
    all_battles: list[tuple[str, str, float]] = []
    for task_id, task_recs in by_task.items():
        all_battles.extend(_battles_for_task(task_recs, tie_eps))
    agents = {r.agent for r in recs}
    return _run_elo(all_battles, agents, k, passes, seed)


def compute_elo_from_battles(
    battles: list[dict],
    *,
    k: float = DEFAULT_K,
    passes: int = DEFAULT_PASSES,
    seed: int = 42,
) -> dict[str, dict]:
    """Elo from real pairwise-judge battle outcomes.

    `battles` items accept any of these shapes (keys are auto-detected):

        {"a1": ..., "a2": ..., "agent_winner": "a1"|"a2"|"tie"}
        {"agent_a": ..., "agent_b": ..., "winner": "a"|"b"|"tie"}
        {"a": ..., "b": ..., "score_a": 1.0|0.5|0.0}

    Returns {agent: {elo, wins, losses, draws, n_battles}}.
    """
    normalised: list[tuple[str, str, float]] = []
    agents: set[str] = set()
    for raw in battles:
        a, b, sa = _normalise_battle(raw)
        if a is None or b is None:
            continue
        normalised.append((a, b, sa))
        agents.add(a); agents.add(b)
    return _run_elo(normalised, agents, k, passes, seed)


def compute_elo_with_ci(
    battles: list[dict],
    *,
    k: float = DEFAULT_K,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict[str, dict]:
    """Bootstrap Elo confidence intervals over pairwise-battle outcomes.

    Chatbot Arena (Zheng et al. 2023) and Arena-Hard-Auto both report
    bootstrap 95% CIs on Elo. Without this, two agents whose true
    strength differs by < 1 CI-half-width can't be statistically
    distinguished. The peer-review audit flagged this as a P1 fix.

    We resample the battle list with replacement `n_resamples` times,
    run single-pass Elo each time, and report per-agent percentile CIs.
    """
    normalised: list[tuple[str, str, float]] = []
    agents: set[str] = set()
    for raw in battles:
        a, b, sa = _normalise_battle(raw)
        if a is None or b is None:
            continue
        normalised.append((a, b, sa))
        agents.add(a); agents.add(b)

    if not normalised:
        return {}

    import statistics
    rng = random.Random(seed)
    all_elos: dict[str, list[float]] = {a: [] for a in agents}

    for _ in range(n_resamples):
        resampled = [normalised[rng.randrange(len(normalised))]
                     for _ in range(len(normalised))]
        rows = {a: EloRow(agent=a) for a in agents}
        rng.shuffle(resampled)
        for a, b, sa in resampled:
            ra, rb = rows[a], rows[b]
            ra_elo, rb_elo = ra.elo, rb.elo
            ra.update(sa, rb_elo, k)
            rb.update(1.0 - sa, ra_elo, k)
        for a, row in rows.items():
            all_elos[a].append(row.elo)

    alpha = (1 - confidence) / 2
    q_lo = alpha
    q_hi = 1 - alpha

    def _pct(lst: list[float], q: float) -> float:
        if not lst:
            return START_RATING
        sl = sorted(lst)
        idx = min(len(sl) - 1, max(0, int(q * len(sl))))
        return sl[idx]

    # Also compute the point-estimate Elo (full sample, no resampling)
    point = _run_elo(normalised, agents, k, passes=DEFAULT_PASSES, seed=seed)

    out: dict[str, dict] = {}
    for a in agents:
        elos = all_elos[a]
        out[a] = {
            "elo":      point.get(a, {}).get("elo", START_RATING),
            "elo_mean": round(statistics.fmean(elos), 1) if elos else START_RATING,
            "elo_lo":   round(_pct(elos, q_lo), 1),
            "elo_hi":   round(_pct(elos, q_hi), 1),
            "elo_half_width": round((_pct(elos, q_hi) - _pct(elos, q_lo)) / 2, 1),
            "n_resamples":   n_resamples,
            "confidence":    confidence,
            "n_battles":     point.get(a, {}).get("n_battles", 0),
            "wins":          point.get(a, {}).get("wins", 0),
            "losses":        point.get(a, {}).get("losses", 0),
            "draws":         point.get(a, {}).get("draws", 0),
        }
    return out


def rank_significance_test(
    battles: list[dict],
    *,
    n_permutations: int = 1000,
    k: float = DEFAULT_K,
    seed: int = 42,
) -> dict:
    """Permutation test: how much of the observed Elo ordering survives
    when we randomly shuffle battle outcomes? Returns p-value per
    adjacent rank pair (probability the null could produce the same
    gap or larger).
    """
    normalised: list[tuple[str, str, float]] = []
    agents: set[str] = set()
    for raw in battles:
        a, b, sa = _normalise_battle(raw)
        if a is None or b is None:
            continue
        normalised.append((a, b, sa))
        agents.add(a); agents.add(b)
    if not normalised:
        return {}

    point = _run_elo(normalised, agents, k, passes=DEFAULT_PASSES, seed=seed)
    ordered = sorted(point.items(), key=lambda kv: -kv[1]["elo"])
    observed_gaps = [
        (ordered[i][0], ordered[i+1][0],
         point[ordered[i][0]]["elo"] - point[ordered[i+1][0]]["elo"])
        for i in range(len(ordered) - 1)
    ]

    rng = random.Random(seed)
    bigger_counts = {(a, b): 0 for a, b, _ in observed_gaps}

    # Permutation null: re-shuffle the *observed* outcome labels across
    # the same battle pairs. Old code drew uniformly from {1, 0, 0.5},
    # which forces 33% draws regardless of the empirical draw rate, so
    # the null was over-disperse and inflated p-values for closely-
    # ranked agents. Using a label-shuffle keeps the outcome marginals
    # exactly equal to the data.
    obs_outcomes = [s for (_, _, s) in normalised]

    for _ in range(n_permutations):
        rng.shuffle(obs_outcomes)
        shuffled = [
            (a, b, obs_outcomes[i])
            for i, (a, b, _) in enumerate(normalised)
        ]
        perm_rows = _run_elo(shuffled, agents, k, passes=1, seed=rng.randint(0, 1 << 30))
        for (a, b, obs_gap) in observed_gaps:
            null_gap = perm_rows.get(a, {}).get("elo", 0) - perm_rows.get(b, {}).get("elo", 0)
            if abs(null_gap) >= abs(obs_gap):
                bigger_counts[(a, b)] += 1

    return {
        "ordered": [a for a, _ in ordered],
        "adjacent_pairs": [
            {
                "higher":   a,
                "lower":    b,
                "gap":      round(gap, 1),
                "p_value":  round(bigger_counts[(a, b)] / n_permutations, 4),
                "significant": bigger_counts[(a, b)] / n_permutations < 0.05,
            }
            for (a, b, gap) in observed_gaps
        ],
    }


def render_elo_table_with_ci(elos_ci: dict[str, dict]) -> str:
    """Return a markdown leaderboard including 95% bootstrap CI."""
    lines = ["| Rank | Agent | Elo | 95% CI | W | L | D | Battles |",
             "|---:|---|---:|---|---:|---:|---:|---:|"]
    ordered = sorted(elos_ci.items(), key=lambda kv: -kv[1]["elo"])
    for i, (a, s) in enumerate(ordered, 1):
        lines.append(
            f"| {i} | {a} | **{s['elo']:.1f}** | "
            f"[{s['elo_lo']:.0f}, {s['elo_hi']:.0f}] ±{s['elo_half_width']:.0f} | "
            f"{s['wins']} | {s['losses']} | {s['draws']} | {s['n_battles']} |"
        )
    return "\n".join(lines)


def compute_elo_per_judge(
    battles: list[dict],
    *,
    judge_field: str = "judge_model",
    k: float = DEFAULT_K,
    passes: int = DEFAULT_PASSES,
    seed: int = 42,
) -> dict[str, dict[str, dict]]:
    """Compute Elo separately per judge to measure judge-agreement.

    Returns {judge_name: {agent: {elo, ...}}}. A battle missing `judge_field`
    goes into the key "unknown".
    """
    by_judge: dict[str, list[dict]] = defaultdict(list)
    for b in battles:
        j = b.get(judge_field) or "unknown"
        by_judge[j].append(b)
    return {j: compute_elo_from_battles(blist, k=k, passes=passes, seed=seed)
            for j, blist in by_judge.items()}


def _normalise_battle(raw: dict) -> tuple[str | None, str | None, float]:
    """Return (agent_a, agent_b, score_a) in canonical form."""
    # Shape 1: a1/a2 + agent_winner
    if "a1" in raw and "a2" in raw:
        a, b = raw["a1"], raw["a2"]
        w = raw.get("agent_winner", raw.get("winner", "tie"))
        if w == a or w == "a1" or w == "a":
            sa = 1.0
        elif w == b or w == "a2" or w == "b":
            sa = 0.0
        else:
            sa = 0.5
        return a, b, sa
    # Shape 2: agent_a/agent_b + winner={"a","b","tie"}
    if "agent_a" in raw and "agent_b" in raw:
        a, b = raw["agent_a"], raw["agent_b"]
        w = (raw.get("winner") or "tie").lower()
        sa = 1.0 if w == "a" else 0.0 if w == "b" else 0.5
        return a, b, sa
    # Shape 3: a/b + explicit score_a
    if "a" in raw and "b" in raw and "score_a" in raw:
        return raw["a"], raw["b"], float(raw["score_a"])
    return None, None, 0.5


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
