import fs from 'node:fs'
import path from 'node:path'

export interface DeepTask {
  task_id: string
  intent: string
  intent_type?: string
  domain?: string
  sites?: string[]
  difficulty?: number
  expected_steps?: number
  url_coverage?: Record<string, number>
  synthesis_requirements?: string[]
  golden?: {
    required_urls?: string[]
    must_cite_urls?: string[]
  }
}

export interface TaskSummary {
  id: string
  title: string
  intentType: string
  domain: string
  sites: string[]
  difficulty: number
  expectedSteps: number
  requiredUrls: number
  checklistItems: number
  prompt: string
}

const REPO_ROOT = path.resolve(process.cwd(), '..')
const TASK_DIR = path.join(REPO_ROOT, 'data/tasks/deep_research/cross_site_deep')
const CHECKLIST_PATH = path.join(TASK_DIR, 'checklists_deep.json')

function readJsonOrNull<T>(p: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8')) as T
  } catch {
    return null
  }
}

let cachedTasks: TaskSummary[] | null = null
let cachedChecklist: Record<string, string[]> | null = null

export function loadChecklists(): Record<string, string[]> {
  if (cachedChecklist) return cachedChecklist
  cachedChecklist = readJsonOrNull<Record<string, string[]>>(CHECKLIST_PATH) ?? {}
  return cachedChecklist
}

export function loadTasks(): TaskSummary[] {
  if (cachedTasks) return cachedTasks
  const checklists = loadChecklists()
  let files: string[] = []
  try {
    files = fs
      .readdirSync(TASK_DIR)
      .filter((name) => /^dr_cross_deep_\d+\.json$/.test(name))
      .sort()
  } catch {
    files = []
  }

  cachedTasks = files.map((name) => {
    const raw = readJsonOrNull<DeepTask>(path.join(TASK_DIR, name))
    const id = raw?.task_id ?? name.replace(/\.json$/, '')
    const prompt = typeof raw?.intent === 'string' ? raw.intent : JSON.stringify(raw?.intent ?? '')
    const requiredUrls =
      raw?.golden?.required_urls?.length ??
      raw?.golden?.must_cite_urls?.length ??
      Object.values(raw?.url_coverage ?? {}).reduce((sum, n) => sum + Number(n || 0), 0)
    return {
      id,
      title: prompt.split('\n')[0]?.replace(/^Produce an? /, '').slice(0, 110) || id,
      intentType: typeof raw?.intent_type === 'string' ? raw.intent_type : inferIntent(prompt),
      domain: typeof raw?.domain === 'string' ? raw.domain : inferDomain(id, prompt),
      sites: Array.isArray(raw?.sites) ? raw.sites.map(String) : [],
      difficulty: raw?.difficulty ?? 5,
      expectedSteps: raw?.expected_steps ?? 80,
      requiredUrls,
      checklistItems: checklists[id]?.length ?? 0,
      prompt,
    }
  })
  return cachedTasks
}

export function getTask(id: string): TaskSummary | undefined {
  return loadTasks().find((task) => task.id === id)
}

export function taskStats() {
  const tasks = loadTasks()
  const intents = new Set(tasks.map((task) => task.intentType))
  const domains = new Set(tasks.map((task) => task.domain))
  const sites = new Set(tasks.flatMap((task) => task.sites))
  return {
    count: tasks.length,
    intents: intents.size,
    domains: domains.size,
    sites: sites.size,
    avgDifficulty: tasks.reduce((sum, task) => sum + task.difficulty, 0) / Math.max(1, tasks.length),
    checklistItems: tasks.reduce((sum, task) => sum + task.checklistItems, 0),
  }
}

function inferIntent(prompt: string): string {
  const lower = prompt.toLowerCase()
  if (lower.includes('recommend')) return 'recommendation'
  if (lower.includes('compare') || lower.includes('comparison')) return 'comparison'
  if (lower.includes('debunk') || lower.includes('fact-check')) return 'debunking'
  if (lower.includes('causal') || lower.includes('why')) return 'causal'
  if (lower.includes('timeline')) return 'timeline'
  return 'enumeration'
}

function inferDomain(id: string, prompt: string): string {
  const match = prompt.match(/on ([^,\n]+),? spanning/i)
  if (match?.[1]) return match[1]
  return id.replace('dr_cross_deep_', 'task ')
}
