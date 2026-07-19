import type { ReactNode } from 'react'
import type { PointsHeadlineData } from '../lib/pointsHeadline'

export default function PointsHeadline({ headline }: { headline: PointsHeadlineData | null }) {
  if (!headline) return null
  const { bucket, nGames, leaked, totalLeaked, detail } = headline
  const games = `${nGames} game${nGames === 1 ? '' : 's'}`

  let body: ReactNode
  if (bucket === 'failed_conversion') {
    body = (
      <>
        Your biggest leak is <strong>failed conversions</strong>: {games} where you reached a winning
        position and gave back <strong>{leaked.toFixed(0)} of your {totalLeaked.toFixed(0)} leaked points</strong>.
        {detail && <> {detail}</>}
      </>
    )
  } else if (bucket === 'missed_swindle') {
    body = (
      <>
        Your biggest leak is <strong>missed swindles</strong>: in {games} your opponent handed the game
        back to even or better and it slipped away again — <strong>{leaked.toFixed(0)} of your{' '}
        {totalLeaked.toFixed(0)} leaked points</strong>.
      </>
    )
  } else {
    body = (
      <>
        Your biggest leak is <strong>failed holds</strong>: {games} that were still level in the
        middlegame but drifted into losses — <strong>{leaked.toFixed(0)} of your {totalLeaked.toFixed(0)}{' '}
        leaked points</strong>.
      </>
    )
  }

  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4 text-sm text-[var(--cw-text)]">
      <p>{body}</p>
    </div>
  )
}
