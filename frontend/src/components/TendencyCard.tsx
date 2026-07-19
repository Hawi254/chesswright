export interface TendencyCardProps {
  label: string
  headline: string
  detail: string
  onClick: () => void
}

export default function TendencyCard({ label, headline, detail, onClick }: TendencyCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex-1 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4 text-left transition-colors hover:border-[var(--cw-copper)]/50"
    >
      <div className="font-condensed text-[11px] uppercase tracking-[0.08em] text-[var(--cw-copper)]">
        {label}
      </div>
      <p className="mt-1.5 text-sm text-[var(--cw-text)]">{headline}</p>
      <p className="mt-1 text-xs text-[var(--cw-muted)]">{detail}</p>
    </button>
  )
}
