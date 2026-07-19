import type { ReactNode } from 'react'

export interface EndingStatTileProps {
  label: string
  value: string | null
  detail?: string
  tone?: 'default' | 'negative'
  children?: ReactNode
}

export default function EndingStatTile({ label, value, detail, tone = 'default', children }: EndingStatTileProps) {
  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
      <div className="font-condensed text-[11px] uppercase tracking-[0.08em] text-[var(--cw-muted)]">{label}</div>
      {value === null ? (
        <p className="mt-1.5 text-sm text-[var(--cw-muted)]">Not enough games yet.</p>
      ) : (
        <>
          <p className={`mt-1.5 text-xl font-semibold ${tone === 'negative' ? 'text-negative' : 'text-[var(--cw-text)]'}`}>
            {value}
          </p>
          {detail && <p className="mt-1 text-xs text-[var(--cw-muted)]">{detail}</p>}
          {children && <div className="mt-2">{children}</div>}
        </>
      )}
    </div>
  )
}
