import { Button } from './ui/button'

export interface MaintenanceCardProps {
  headline: string
  buttonLabel: string
  onAction: () => void
  pending: boolean
  error: string | null
}

export default function MaintenanceCard({ headline, buttonLabel, onAction, pending, error }: MaintenanceCardProps) {
  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
      <p className="text-sm text-[var(--cw-text)]">{headline}</p>
      <Button className="mt-3" size="sm" onClick={onAction} disabled={pending}>
        {pending ? 'Working…' : buttonLabel}
      </Button>
      {error && <p className="mt-2 text-xs text-negative">{error}</p>}
    </div>
  )
}
