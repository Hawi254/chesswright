export interface VariationPanelProps {
  active: boolean
  branchPly: number | null
  sans: string[]
  step: number
  onStepTo: (n: number) => void
  onExit: () => void
  onDiscard: () => void
}

function formatSanLine(branchPly: number, sans: string[], step: number): string {
  if (step === 0) return 'Branch point'
  let turn: 'w' | 'b' = branchPly % 2 === 1 ? 'b' : 'w'
  let moveNumber = Math.floor(branchPly / 2) + 1
  const parts: string[] = []
  for (let i = 0; i < step; i++) {
    const san = sans[i]
    if (turn === 'w') {
      parts.push(`${moveNumber}. ${san}`)
    } else if (i === 0) {
      parts.push(`${moveNumber}… ${san}`)
    } else {
      parts.push(san)
    }
    if (turn === 'b') moveNumber += 1
    turn = turn === 'w' ? 'b' : 'w'
  }
  return 'Line: ' + parts.join(' ')
}

export default function VariationPanel({
  active,
  branchPly,
  sans,
  step,
  onStepTo,
  onExit,
  onDiscard,
}: VariationPanelProps) {
  if (!active || branchPly === null) return null

  const moveNumberLabel = Math.floor((branchPly + 1) / 2)

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <div className="flex items-center justify-between">
        <p className="font-condensed text-xs text-[var(--cw-text)]">
          Variation from move {moveNumberLabel} — {step} of {sans.length} moves
        </p>
        <button type="button" onClick={onExit} className="font-condensed text-xs text-[var(--cw-copper)]">
          Exit
        </button>
      </div>
      <p className="mt-2 font-mono text-xs text-[var(--cw-muted)]">{formatSanLine(branchPly, sans, step)}</p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={step === 0}
          onClick={() => onStepTo(step - 1)}
          className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
        >
          {'< Prev'}
        </button>
        <button
          type="button"
          disabled={step >= sans.length}
          onClick={() => onStepTo(step + 1)}
          className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
        >
          {'Next >'}
        </button>
        <button
          type="button"
          onClick={onDiscard}
          className="ml-auto rounded border border-negative px-2 py-1 font-condensed text-xs text-negative"
        >
          Discard variation
        </button>
      </div>
    </div>
  )
}
