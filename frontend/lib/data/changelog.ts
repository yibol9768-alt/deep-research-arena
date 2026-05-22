import fs from 'node:fs'
import path from 'node:path'

export type ChangelogSection = {
  heading: string
  bullets: string[]
}

export type ChangelogLink = {
  label: string
  href: string
}

export type ChangelogEntry = {
  version: string
  date: string
  title: string
  summary: string
  tags: string[]
  sections: ChangelogSection[]
  links?: ChangelogLink[]
}

export type ChangelogFile = {
  _schema?: string
  _notes?: string
  entries: ChangelogEntry[]
}

const FALLBACK: ChangelogFile = {
  _schema: 'deep-research-arena-changelog/v1',
  entries: [],
}

function resolveChangelogPath(): string {
  const candidates = [
    path.join(process.cwd(), '..', 'data', 'changelog.json'),
    path.join(process.cwd(), 'data', 'changelog.json'),
    path.join(process.cwd(), '..', '..', 'data', 'changelog.json'),
  ]
  for (const p of candidates) {
    if (fs.existsSync(p)) return p
  }
  return candidates[0]
}

export function loadChangelog(): ChangelogFile {
  try {
    const file = resolveChangelogPath()
    const raw = fs.readFileSync(file, 'utf-8')
    const parsed = JSON.parse(raw) as ChangelogFile
    if (!parsed || !Array.isArray(parsed.entries)) return FALLBACK
    return parsed
  } catch {
    return FALLBACK
  }
}
