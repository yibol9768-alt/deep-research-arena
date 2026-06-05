// Maps an agent name → its display backbone, brand color, and one-line description.
// Edit when adding a new agent.

export type ProviderKey =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'meta'
  | 'deepseek'
  | 'xai'
  | 'mistral'
  | 'glm'
  | 'qwen'
  | 'minimax'
  | 'nvidia'
  | 'z'

export interface AgentMeta {
  /** Canonical agent id used in JSON files (e.g., 'react-qwen35plus') */
  id: string
  /** Display name shown in UI */
  display: string
  /** Backbone model identifier */
  backbone: string
  /** Architectural family */
  family: 'ReAct' | 'Plan-Execute-Report' | 'Multi-agent' | 'Code-as-Action' | 'Graph-based' | 'Memory-augmented'
  /** Provider key used for color */
  provider: ProviderKey
  /** Hex color for charts (resolved from provider) */
  color: string
  /** Optional GitHub link */
  github?: string
  /** One-line description */
  blurb?: string
}

const PROVIDER_COLOR: Record<ProviderKey, string> = {
  openai: '#1f1f1f',
  anthropic: '#cc785c',
  google: '#34A853',
  meta: '#047AFE',
  deepseek: '#1c7ff8',
  xai: '#ff6900',
  mistral: '#ff7018',
  glm: '#86b737',
  qwen: '#FF9900',
  minimax: '#EB3568',
  nvidia: '#76B900',
  z: '#6E5BFF',
}

export function providerColor(p: ProviderKey): string {
  return PROVIDER_COLOR[p] ?? '#7F4BF3'
}

// Backbones below are the ACTUAL models recorded in each run's meta.json on the
// eval box (2026-06-05): every framework ran on deepseek-v4-flash except
// DeerFlow (qwen3.5-27b). Do not list aspirational/configured-but-unused models.
const AGENTS: AgentMeta[] = [
  {
    id: 'camel-ai',
    display: 'CAMEL-AI',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'glm',
    color: PROVIDER_COLOR.glm,
    github: 'https://github.com/camel-ai/camel',
    blurb: 'Role-playing multi-agent framework with researcher / writer roles. Most grounded agent on the board (60% reachable citations).',
  },
  {
    id: 'deerflow',
    display: 'DeerFlow',
    backbone: 'qwen3.5-27b',
    family: 'Plan-Execute-Report',
    provider: 'meta',
    color: PROVIDER_COLOR.meta,
    blurb: 'ByteDance plan/execute/report stack. Ties camel-ai on grounding (60% reachable); some runs degrade into data-availability writeups.',
  },
  {
    id: 'flowsearcher-ds',
    display: 'FlowSearcher',
    backbone: 'deepseek-v4-flash',
    family: 'Memory-augmented',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'Custom L1/L2/L3 hierarchical memory + adaptive search.',
  },
  {
    id: 'smolagents',
    display: 'smolagents',
    backbone: 'deepseek-v4-flash',
    family: 'Code-as-Action',
    provider: 'glm',
    color: PROVIDER_COLOR.glm,
    github: 'https://github.com/huggingface/smolagents',
    blurb: 'HuggingFace code-as-action agent. Solid prose; citations sometimes drift off-topic.',
  },
  {
    id: 'langchain-odr',
    display: 'open-deep-research',
    backbone: 'deepseek-v4-flash',
    family: 'Graph-based',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'LangChain open_deep_research graph pipeline.',
  },
  {
    id: 'ii-researcher',
    display: 'ii-researcher',
    backbone: 'deepseek-v4-flash',
    family: 'ReAct',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    blurb: 'Lightweight ReAct loop + retrieval. High judge Elo but only ~27% of citations resolve.',
  },
  {
    id: 'ldr',
    display: 'local-deep-research',
    backbone: 'deepseek-v4-flash',
    family: 'Plan-Execute-Report',
    provider: 'google',
    color: PROVIDER_COLOR.google,
    blurb: 'Lightweight local DR variant. Citations rarely resolve (2% reachable).',
  },
  {
    id: 'storm',
    display: 'STORM',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'minimax',
    color: PROVIDER_COLOR.minimax,
    github: 'https://github.com/stanford-oval/storm',
    blurb: 'Stanford OVAL outline-then-write framework. Fluent, weakly grounded in the sandbox (13% reachable).',
  },
  {
    id: 'gpt-researcher',
    display: 'gpt-researcher',
    backbone: 'deepseek-v4-flash',
    family: 'Plan-Execute-Report',
    provider: 'openai',
    color: PROVIDER_COLOR.openai,
    github: 'https://github.com/assafelovic/gpt-researcher',
    blurb: 'RAG + report-writing pipeline. Tops the RAW judge Elo (1207) yet only 4% of its citations resolve -- the canonical fluent-fabrication case the truth gate exists for.',
  },
  {
    id: 'qx-agents',
    display: 'qx-agents',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    blurb: 'Partial coverage (48 tasks attempted, 13 battles); near-zero grounding so far.',
  },
]

export const AGENT_INDEX: Record<string, AgentMeta> = Object.fromEntries(AGENTS.map((a) => [a.id, a]))

export function agentMeta(id: string): AgentMeta {
  return (
    AGENT_INDEX[id] ?? {
      id,
      display: id,
      backbone: 'unknown',
      family: 'ReAct',
      provider: 'z',
      color: PROVIDER_COLOR.z,
    }
  )
}

export function allAgents(): AgentMeta[] {
  return AGENTS
}
