export default function ZoneHead({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--cw-cyan)]">
        {eyebrow}
      </span>
      <span className="font-condensed text-[15px] font-bold text-[var(--cw-text)]">{title}</span>
      <span className="h-px flex-1 bg-[var(--cw-line)]" />
    </div>
  )
}
