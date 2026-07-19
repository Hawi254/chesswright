// Brand mark: a miniature of the same two-tone "eval bar" signature used
// for career win-rate on Overview (IdentityZone) -- reused here instead of
// a generic chess-piece glyph so the app's one distinctive visual idea
// carries through its own chrome, not just one page.
export default function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span
        aria-hidden="true"
        className="relative h-[18px] w-[7px] overflow-hidden rounded-[1px] border border-[var(--cw-line)] bg-[var(--cw-canvas)]"
      >
        <span
          className="absolute inset-x-0 bottom-0 block"
          style={{ height: '65%', background: 'linear-gradient(180deg, var(--cw-copper), #a95f22)' }}
        />
        <span className="absolute inset-x-0 top-1/2 h-px bg-[var(--cw-text)]/30" />
      </span>
      <span className="font-condensed text-sm font-bold uppercase tracking-[0.14em] text-[var(--cw-text)]">
        Chesswright
      </span>
    </span>
  )
}
