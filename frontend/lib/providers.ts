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

// The `backbone` field below is only a fallback for legacy pages. The public
// board is harness x backbone: actual backbones per entry come from the
// matrix_subset snapshot (lib/data/load-arena-v2.ts), not from this file.
const AGENTS: AgentMeta[] = [
  {
    id: 'claude-code',
    display: 'Claude Code',
    backbone: 'deepseek-v4-flash',
    family: 'Code-as-Action',
    provider: 'deepseek',
    color: PROVIDER_COLOR.deepseek,
    blurb: 'CLI coding-agent workflow adapted to the sandbox search contract.',
  },
  {
    id: 'opencode',
    display: 'OpenCode',
    backbone: 'deepseek-v4-flash',
    family: 'Code-as-Action',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    github: 'https://github.com/sst/opencode',
    blurb: 'Terminal-native coding-agent workflow.',
  },
  {
    id: 'camel-ai',
    display: 'CAMEL-AI',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'glm',
    color: PROVIDER_COLOR.glm,
    github: 'https://github.com/camel-ai/camel',
    blurb: 'Role-playing multi-agent framework with researcher / writer roles.',
  },
  {
    id: 'deerflow',
    display: 'DeerFlow',
    backbone: 'qwen3.5-27b',
    family: 'Plan-Execute-Report',
    provider: 'meta',
    color: PROVIDER_COLOR.meta,
    blurb: 'ByteDance plan/execute/report stack.',
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
    blurb: 'HuggingFace code-as-action agent.',
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
    blurb: 'Lightweight ReAct loop + retrieval.',
  },
  {
    id: 'ldr',
    display: 'local-deep-research',
    backbone: 'deepseek-v4-flash',
    family: 'Plan-Execute-Report',
    provider: 'google',
    color: PROVIDER_COLOR.google,
    blurb: 'Lightweight local deep-research variant.',
  },
  {
    id: 'storm',
    display: 'STORM',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'minimax',
    color: PROVIDER_COLOR.minimax,
    github: 'https://github.com/stanford-oval/storm',
    blurb: 'Stanford OVAL outline-then-write framework.',
  },
  {
    id: 'gpt-researcher',
    display: 'gpt-researcher',
    backbone: 'deepseek-v4-flash',
    family: 'Plan-Execute-Report',
    provider: 'openai',
    color: PROVIDER_COLOR.openai,
    github: 'https://github.com/assafelovic/gpt-researcher',
    blurb: 'RAG + report-writing pipeline.',
  },
  {
    id: 'qx-agents',
    display: 'qx-agents',
    backbone: 'deepseek-v4-flash',
    family: 'Multi-agent',
    provider: 'z',
    color: PROVIDER_COLOR.z,
    blurb: 'Custom multi-agent research stack.',
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
