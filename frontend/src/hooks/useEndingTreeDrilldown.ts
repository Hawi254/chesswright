import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface SecondaryChartRow {
  label: string
  n: number
  pct: number
}

export interface EndingDrilldownData {
  gameIds: string[]
  total: number
  secondaryChart: SecondaryChartRow[] | null
  secondaryChartKind: 'piece' | 'mate' | 'scramble' | null
}

interface RawResponse {
  game_ids: string[]
  total: number
  secondary_chart: SecondaryChartRow[] | null
  secondary_chart_kind: 'piece' | 'mate' | 'scramble' | null
}

export interface UseEndingTreeDrilldownResult {
  drilldown: EndingDrilldownData | null
  loading: boolean
  error: boolean
}

export function useEndingTreeDrilldown(
  path: string | null,
  timeControl: string | null,
): UseEndingTreeDrilldownResult {
  const [state, setState] = useState<UseEndingTreeDrilldownResult>({ drilldown: null, loading: false, error: false })

  useEffect(() => {
    if (path === null || path === 'root') {
      setState({ drilldown: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState({ drilldown: null, loading: true, error: false })
    const params = new URLSearchParams({ path })
    if (timeControl) params.set('time_control', timeControl)
    fetch(`${API_BASE}/api/game-endings/games?${params.toString()}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<RawResponse>
      })
      .then((body) => {
        if (!cancelled) {
          setState({
            drilldown: {
              gameIds: body.game_ids,
              total: body.total,
              secondaryChart: body.secondary_chart,
              secondaryChartKind: body.secondary_chart_kind,
            },
            loading: false,
            error: false,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setState({ drilldown: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [path, timeControl])

  return state
}
