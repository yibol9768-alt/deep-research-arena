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
  | 'moonshot'

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
  /** Included in the home-page charts / leaderboard (well-known open-source DR frameworks). */
  featured?: boolean
  /** Open-source deep-research framework (as opposed to a coding CLI or niche tool). */
  openSource?: boolean
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
  moonshot: '#4D67FF',
}

export function providerColor(p: ProviderKey): string {
  return PROVIDER_COLOR[p] ?? '#7F4BF3'
}

// Backbones below are the ACTUAL models recorded in each run's meta.json on the
// eval box (2026-06-05): every framework ran on deepseek-v4-flash except
// DeerFlow (qwen3.5-27b). Do not list aspirational/configured-but-unused models.
const AGENTS: AgentMeta[] = [
  {
    id: 'claude-code',
    display: 'Claude Code',
    backbone: 'deepseek-v4-flash',
    family: 'Code-as-Action',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'CLI coding-agent workflow adapted to the sandbox. Leads the truth-gated board because high judge Elo is paired with strong citation reachability.',
  },
  {
    id: 'opencode',
    display: 'OpenCode',
    backbone: 'deepseek-v4-flash',
    family: 'Code-as-Action',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    github: 'https://github.com/sst/opencode',
    blurb: 'Terminal-native coding-agent workflow. The strongest grounding profile in the current snapshot, with more than 90% reachable citations.',
  },
  {
    id: 'camel-ai',
    display: 'CAMEL-AI',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'glm',
    // Overridden off the GLM green so it does not collide with smolagents in charts.
    color: '#cc785c',
    github: 'https://github.com/camel-ai/camel',
    blurb: 'Role-playing multi-agent framework with researcher / writer roles. Most grounded agent on the board (60% reachable citations).',
    featured: true,
    openSource: true,
  },
  {
    id: 'deerflow',
    display: 'DeerFlow',
    backbone: 'qwen3.5-27b',
    family: 'Plan-Execute-Report',
    provider: 'meta',
    color: PROVIDER_COLOR.meta,
    github: 'https://github.com/bytedance/deer-flow',
    blurb: 'ByteDance plan/execute/report stack. Ties camel-ai on grounding (60% reachable); some runs degrade into data-availability writeups.',
    featured: true,
    openSource: true,
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
    featured: true,
    openSource: true,
  },
  {
    id: 'langchain-odr',
    display: 'open-deep-research',
    backbone: 'deepseek-v4-flash',
    family: 'Graph-based',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    github: 'https://github.com/langchain-ai/open_deep_research',
    blurb: 'LangChain open_deep_research graph pipeline.',
    featured: true,
    openSource: true,
  },
  {
    id: 'ii-researcher',
    display: 'ii-researcher',
    backbone: 'deepseek-v4-flash',
    family: 'ReAct',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    github: 'https://github.com/Intelligent-Internet/ii-researcher',
    blurb: 'Lightweight ReAct loop + retrieval. High judge Elo but only ~27% of citations resolve.',
    featured: true,
    openSource: true,
  },
  {
    id: 'ldr',
    display: 'local-deep-research',
    backbone: 'deepseek-v4-flash',
    family: 'Plan-Execute-Report',
    provider: 'google',
    color: PROVIDER_COLOR.google,
    github: 'https://github.com/LearningCircuit/local-deep-research',
    blurb: 'Lightweight local DR variant. Citations rarely resolve (2% reachable).',
    featured: true,
    openSource: true,
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
    featured: true,
    openSource: true,
  },
  {
    id: 'gpt-researcher',
    display: 'gpt-researcher',
    backbone: 'deepseek-v4-flash',
    family: 'Plan-Execute-Report',
    provider: 'openai',
    color: PROVIDER_COLOR.openai,
    github: 'https://github.com/assafelovic/gpt-researcher',
    blurb: 'RAG + report-writing pipeline. Strong raw judge Elo, but only 4% of cited URLs resolve in the sandbox, so the truth gate sharply lowers its public rank.',
    featured: true,
    openSource: true,
  },
  {
    id: 'qx-agents',
    display: 'qx-agents',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    github: 'https://github.com/qx-labs/agents-deep-research',
    openSource: true,
    blurb: 'Partial coverage (48 tasks attempted, 13 battles); near-zero grounding so far.',
  },
]

const MODEL_META: Record<string, AgentMeta> = {
  'glm-5': {
    id: 'glm-5',
    display: 'GLM-5',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'glm',
    color: PROVIDER_COLOR.glm,
  },
  'kimi-k2.5': {
    id: 'kimi-k2.5',
    display: 'Kimi K2.5',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'moonshot',
    color: PROVIDER_COLOR.moonshot,
  },
  'minimax-m2.5': {
    id: 'minimax-m2.5',
    display: 'MiniMax M2.5',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'minimax',
    color: PROVIDER_COLOR.minimax,
  },
  'deepseek-v4-flash': {
    id: 'deepseek-v4-flash',
    display: 'DeepSeek V4 Flash',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
  },
  'qwen3-32b': {
    id: 'qwen3-32b',
    display: 'Qwen3 32B',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'qwen',
    color: PROVIDER_COLOR.qwen,
  },
  'qwen-flash': {
    id: 'qwen-flash',
    display: 'Qwen Flash',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'qwen',
    color: PROVIDER_COLOR.qwen,
  },
  'qwen3-max': {
    id: 'qwen3-max',
    display: 'Qwen3 Max',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'qwen',
    color: PROVIDER_COLOR.qwen,
  },
  'qwen3-30b-a3b-instruct-2507': {
    id: 'qwen3-30b-a3b-instruct-2507',
    display: 'Qwen3 30B-A3B',
    backbone: 'fixed DR scaffold',
    family: 'ReAct',
    provider: 'qwen',
    color: PROVIDER_COLOR.qwen,
  },
}

export const AGENT_INDEX: Record<string, AgentMeta> = Object.fromEntries(AGENTS.map((a) => [a.id, a]))

export function agentMeta(id: string): AgentMeta {
  return (
    AGENT_INDEX[id] ??
    MODEL_META[id] ?? {
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

/**
 * Well-known open-source deep-research frameworks shown on the home page charts
 * and leaderboard. Coding CLIs (claude-code, opencode) and niche tools
 * (qx-agents, flowsearcher-ds) are kept in the registry — their /agents/[id]
 * pages still render — but are filtered out of the home page.
 */
export function featuredAgents(): AgentMeta[] {
  return AGENTS.filter((a) => a.featured)
}

export function isFeatured(id: string): boolean {
  return !!AGENT_INDEX[id]?.featured
}
