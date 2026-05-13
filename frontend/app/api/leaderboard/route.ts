import { NextResponse } from 'next/server'
import { rankedAgents } from '@/lib/data/load-leaderboard'

// Static export: this route is materialized to /api/leaderboard.json at build time.
export const dynamic = 'force-static'

export function GET() {
  const data = rankedAgents()
  return NextResponse.json(data)
}
