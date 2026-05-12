// Build-time data loading. Reads from the existing data/results/ tree so the
// Next.js pipeline doesn't need its own copy of the leaderboard data.
import fs from 'node:fs';
import path from 'node:path';
import type { LeaderboardData, EloStats } from './types';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const V3_DIR = path.join(REPO_ROOT, 'data', 'results', 'deep_v3');
const TASKS_DIR = path.join(REPO_ROOT, 'data', 'tasks', 'deep_research', 'cross_site_deep');
const AUDIT_DIR = path.join(REPO_ROOT, 'data', 'results', 'audit');
const DOCS_DIR = path.join(REPO_ROOT, 'docs');

function readJsonOrNull<T = unknown>(p: string): T | null {
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(fs.readFileSync(p, 'utf-8')) as T;
  } catch {
    return null;
  }
}

function readTextOrNull(p: string): { text: string; mtime: string } | null {
  try {
    if (!fs.existsSync(p)) return null;
    const text = fs.readFileSync(p, 'utf-8');
    const mtime = new Date(fs.statSync(p).mtime).toISOString().replace('T', ' ').slice(0, 19);
    return { text, mtime };
  } catch {
    return null;
  }
}

interface RawLeaderboardJson {
  n_runs?: number;
  agents?: Record<string, EloStats>;
  elo_v2_ci?: Record<string, EloStats>;
  ranked?: [string, EloStats][];
  pair_counts?: Record<string, number>;
  significance?: Array<{ higher: string; lower: string; gap: number; p_value: number | string; significant: boolean }>;
  n_tasks?: number;
  n_tasks_target?: number;
  kpis?: LeaderboardData['kpis'];
}

export function loadLeaderboard(): LeaderboardData {
  const empty: LeaderboardData = {
    n_runs: 0,
    n_agents: 0,
    n_tasks: 0,
    ranked: [],
    elo_min: 0,
    elo_max: 0,
    elo_span: 1,
    sig: [],
    sig_lookup: {},
    pair_counts: {},
    n_tasks_target: 57,
    leaderboard_mtime: null,
    kpis: null,
  };

  const lbPath = path.join(V3_DIR, 'leaderboard_deep.json');
  const raw = readJsonOrNull<RawLeaderboardJson>(lbPath);
  if (!raw) return empty;

  // Source of truth for ranking is elo_v2_ci (object keyed by agent name).
  const agents = raw.elo_v2_ci || raw.agents || {};
  const entries: [string, EloStats][] = Object.entries(agents);
  entries.sort((a, b) => (b[1].elo ?? 0) - (a[1].elo ?? 0));

  const elos = entries.map(([, s]) => s.elo);
  const elo_min = elos.length ? Math.min(...elos) : 0;
  const elo_max = elos.length ? Math.max(...elos) : 0;
  const elo_span = Math.max(1, elo_max - elo_min);

  const sig = (raw.significance || []) as LeaderboardData['sig'];
  const sig_lookup: Record<string, boolean> = {};
  sig.forEach((p) => {
    sig_lookup[`${p.higher}__${p.lower}`] = p.significant;
  });

  // Load KPI stats sidecar if present.
  const kpisRaw = readJsonOrNull<{
    total_pairs?: number;
    unique_urls?: number;
    est_tokens?: number;
    judge_calls?: number;
    degenerate_filtered?: number;
  }>(path.join(V3_DIR, 'kpi_stats.json'));

  const kpis = kpisRaw
    ? {
        total_pairs: kpisRaw.total_pairs ?? 0,
        unique_urls: kpisRaw.unique_urls ?? 0,
        est_tokens: kpisRaw.est_tokens ?? 0,
        judge_calls: kpisRaw.judge_calls ?? 0,
        degenerate_filtered: kpisRaw.degenerate_filtered ?? 0,
      }
    : null;

  const mtime = fs.existsSync(lbPath)
    ? new Date(fs.statSync(lbPath).mtime).toISOString().replace('T', ' ').slice(0, 19)
    : null;

  return {
    n_runs: raw.n_runs ?? 0,
    n_agents: entries.length,
    n_tasks: raw.n_tasks ?? 0,
    ranked: entries,
    elo_min,
    elo_max,
    elo_span,
    sig,
    sig_lookup,
    pair_counts: raw.pair_counts || {},
    n_tasks_target: raw.n_tasks_target ?? 57,
    leaderboard_mtime: mtime,
    kpis,
  };
}

export function listTaskIds(): string[] {
  try {
    if (!fs.existsSync(TASKS_DIR)) return [];
    return fs
      .readdirSync(TASKS_DIR)
      .filter((n) => n.startsWith('dr_cross_deep_') && n.endsWith('.json'))
      .map((n) => n.replace(/\.json$/, ''))
      .sort();
  } catch {
    return [];
  }
}

export function loadTask(taskId: string): { cfg: Record<string, unknown> | null; rows: Array<Record<string, unknown>> } {
  const cfg = readJsonOrNull(path.join(TASKS_DIR, `${taskId}.json`));
  // per-task agent rows live in score sidecars; we don't synthesize here.
  return { cfg: cfg as Record<string, unknown> | null, rows: [] };
}

export function loadProjectWriteup() {
  return readTextOrNull(path.join(DOCS_DIR, 'PROJECT_WRITEUP.md'));
}

export function loadLatestAudit(): { filename: string; text: string; mtime: string } | null {
  try {
    if (!fs.existsSync(AUDIT_DIR)) return null;
    const candidates = fs
      .readdirSync(AUDIT_DIR)
      .filter((n) => /^DR_SCORE_AUDIT_.*\.md$/.test(n))
      .map((n) => ({ n, mtime: fs.statSync(path.join(AUDIT_DIR, n)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);
    if (!candidates.length) return null;
    const latest = candidates[0];
    const full = path.join(AUDIT_DIR, latest.n);
    return {
      filename: latest.n,
      text: fs.readFileSync(full, 'utf-8'),
      mtime: new Date(latest.mtime).toISOString().replace('T', ' ').slice(0, 19),
    };
  } catch {
    return null;
  }
}

export const GITHUB_URL = 'https://github.com/yibol9768-alt/deep-research-arena';
