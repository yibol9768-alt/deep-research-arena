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

const AGENTS: AgentMeta[] = [
  {
    id: 'flowsearcher-ds',
    display: 'FlowSearcher',
    backbone: 'DeepSeek V3.2',
    family: 'Memory-augmented',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'Custom L1/L2/L3 hierarchical memory + adaptive search.',
  },
  {
    id: 'camel-ai',
    display: 'CAMEL-AI',
    backbone: 'GLM-4.6',
    family: 'Multi-agent',
    provider: 'glm',
    color: PROVIDER_COLOR.glm,
    github: 'https://github.com/camel-ai/camel',
    blurb: 'Role-playing multi-agent framework with researcher / writer roles.',
  },
  {
    id: 'smolagents',
    display: 'smolagents',
    backbone: 'GLM-4.7',
    family: 'Code-as-Action',
    provider: 'glm',
    color: PROVIDER_COLOR.glm,
    github: 'https://github.com/huggingface/smolagents',
    blurb: 'HuggingFace code-as-action agent. Beautiful prose, fragile citations.',
  },
  {
    id: 'gpt-researcher',
    display: 'gpt-researcher',
    backbone: 'GLM-4.7',
    family: 'Plan-Execute-Report',
    provider: 'openai',
    color: PROVIDER_COLOR.openai,
    github: 'https://github.com/assafelovic/gpt-researcher',
    blurb: 'RAG + report writing pipeline. Strong on citation alignment.',
  },
  {
    id: 'deerflow',
    display: 'DeerFlow',
    backbone: 'GLM-4.6',
    family: 'Plan-Execute-Report',
    provider: 'meta',
    color: PROVIDER_COLOR.meta,
    blurb: 'ByteDance plan/execute/report stack. +162 Elo after adapter swap.',
  },
  {
    id: 'ldr',
    display: 'local-deep-research',
    backbone: 'GLM-4.6',
    family: 'Plan-Execute-Report',
    provider: 'google',
    color: PROVIDER_COLOR.google,
    blurb: 'Lightweight local DR variant. Solid mid-pack contender.',
  },
  {
    id: 'storm',
    display: 'STORM',
    backbone: 'GLM-4.6',
    family: 'Multi-agent',
    provider: 'minimax',
    color: PROVIDER_COLOR.minimax,
    github: 'https://github.com/stanford-oval/storm',
    blurb: 'Stanford OVAL Wikipedia-style outline + write framework.',
  },
  {
    id: 'langchain-odr',
    display: 'open-deep-research',
    backbone: 'DeepSeek V4 flash',
    family: 'Graph-based',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'LangChain open_deep_research. DeepSeek-only due to GLM JSON quirks.',
  },
  {
    id: 'open-deep-research',
    display: 'open-deep-research',
    backbone: 'DeepSeek V4 flash',
    family: 'Graph-based',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'LangChain open_deep_research. DeepSeek-only due to GLM JSON quirks.',
  },
  {
    id: 'ii-researcher',
    display: 'ii-researcher',
    backbone: 'GLM-4.6',
    family: 'ReAct',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    blurb: 'II-Researcher: lightweight ReAct loop + retrieval. Strong on debunking tasks.',
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
