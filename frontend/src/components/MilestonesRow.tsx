import type { Milestone } from '../hooks/useMilestones'

export default function MilestonesRow({ milestones }: { milestones: Milestone[] }) {
  if (milestones.length === 0) return null

  return (
    <div className="mt-6">
      <h2 className="text-xs uppercase tracking-wide text-text-muted">Milestones</h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {milestones.map((m) => (
          <div
            key={m.achievement_id}
            className="rounded border border-bg-secondary bg-bg-secondary/40 px-3 py-1.5 text-sm"
          >
            <span className="text-text">{m.name}</span>
            <span className="ml-2 text-xs text-text-muted">{m.unlocked_at.slice(0, 10)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
