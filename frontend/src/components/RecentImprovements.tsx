import ZoneHead from './ZoneHead'
import type { Milestone } from '../hooks/useMilestones'

export default function RecentImprovements({ milestones }: { milestones: Milestone[] }) {
  return (
    <div data-testid="recent-improvements" className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="Recent improvements" title="What's unlocked lately" />
      {milestones.length === 0 ? (
        <p className="mt-4 text-xs text-[var(--cw-muted)]">
          Nothing unlocked yet — keep playing and analyzing.
        </p>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {milestones.map((m) => (
            <div
              key={m.achievement_id}
              className="inline-flex items-center gap-1.5 rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] px-2.5 py-1.5"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--cw-copper)]" />
              <span className="font-condensed text-[10px] text-[var(--cw-text)]">{m.name}</span>
              <span className="font-mono text-[10px] text-[var(--cw-muted)]">
                {m.unlocked_at.slice(0, 10)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
