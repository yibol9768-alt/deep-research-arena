import { rankedAgents } from '@/lib/data/load-leaderboard'
import { AgentsClient } from './agents-client'

export const dynamic = 'force-static'

export default function AgentsHubPage() {
  return <AgentsClient agents={rankedAgents()} />
}
