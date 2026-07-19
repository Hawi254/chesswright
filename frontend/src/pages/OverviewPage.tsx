import CareerHighlight from '../components/CareerHighlight'
import CoachingZone from '../components/CoachingZone'
import EngineStatusStrip from '../components/EngineStatusStrip'
import EvolutionZone from '../components/EvolutionZone'
import IdentityZone from '../components/IdentityZone'
import MilestonesRow from '../components/MilestonesRow'
import ZoneHead from '../components/ZoneHead'
import { useCareerHighlight } from '../hooks/useCareerHighlight'
import { useCoachingPlanStatus } from '../hooks/useCoachingPlanStatus'
import { useEngineStatus } from '../hooks/useEngineStatus'
import { useEvolutionData } from '../hooks/useEvolutionData'
import { useMilestones } from '../hooks/useMilestones'
import { useOverviewData } from '../hooks/useOverviewData'
import { useWinRateByColor } from '../hooks/useWinRateByColor'

export default function OverviewPage() {
  const { stats, ratingSnapshot, streak, findings, narrative, loading, error } = useOverviewData()
  const { milestones } = useMilestones()
  const { ratingTrajectory, acplTrajectory } = useEvolutionData()
  const { games } = useCareerHighlight()
  const { cached } = useCoachingPlanStatus()
  const engineStatus = useEngineStatus()
  const { rows: winRateByColor } = useWinRateByColor()

  const showEvolutionBlock = Boolean(
    (milestones && milestones.length > 0) ||
    (ratingTrajectory && acplTrajectory) ||
    (games && games.length > 0),
  )

  return (
    <div className="cw-overview min-h-full p-8">
      <EngineStatusStrip
        status={engineStatus}
        totalGames={stats?.total_games ?? null}
        analyzedGames={stats?.analyzed_games ?? null}
      />

      {loading && <p className="mt-4 text-[var(--cw-muted)]">Loading…</p>}

      {!loading && error && (
        <p className="mt-4 text-negative">
          Couldn&apos;t load your Overview data. Confirm the Chesswright API server
          is running.
        </p>
      )}

      {!loading && !error && stats && ratingSnapshot && streak && findings && narrative !== null && (
        <div className="cw-zone-stagger">
          <IdentityZone
            stats={stats}
            ratingSnapshot={ratingSnapshot}
            streak={streak}
            findings={findings}
            narrative={narrative}
            winRateByColor={winRateByColor}
          />
        </div>
      )}

      {showEvolutionBlock && (
        <div className="cw-zone-stagger mt-8 border-t border-[var(--cw-line)] pt-8" style={{ animationDelay: '80ms' }}>
          <ZoneHead eyebrow="How you've evolved" title="Progress & milestones" />
          {ratingTrajectory && acplTrajectory && (
            <EvolutionZone ratingTrajectory={ratingTrajectory} acplTrajectory={acplTrajectory} />
          )}
          {milestones && <MilestonesRow milestones={milestones} />}
          <CareerHighlight games={games} />
        </div>
      )}

      {!loading && !error && findings && (
        <div className="cw-zone-stagger" style={{ animationDelay: '160ms' }}>
          <CoachingZone findings={findings} cached={cached} />
        </div>
      )}
    </div>
  )
}
