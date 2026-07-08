import { loadMatrixSubset, type MatrixSubset, type MatrixAgentRow } from './load-matrix-subset'

// Arena v2 (uj_v1 protocol): every leaderboard entry is one harness x backbone
// run. Flattened from the matrix_subset snapshot at build time.

export interface ArenaEntry extends MatrixAgentRow {
  /** Unique key: `${id}__${backbone}` */
  key: string
  backbone: string
  /** Backbone-level jury reliability (Fleiss kappa) for context chips. */
  fleiss_kappa: number
  spearman_truth_vs_usefulness: number
}

export interface ArenaSnapshot {
  entries: ArenaEntry[]
  backbones: string[]
  judges: string[]
  arena_formula: string
  task_set: string
  protocol: string
  generated_at: string
  n_judge_records_total: number
  excluded_agents: string[]
  excluded_reason: string
  perBackbone: Record<string, { fleiss_kappa: number; spearman: number; n_clean_items: number; n_items: number }>
}

export { BACKBONE_SHORT, backboneShort } from '../backbones'

/** One harness aggregated across every backbone it ran on. */
export interface HarnessAgg {
  id: string
  runs: ArenaEntry[]
  /** Unweighted mean across backbones (each backbone counts once). */
  arena: number
  reach: number
  bt_elo: number
  winrate: number
  truth: number
  n_battles: number
}

/** One backbone LLM aggregated across every harness that ran on it. */
export interface BackboneAgg {
  backbone: string
  runs: ArenaEntry[]
  arena: number
  reach: number
  bt_elo: number
  winrate: number
  truth: number
  n_battles: number
  fleiss_kappa: number
  spearman: number
}

const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / Math.max(1, xs.length)

/** Harness view: one row per framework, averaged across backbones. */
export function harnessAggregates(snapshot: ArenaSnapshot): HarnessAgg[] {
  const byId = new Map<string, ArenaEntry[]>()
  for (const e of snapshot.entries) {
    const arr = byId.get(e.id) ?? []
    arr.push(e)
    byId.set(e.id, arr)
  }
  const out: HarnessAgg[] = []
  for (const [id, runs] of byId) {
    runs.sort((a, b) => b.arena - a.arena)
    out.push({
      id,
      runs,
      arena: mean(runs.map((r) => r.arena)),
      reach: mean(runs.map((r) => r.reach)),
      bt_elo: mean(runs.map((r) => r.bt_elo)),
      winrate: mean(runs.map((r) => r.winrate)),
      truth: mean(runs.map((r) => r.truth)),
      n_battles: runs.reduce((s, r) => s + r.n_battles, 0),
    })
  }
  return out.sort((a, b) => b.arena - a.arena || b.bt_elo - a.bt_elo)
}

/** Backbone view: one row per LLM, averaged across harnesses. */
export function backboneAggregates(snapshot: ArenaSnapshot): BackboneAgg[] {
  return snapshot.backbones
    .map((backbone) => {
      const runs = snapshot.entries.filter((e) => e.backbone === backbone).sort((a, b) => b.arena - a.arena)
      const bb = snapshot.perBackbone[backbone]
      return {
        backbone,
        runs,
        arena: mean(runs.map((r) => r.arena)),
        reach: mean(runs.map((r) => r.reach)),
        bt_elo: mean(runs.map((r) => r.bt_elo)),
        winrate: mean(runs.map((r) => r.winrate)),
        truth: mean(runs.map((r) => r.truth)),
        n_battles: runs.reduce((s, r) => s + r.n_battles, 0),
        fleiss_kappa: bb.fleiss_kappa,
        spearman: bb.spearman,
      }
    })
    .sort((a, b) => b.arena - a.arena)
}

export function loadArenaV2(): ArenaSnapshot | null {
  const raw: MatrixSubset | null = loadMatrixSubset()
  if (!raw) return null

  const entries: ArenaEntry[] = []
  const perBackbone: ArenaSnapshot['perBackbone'] = {}
  for (const [backbone, bb] of Object.entries(raw.backbones)) {
    perBackbone[backbone] = {
      fleiss_kappa: bb.fleiss_kappa,
      spearman: bb.spearman_truth_vs_usefulness,
      n_clean_items: bb.n_clean_items,
      n_items: bb.n_items,
    }
    for (const a of bb.agents) {
      entries.push({
        ...a,
        key: `${a.id}__${backbone}`,
        backbone,
        fleiss_kappa: bb.fleiss_kappa,
        spearman_truth_vs_usefulness: bb.spearman_truth_vs_usefulness,
      })
    }
  }
  entries.sort((a, b) => b.arena - a.arena || b.bt_elo - a.bt_elo)

  return {
    entries,
    backbones: Object.keys(raw.backbones),
    judges: raw.judges,
    arena_formula: raw.arena_formula,
    task_set: raw.task_set,
    protocol: raw.protocol,
    generated_at: raw.generated_at,
    n_judge_records_total: raw.n_judge_records_total,
    excluded_agents: raw.excluded_agents,
    excluded_reason: raw.excluded_reason,
    perBackbone,
  }
}
