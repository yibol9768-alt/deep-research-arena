// Client-safe backbone display helpers (no node imports).

/** Short backbone tag used in chart labels and pills. */
export const BACKBONE_SHORT: Record<string, string> = {
  'qwen3-8b': 'Qwen3-8B',
  'deepseek-v4-flash': 'DS-V4-Flash',
}

export function backboneShort(bb: string): string {
  return BACKBONE_SHORT[bb] ?? bb
}
