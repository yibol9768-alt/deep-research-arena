'use client'

import { useEffect, useState } from 'react'
import type { RankedAgent } from '@/lib/data/types'

// Fetches the leaderboard via an internal Route Handler so the client can
// consume it without bundling Node-only fs imports.
export function useRanked(): RankedAgent[] {
  const [data, setData] = useState<RankedAgent[]>([])
  useEffect(() => {
    let cancelled = false
    fetch('/api/leaderboard')
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])
  return data
}
