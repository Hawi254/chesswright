import { THEME } from '../lib/theme'

export default function WaffleStat({ percent }: { percent: number }) {
  const filled = Math.min(100, Math.max(0, Math.round(percent)))
  const cells = Array.from({ length: 100 }, (_, i) => i < filled)

  return (
    <div
      className="grid grid-cols-10 gap-[2px]"
      role="img"
      aria-label={`${filled}% explained`}
    >
      {cells.map((isFilled, i) => (
        <span
          key={i}
          data-cell
          data-filled={isFilled}
          className="h-2 w-2 rounded-[1px]"
          style={{ backgroundColor: isFilled ? THEME.accentGold : THEME.textMuted }}
        />
      ))}
    </div>
  )
}
