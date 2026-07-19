export default function Slider({
  id,
  label,
  min,
  max,
  value,
  onChange,
}: {
  id?: string
  label: string
  min: number
  max: number
  value: number
  onChange: (value: number) => void
}) {
  return (
    <label htmlFor={id} className="block text-xs text-[var(--cw-muted)]">
      <span className="flex items-center justify-between">
        <span>{label}</span>
        <span className="font-mono text-[var(--cw-text)]">{value}</span>
      </span>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 block w-full accent-[var(--cw-copper)]"
      />
    </label>
  )
}
