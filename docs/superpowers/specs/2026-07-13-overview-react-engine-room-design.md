# Overview Page (React) — Production Visual Design, Engine Room — Design

Status: brainstormed and approved by the user (live mockup, browser companion); pending written self-review + user sign-off on this doc before an implementation plan is written.
Date: 2026-07-13
Branch: worktree-frontend-spike (`.claude/worktrees/frontend-spike`)

## Context

The React port of Overview was built as five independent, sequenced slices
(Identity, Milestones, Evolution charts, Career Highlight, Coaching —
see `2026-07-12-overview-identity-zone-port-design.md` through
`2026-07-13-overview-coaching-zone-design.md`), each explicitly deferring
visual polish: "styled with Tailwind against the existing `@theme` tokens,
no pixel parity attempted." The result is functionally complete but
visually flat — a single `p-8` column of bare text/grids with no
established typographic hierarchy, spacing rhythm, or card treatment, and
the live engine-status strip was never built at all.

This spec is that deferred design pass, covering the whole page (five
existing zones + the new engine-status strip) in one pass rather than
per-slice, because a coherent visual system has to be designed holistically
— retrofitting it zone-by-zone would mean redoing earlier zones anyway.

**Mid-brainstorm discovery that reshaped this spec:** the *Streamlit*
Overview page (`dashboard/overview_view.py`, main repo, branch
`feature/eval-dedup-cache`) was independently redesigned the same day
under a "Engine Room" visual identity — copper/cyan accents, a three-font
system, an animated eval-bar rail, milestone-tick chips, severity dots —
per `2026-07-12-overview-engine-room-redesign-design.md`, shipped in
commits `7e81a40`/`17087c8`. It shares the same three-zone information
architecture (Identity/Evolution/Coaching) the React port already
independently arrived at, styled with a completely different, unrelated
palette. **User decision: adopt Engine Room's visual identity into the
React Overview page** (not the flat-editorial gold-toned system this
session had designed and validated first) — reusing its exact tokens,
typography, and component patterns, applied to the content this session
had already scoped, rather than either designing a third system or
reverting to Engine Room's original scope. Engine Room's own CSS also
disagreed with its own design doc in one place — see "Eval rail" below —
this spec follows the shipped code, not the doc, where they diverge.

## Goals

- Give the React Overview page one coherent, production-grade visual
  system — typography scale, spacing rhythm, color usage — replacing the
  current bare-Tailwind, no-design-pass styling.
- Reuse Engine Room's already-shipped, already-user-approved visual
  identity (tokens, three-font pairing, zone-head/trait-tag/milestone/
  balance-row/eval-rail component patterns) rather than inventing a new
  one, for a real reason: it already went through three rounds of live
  mockup iteration and user approval on the Streamlit side.
- Fill the page's real excess horizontal whitespace (flagged directly by
  the user against the first flat-editorial pass) with genuinely relevant,
  cheap content additions — not decorative filler. Every addition below
  was checked against the real backend before being proposed.
- Finally build the engine-status strip, the one Overview piece never
  ported, preserving the "never eagerly start Stockfish" constraint the
  Streamlit version was fixed for today (commit `1d77d03`).

## Non-goals (explicit)

- **No app-wide token rollout.** Engine Room stays scoped to the Overview
  page only, exactly as it's scoped in Streamlit (its own design doc's
  Non-goals: "additive... not touching global `theme.py` tokens"). `Shell.tsx`,
  `Sidebar.tsx`, `CommandPalette.tsx`, and every other already-built React
  page keep today's shared gold/`@theme` tokens. Redesigning those is a
  separate, larger, not-yet-scoped decision — explicitly declined for this
  pass.
- **No column-based page restructuring.** Two two-column layout directions
  were mocked and explicitly rejected by the user in favor of staying
  single-column with more content per zone. This spec does not revisit
  that.
- **Recent form ticker stays dropped.** Engine Room's Streamlit Evolution
  zone includes a "Recent form" ticker table; the React Overview's own
  2026-07-13 decision to drop Recent form entirely was reaffirmed
  explicitly during this session's reconciliation — adopting Engine Room's
  *visual language* does not mean adopting every content item it happens
  to also include.
- **No Game Detail, no per-card view-game affordance.** Career Highlight
  expands from 1 game to 3; each inert "View this game" button (the
  existing single-card pattern) is dropped entirely rather than tripled,
  since three disabled buttons in a row is worse than none. Game Detail
  remains fully unscheduled (Phase 3 board-heavy work).
