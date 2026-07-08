import { loadArenaV2, harnessAggregates } from '@/lib/data/load-arena-v2'
import { AgentsClient } from './agents-client'

export const dynamic = 'force-static'

export default function AgentsHubPage() {
  const arena = loadArenaV2()
  const harnesses = arena ? harnessAggregates(arena) : []
  return <AgentsClient harnesses={harnesses} nBackbones={arena?.backbones.length ?? 0} />
}
