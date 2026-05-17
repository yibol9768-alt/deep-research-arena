import fs from 'node:fs'
import path from 'node:path'

const TASKS_DIR = path.join(
  process.cwd(),
  '..',
  'data',
  'tasks',
  'deep_research',
  'cross_site_deep',
)

export interface Task {
  id: string
  title: string
  prompt: string
  intentType: string
  domain: string
  difficulty: number
  expectedSteps: number
  sites: string[]
  checklistItems: number
  /** Total URLs the task requires citing (read from url_coverage.must_cite or similar) */
  requiredUrls: number
  tier?: string
}

interface TaskJson {
  task_id: string
  intent: string
  domain?: string
  intent_type?: string
  difficulty?: number | string
  expected_steps?: number | string
  sites?: string[]
  tier?: string
  url_coverage?: { must_cite?: number; total?: number }
}

let _tasksCache: Task[] | null = null
let _checklistsCache: Record<string, string[]> | null = null

function _loadChecklistsRaw(): Record<string, string[]> {
  if (_checklistsCache) return _checklistsCache
  const p = path.join(TASKS_DIR, 'checklists_deep.json')
  if (!fs.existsSync(p)) {
    _checklistsCache = {}
    return _checklistsCache
  }
  _checklistsCache = JSON.parse(fs.readFileSync(p, 'utf-8')) as Record<string, string[]>
  return _checklistsCache
}

export function loadChecklists(): Record<string, string[]> {
  return _loadChecklistsRaw()
}

function _firstLine(s: string): string {
  const line = (s.split(/\n/)[0] || '').trim()
  // Stop at the first colon for cleaner card titles when intents are like
  // "Produce a comprehensive market-intelligence report on X, spanning THREE…"
  if (line.length > 110) {
    const trimmed = line.slice(0, 107).trimEnd()
    return trimmed + '…'
  }
  return line
}

export function loadTasks(): Task[] {
  if (_tasksCache) return _tasksCache
  if (!fs.existsSync(TASKS_DIR)) {
    _tasksCache = []
    return _tasksCache
  }
  const checklists = _loadChecklistsRaw()
  const entries = fs
    .readdirSync(TASKS_DIR)
    .filter((f) => f.startsWith('dr_cross_deep_') && f.endsWith('.json'))
    .sort()
  const tasks: Task[] = []
  for (const f of entries) {
    try {
      const j = JSON.parse(fs.readFileSync(path.join(TASKS_DIR, f), 'utf-8')) as TaskJson
      const id = j.task_id
      const intent = j.intent ?? ''
      tasks.push({
        id,
        title: _firstLine(intent) || id,
        prompt: intent,
        intentType: (j.intent_type || 'unknown').toLowerCase(),
        domain: j.domain || 'unknown',
        difficulty: Number(j.difficulty ?? 3),
        expectedSteps: Number(j.expected_steps ?? 15),
        sites: j.sites || ['shopping', 'reddit', 'wikipedia'],
        checklistItems: (checklists[id] || []).length,
        requiredUrls: Number(j.url_coverage?.must_cite ?? j.url_coverage?.total ?? 0),
        tier: j.tier,
      })
    } catch {
      // Skip malformed entries silently — they shouldn't break the build.
    }
  }
  _tasksCache = tasks
  return tasks
}

export function getTask(id: string): Task | undefined {
  return loadTasks().find((t) => t.id === id)
}

export function taskStats(): {
  count: number
  intents: number
  checklistItems: number
  avgDifficulty: number
} {
  const tasks = loadTasks()
  const intents = new Set(tasks.map((t) => t.intentType)).size
  const checklistItems = Object.values(_loadChecklistsRaw()).reduce(
    (acc, items) => acc + (items?.length || 0),
    0,
  )
  const avgDifficulty =
    tasks.length === 0
      ? 0
      : tasks.reduce((acc, t) => acc + (Number.isFinite(t.difficulty) ? t.difficulty : 3), 0) /
        tasks.length
  return {
    count: tasks.length,
    intents,
    checklistItems,
    avgDifficulty,
  }
}