- **No per-game eval-rail data.** The Engine Room design doc's own text
  describes the eval rail as driven by "the featured game's real final
  evaluation/win-probability" — but the shipped implementation
  (`overview_view.py:146-152`) actually renders `stats["win_pct"]`, the
  player's overall career win rate, with no per-game data at all. This
  spec ports the shipped behavior, not the doc's original, unbuilt
  ambition — meaning **zero new backend work** for the rail: `win_pct` is
  already part of `useOverviewData()`'s existing payload.
- **No pixel-parity claim.** Streamlit's `st.columns`/`st.container(border=True)`
  primitives don't map 1:1 to React/Tailwind. This spec defines the
  React-native structure that reproduces Engine Room's visual result, not
  a literal DOM port.

## Design

### Visual tokens — Overview-scoped, not global

New CSS custom properties, defined under a `.cw-overview` wrapper class
(applied to `OverviewPage`'s root `<div>`) in `frontend/src/index.css` —
**not** added to the shared `@theme` block, so they cannot leak into or
override Shell/Sidebar/any other page's existing `--color-*` tokens:

| Token | Value | Role |
|---|---|---|
| `--cw-canvas` | `#0B0F14` | Overview page background (overrides the shared `bg` only within `.cw-overview`) |
| `--cw-panel` / `--cw-panel-2` | `#131A22` / `#0F141B` | card/panel surfaces, two elevation tiers |
| `--cw-copper` | `#E08A3C` | primary accent — CTAs, active/focus tone, eval-rail fill, "focus areas" |
| `--cw-cyan` | `#4FB8C4` | secondary accent — eyebrow labels, engine-status "connected" dot |
| `--cw-text` | `#ECEEF0` | primary text |
| `--cw-muted` | `rgb(236 238 240 / 0.6)` | secondary text |
| `--cw-line` / `--cw-line-soft` | `#232B37` / `#1a212b` | hairline dividers, card borders |

**Reused unchanged, from the existing shared `@theme` (not redefined):**
`--color-positive` (`#6FA98C`) and `--color-negative` (`#B0584F`) — same
values Engine Room's own CSS reuses from `theme.py` for win/loss/strength
semantics, so no new duplication here.

**Typography — three-way pairing**, matching Engine Room exactly:
- Condensed grotesk (structure: zone titles, trait tags, balance-row
  titles, milestone labels) — add `--font-condensed: "Archivo Narrow","Arial Narrow",sans-serif`
  to the shared `@theme` block (safe globally: an unused Tailwind font
  utility until referenced) → `font-condensed`.
- Monospace (all numerals: stat tiles, rating, eyebrow labels, engine
  strip, milestone dates) — Tailwind's built-in `font-mono` (its default
  stack — `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas` — is a
  close-enough match to Engine Room's `SF Mono/JetBrains Mono/Consolas`
  chain; no new token needed).
- Serif (the one remaining prose element — the narrative/executive
  summary) — add `--font-cw-serif: Georgia,"Iowan Old Style",serif` to
  `@theme` → `font-cw-serif`.

Fallback-chain system fonts only, zero webfont/packaging risk — same
reasoning the Streamlit design doc already used.

### Component patterns

**Zone head** (reused for Identity/Evolution/Coaching — Milestones and
Career Highlights are sub-sections within Evolution, not their own zone
heads): `flex items-baseline gap-2`, containing a `font-mono text-[10px]
uppercase tracking-[0.1em] text-[var(--cw-cyan)]` eyebrow span, a
`font-condensed font-bold text-[15px] text-[var(--cw-text)]` title, and a
`flex-1 h-px bg-[var(--cw-line)]` trailing rule. Copy ported verbatim from
the shipped Streamlit strings:
- Identity: eyebrow "Who you are", title "Your chess identity"
- Evolution: eyebrow "How you've evolved", title "Progress & milestones"
- Coaching: eyebrow "What to work on", title "Your coaching plan"

**Engine-status strip** *(new)* — sits above the first zone head, no zone
head of its own (matches Streamlit — it's a utility strip, not a content
zone). `flex items-center gap-2 font-mono text-[11px] text-[var(--cw-muted)]`.
Dot: `w-1.5 h-1.5 rounded-full`, `bg-[var(--cw-cyan)]` when connected,
`bg-[var(--cw-line)]` when not (quiet/neutral, not alarming — matches the
Streamlit `.dot.off` treatment). Text: `Chesswright v{app_version} ·
{total_games} games · {analyzed_games} analyzed · {engine_text}`, where
`engine_text` is `Stockfish {version}` or `Engine not detected`.
Renders nothing while loading (no flicker on a quiet utility bar).

