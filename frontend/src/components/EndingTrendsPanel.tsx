import { useState } from 'react'
import Plot from 'react-plotly.js'
import { Tabs, TabsList, TabsTab } from './ui/tabs'
import { lineChart, multiLineChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { ResignationTrendRow, TimeForfeitTrendRow } from '../hooks/useEndingSummary'

export default function EndingTrendsPanel({
  resignationTrend,
  timeForfeitTrend,
}: {
  resignationTrend: ResignationTrendRow[]
  timeForfeitTrend: TimeForfeitTrendRow[]
}) {
  const [view, setView] = useState<'resignation' | 'time_forfeit'>('resignation')

  const hasResignationData = resignationTrend.length >= 2
  const hasTimeForfeitData = timeForfeitTrend.length >= 2

  return (
    <div className="mt-3">
      <Tabs value={view} onValueChange={(v) => setView(v as 'resignation' | 'time_forfeit')}>
        <TabsList>
          <TabsTab value="resignation">Resignations: time pressure</TabsTab>
          <TabsTab value="time_forfeit">Time forfeits: ahead vs. scrambling</TabsTab>
        </TabsList>
      </Tabs>

      <div className="mt-3">
        {view === 'resignation' &&
          (hasResignationData ? (
            <Plot
              {...lineChart(resignationTrend, 'label', 'pct', THEME.negative, {
                height: 280,
                xTitle: 'Quarter',
                yTitle: '% of resignation losses',
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          ) : (
            <p className="text-xs text-[var(--cw-muted)]">Not enough games yet.</p>
          ))}

        {view === 'time_forfeit' &&
          (hasTimeForfeitData ? (
            <Plot
              {...multiLineChart(
                timeForfeitTrend,
                'label',
                [
                  { y: 'pct_ahead', label: 'flagged while ahead on material', color: THEME.negative },
                  { y: 'pct_mutual', label: 'mutual scramble', color: THEME.accentGold },
                ],
                { height: 280, xTitle: 'Quarter', yTitle: '% of time-forfeit losses' },
              )}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          ) : (
            <p className="text-xs text-[var(--cw-muted)]">Not enough games yet.</p>
          ))}
      </div>
    </div>
  )
}
