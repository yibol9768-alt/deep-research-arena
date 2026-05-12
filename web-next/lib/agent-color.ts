// Deterministic per-agent color hashing. Same agent name always → same color.
export const AGENT_PALETTE = [
  '#3b82f6', '#8b5cf6', '#ec4899', '#f97316',
  '#14b8a6', '#0ea5e9', '#a855f7', '#f59e0b',
  '#6366f1', '#10b981', '#ef4444', '#06b6d4',
];

export function agentColor(name: string): string {
  if (!name) return AGENT_PALETTE[0];
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) & 0xffffffff;
  }
  return AGENT_PALETTE[Math.abs(h) % AGENT_PALETTE.length];
}