Backend: new `GET /api/overview/engine-status` → `{"connected": bool,
"version": str | null, "app_version": str}`, thin wrapper over
`live_engine.get_engine_status_summary()` plus `dashboard/version.py`'s
`__version__` (a plain, Streamlit-independent module — safe to import
into `api/main.py`). **Must not** call `get_engine_service()` as first
caller — same read-only constraint the Streamlit strip was just fixed for
(commit `1d77d03`); `get_engine_status_summary()` already enforces this
internally, so the wrapper just needs to not add its own eager call.
`total_games`/`analyzed_games` are not duplicated here — the frontend
composes the full strip text from this endpoint plus the `stats` field
`useOverviewData()` already fetches.

**Identity zone** — eval-rail + trait tags + rating/streak block, side by
side (`flex gap-4`); executive summary below as a blockquote; 6 stat
tiles below that.

- *Eval rail*: `w-3 h-20 relative bg-[var(--cw-panel-2)] border
  border-[var(--cw-line)] rounded-sm overflow-hidden`, a horizontal
  midline (`absolute top-1/2 inset-x-0 h-px bg-[var(--cw-text)]/28`), and
  a fill div (`absolute inset-x-0 bottom-0 w-full`, gradient
  `linear-gradient(180deg,var(--cw-copper),#a95f22)`) whose height is
  `stats.win_pct` (already fetched, 0 if null) — **zero new backend
  work**. CSS transition/`@keyframes` rise from 50% on mount, respecting
  `prefers-reduced-motion` (`transition-none` fallback), matching the
  Streamlit version's own reduced-motion media query.
- *Trait tags*: unchanged selection logic (`topTraitTags`), restyled —
  `font-condensed text-[10px] font-semibold px-2.5 py-1 rounded
  bg-[var(--cw-panel)] border border-[var(--cw-line)] text-[var(--cw-text)]`
  (rounded-4px chip, not today's `rounded-full` pill).
- *Rating*: `font-mono tabular-nums text-2xl font-semibold
  text-[var(--cw-text)]`, trend span colored `text-positive`/`text-negative`
  (shared tokens, unchanged logic).
- *Executive summary*: replaces the current plain `<p>` — `italic text-xs
  leading-relaxed text-[var(--cw-muted)] max-w-[60ch] border-l-2
  border-[var(--cw-line)] pl-3 font-cw-serif`.
- *Stat tiles*: `grid grid-cols-6 gap-5` (existing 4: Total, Analyzed, Win
  rate, ACPL — unchanged data/formatting), **+2 new**: "As White" / "As
  Black" (`win_pct.toFixed(1)}%`). Tile numbers: `font-mono tabular-nums
  text-sm font-semibold text-[var(--cw-text)]`.
  - Backend: new `GET /api/overview/win-rate-by-color`, thin wrapper over
    the already-existing-but-currently-unused `data.get_win_rate_by_color`,
    no caching (single indexed query, same cost bar as `current-streak`).
    New `useWinRateByColor` hook, independent (no dependency on other
    Overview fields, same pattern as `useMilestones`).

**Evolution zone** — progress panel, then milestones row, then career
highlights.

- *Progress panel*: `bg-[var(--cw-panel)] border border-[var(--cw-line)]
  rounded-md p-3` (Engine Room's bordered-container treatment, the one
  place this design uses an actual card background rather than a bare
  hairline section). Contains a `font-condensed text-[11px]
  text-[var(--cw-text)]` sub-heading "Rating, accuracy & activity over
  time", then `grid grid-cols-3 gap-4`:
  1. Rating-by-year line, color `var(--cw-copper)` (was accent-gold —
     retint to stay internally consistent within Overview).
  2. ACPL-by-year line, color shared `--color-negative` (unchanged —
     Engine Room's own CSS reuses `theme.NEGATIVE` here too).
  3. **New** games-per-year volume bar chart, color `var(--cw-muted)` —
     zero new backend cost, `get_rating_trajectory` already returns
     `n_games` per year, currently unused by the frontend. New
     `barChart()` helper in `lib/charts.ts`, same generic-`keyof T` shape
     as `lineChart()`.
  Coverage-skew caption unchanged, styled `text-[var(--cw-muted)] text-xs`.
- *Milestones*: **no content change** (still `limit=4`, no
  progress-teaser) — restyled only, to Engine Room's tick pattern:
  `inline-flex items-center gap-1.5 bg-[var(--cw-panel)] border
  border-[var(--cw-line)] rounded px-2.5 py-1.5`, a `w-1.5 h-1.5
  rounded-full bg-[var(--cw-copper)]` tick, `font-condensed text-[10px]`
  label, `font-mono text-[9px] text-[var(--cw-muted)]` date.
- *Career highlights*: **renamed from singular**, top 3 games by
  `drama_score` instead of 1 — one-line backend change
  (`explorer_df.head(3)` instead of `.iloc[0]`), same endpoint, same 60s
  TTL cache. Rendered as `flex gap-3`, each card
  `flex-1 bg-[var(--cw-panel)] border border-[var(--cw-line)] rounded-md
  p-3`: badge chips (`font-condensed text-[8px] text-[var(--cw-copper)]
  bg-[var(--cw-panel-2)] rounded px-1.5 py-0.5`) + `vs. {opponent} ({result})`
  text. Shared badge legend caption renders once below all 3 cards, not
  per-card. **No "View this game" button** on any card (dropped, see
  Non-goals).

**Coaching zone** — 3-column balance split, ranked focus list, CTA row.

- *Balance columns*: `grid grid-cols-3 gap-5` — Strengths / Mixed / Focus
  areas, splitting `findings` directly by `polarity` (`'strength'`,
  `'mixed'`, `'weakness'`) instead of today's `splitByPolarity` that folds
  mixed into weaknesses. Column headers: `font-condensed text-[9px]
  uppercase tracking-[0.12em] font-bold`, colored `text-positive` /
  `text-[var(--cw-muted)]` / `text-[var(--cw-copper)]` respectively. Each
  row: a `w-1.75 h-1.75 rounded-full mt-1` marker (same three colors) +
  `font-condensed text-[11px] font-semibold` title + `text-xs
  text-[var(--cw-muted)]` detail — this is the "balance-row" pattern from
  Engine Room's CSS, ported directly.
  - **This is a preview-grid change only.** The ranked focus-area list
    below keeps its current eligibility (`weakness` OR `mixed`, sorted by
    severity, capped at 3) — unchanged logic, zero regression risk on the
    CTA copy it drives.
- *Ranked list*: `bg-[var(--cw-panel)] border border-[var(--cw-line)]
  rounded-md p-3`, each row: severity dots (`inline-flex gap-0.5`, 3×
  `w-1.5 h-1.5 rounded-full`, `bg-[var(--cw-copper)]` on / `bg-[var(--cw-line)]`
  off — was gold/negative before, now copper), title, detail, and the
  existing destination link.
- *CTA + quick links*: unchanged structure and logic, retinted from
  `accent-gold` to `var(--cw-copper)` for internal Overview consistency
  (border, text, hover states).

### States (empty/error/loading)

Unchanged rules throughout, just restyled: Milestones/Career
Highlights/Coaching keep their existing "render nothing on empty or
error" collapse. Stat tiles (existing + new White/Black win-rate tiles)
show `--` on `null`, matching ACPL/win-rate's existing convention. Career
Highlights renders however many of the top 3 actually exist (not padded).
Engine strip renders nothing until its own fetch resolves.

### Responsive behavior

The window is an embedded native webview, not an arbitrarily-resized
browser tab, but can still be resized. Stat tiles, the 3-chart Evolution
grid, the 3-card highlights row, and the 3-column Coaching grid each get a
narrower-width fallback (e.g. `grid-cols-6 sm:grid-cols-3`-style patterns)
rather than assuming full width always holds — exact breakpoints are a
plan-time detail.

## Data requirements — summary

| Endpoint | Status | Cost |
|---|---|---|
| `GET /api/overview/engine-status` | New | Thin wrapper, `live_engine.get_engine_status_summary()` + `version.__version__`, no caching |
| `GET /api/overview/win-rate-by-color` | New | Thin wrapper over existing-but-unused `data.get_win_rate_by_color`, no caching |
| `GET /api/overview/career-highlight` | Existing, one-line change | `explorer_df.head(3)` instead of `.iloc[0]`, same cache |
| Games-per-year volume chart | Zero new cost | `n_games` field already returned by `get_rating_trajectory`, currently unused frontend-side |
| Eval-rail fill | Zero new cost | `stats.win_pct`, already part of `useOverviewData()`'s existing payload |
| Coaching 3-column split | Zero new cost | Same `findings` array already fetched, split by `polarity` client-side |
| Milestones, other Coaching/CTA logic | Unchanged | No backend changes |

## Open items for the implementation plan to resolve

- Exact Tailwind breakpoint values for the four responsive grids
  (stat tiles, Evolution charts, highlight cards, Coaching columns).
- Whether `barChart()` in `lib/charts.ts` should live alongside or replace
  any part of `lineChart()`'s shared axis-theming helpers (both will need
  `--cw-*` tokens instead of the shared `THEME` object where Overview
  differs from other charted pages — Evolution's rating/ACPL lines now use
  `var(--cw-copper)`/shared negative, not `THEME.accentGold`).
- Confirm whether `.cw-overview`'s scoped tokens should be plain CSS custom
  properties (as specced) or a Tailwind v4 `@theme` scoped variant, once
  the plan is checking real Tailwind v4 scoping support against the
  installed version.
