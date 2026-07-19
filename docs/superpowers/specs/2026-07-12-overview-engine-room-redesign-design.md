# Overview Page Redesign — "Engine Room" — Design

Status: pending user review of this doc (design itself approved as "a good starting point" via live mockup)
Date: 2026-07-12
Branch: feature/eval-dedup-cache

## Context

Overview (`dashboard/overview_view.py`, Phase 6c.4) is already the app's de
facto landing page — first page after onboarding, first sidebar nav item —
and already carries the right content: a career narrative, a top-finding
focus card, four headline stats, a "most dramatic game" teaser, three trend
chart panels, a coaching teaser, and quick-explore links. This design does
not add or remove what the page is about; it replaces the visual language
and reorganizes the layout.

Two problems drove this redesign, found by mocking the page live (as an
HTML/CSS artifact, not by reasoning abstractly):

1. **Visual identity felt generic.** The existing "Midnight Study" theme
   (`theme.py`) is deliberately dark, WCAG-validated, and quiet/literary —
   correct for the rest of the app, but a first cut at "make it stand out"
   still read as boxed `st.container(border=True)` cards with no real
   signature. Two bolder directions were mocked side-by-side as a live
   artifact; "Engine Room" (copper/cyan, instrument-panel register, an
   animated eval-bar rail as the signature element) was chosen over
   "Checkered Ledger" (brass/slate, board-square panel rhythm).
2. **The content itself was flat and front-loaded.** A full-width narrative
   blockquote hero ate a disproportionate amount of vertical space to say
   comparatively little, and everything after it was a single undifferentiated
   scroll of cards with no explicit hierarchy of what question each card was
   answering.

Direct follow-up instruction: reorganize the page around three real
questions instead of a flat scroll — **Who am I as a player? How have I
evolved? What should I improve next?**

Iterated 3x as a live Artifact mockup (initial two-concept comparison → app
chrome/density pass → three-zone information-architecture pass → production
polish pass covering brand mark, personalization, and craft-floor fixes).
User-approved the latest pass as "a good starting point."

## Goals

- Replace the current front-loaded single-column scroll with three explicit
  zones — **Identity**, **Evolution**, **Coaching** — each with its own
  labeled section head, each answering one of the three questions above.
- Adopt the "Engine Room" visual identity: a new copper/cyan accent pair
  (additive, Overview-scoped — see Non-goals), a three-way type pairing
  (condensed grotesk for structure, monospace for data/numerals, serif for
  the one remaining piece of narrative prose), hairline/ledger panel
  treatment replacing boxed `st.container(border=True)` defaults.
- Shrink the career-narrative quote from a full-width glowing hero down to a
  compact two-line executive summary, subordinate to a new identity strip
  (trait tags + rating).
- Surface **strengths**, not just the single top weakness. `get_career_findings()`
  already computes a `polarity` field that the current page never uses.
- Signature element: a vertical eval-bar rail spanning the content column,
  animating on page load from center to the real evaluation swing of the
  featured "career highlight" game.
- Add a milestones row (career achievements/badges) if — and only if — the
  underlying achievements read path is actually available (see Data
  requirements item 4; this is a real dependency check, not assumed).

## Non-goals (explicit)

- **A real, working `⌘K` global keyboard shortcut.** The mockup shows the
  hint visually; actually intercepting the keystroke needs a small JS
  injection with no existing precedent in this codebase. Out of scope here
  — the search box itself already exists (Global Search), this only touches
  how its entry point looks on Overview.
- **App-wide topbar/statusbar chrome.** The mockup renders a topbar
  (search + engine status) and statusbar (sync/version info) as part of
  Overview's own container for visual completeness. Rolling either out as
  *persistent chrome on every page* would mean touching `app.py`'s page
  shell globally — a much bigger blast radius than one page's redesign.
  Not assumed or scoped here.
- **A new identity-classification system.** "Trait tags" (e.g. "King's
  Indian specialist," "Time-pressure prone") are NOT a new taxonomy/ML
  classifier. They're the titles of the top 2-3 `polarity`-sorted findings
  already computed by `get_career_findings()`, reused as-is. If a finding's
  title doesn't read as a good tag verbatim, the right response is to drop
  that tag, not build a paraphraser.
- **New achievement types or notification delivery.** If the milestones row
  ships, it only reads the existing achievement catalog/unlock table.
  Matches the Notification Service non-goal already established in the
  Phase 6 Settings design (`2026-07-11-phase6-settings-design.md`) —
  delivery mechanism is a separate, unscoped decision.
- **Changing any global `theme.py` token.** New copper/cyan values are
  additive and scoped to a single Overview-only CSS wrapper class. Every
  other page keeps using the existing, WCAG-measured `POSITIVE`/`NEGATIVE`/
  `ACCENT_GOLD`/`BG` tokens exactly as they are today — nothing here touches
  shared chart theming.
- **A custom React/JS component.** Confirmed direction is styled native
  Streamlit — CSS injection through the same mechanism `theme.py` already
  uses, not a new component like the chessboard's.

## Design

### Visual tokens (additive, Overview-scoped only)

| Token | Value | Role |
|---|---|---|
| `--canvas` | `#0B0F14` | page background |
| `--panel` / `--panel-2` | `#131A22` / `#0F141B` | card surfaces, two elevation tiers |
| `--copper` | `#E08A3C` | primary accent — CTAs, active states, eval-rail fill |
| `--cyan` | `#4FB8C4` | secondary accent — "live data" (search, engine status, ACPL series) |
| `--text` / `--muted` / `--faint` | `#ECEEF0` at 100/60/36% | text hierarchy |
| `--line` / `--line-soft` | `#232B37` / `#1a212b` | hairline dividers, replacing boxed borders |

`POSITIVE`/`NEGATIVE` from the shared `theme.py` are reused unchanged for
win/loss/result semantics (badges, chips, ticker rows) — not redefined.

**Type**: condensed grotesk (structure — nav, labels, headings, buttons),
monospace (all numerals — stats, rating, eval readout, timestamps), serif
(the one remaining prose element — the two-line executive summary). Ship
with system-font stacks first (`"Archivo Narrow"/"Arial Narrow"` fallback
chain for display, `ui-monospace`/`"SF Mono"`/`"Cascadia Code"` fallback
chain for numerals, `Georgia`/`"Iowan Old Style"` fallback chain for the
summary) — zero packaging risk, matches how `theme.py` already handles
type today. Bundling a real webfont (e.g. via a `@font-face` file shipped
in the installer) is a separate future decision, same category of change
as the `markdown` dependency's `collect_all()` addition to both PyInstaller
specs — not needed for this design to ship.

### Layout — three zones, replacing the current flat scroll

**Zone 1 — "Who you are" (identity)**
Identity strip (2-3 trait-tag chips + current/peak rating + streak) → a
compact two-line executive summary (replaces the old full-width blockquote
hero) → the existing four-stat career-snapshot row (total games, analyzed,
win rate, ACPL — unchanged content, re-skinned only).

**Zone 2 — "How you've evolved" (evolution)**
One consolidated progress card (rating trajectory + ACPL trend together,
was two separate cards) → milestones row (conditional, see Data
requirements #4) → recent-form ticker (last 4-5 games: result/opponent/date/
rating delta) → the existing "career highlight" game teaser (renamed from
"most dramatic game on record," same underlying data).

**Zone 3 — "What to work on" (coaching)**
Strengths vs. focus-areas, two columns side by side (NEW — both directions
of `polarity`, not just weaknesses) → a ranked, severity-dotted coaching
list of the top 3 findings (replaces the single oversized focus card) → one
contextual CTA tied to the actual top weakness, plus the existing
quick-explore row as a secondary strip.

Each zone has a real eyebrow label naming the question it answers — this is
a genuine three-part narrative arc (who → how → what next), not decorative
sequence numbering.

### Signature elements

- **Eval rail**: a vertical bar along the content column's left edge,
  styled like a real chess-engine evaluation bar. Fill height computed
  server-side (Python) from the featured game's real final evaluation/
  win-probability, rendered as an inline `style` percentage, animated via a
  pure CSS transition from center (50%) on page load — no JS required. A
  fixed center reference line marks "even."
- **Brand mark**: a small static three-bar SVG in the sidebar, built from
  the same visual language as the eval rail (three bars, varying heights,
  copper/cyan/neutral) — one coherent motif reused as the page's signature
  AND its wordmark accent, rather than two unrelated decorative elements.

## Data requirements — what's ready vs. new work

Confirmed by direct inspection of `dashboard/data/` (line numbers as of this
session):

1. **Findings (strengths + weaknesses)** — READY, zero new backend work.
   `get_career_findings()` (`dashboard/data/insights.py:474`) already
   returns `polarity` (`"strength"`/`"weakness"`/`"mixed"`/`"neutral"`)
   alongside `severity`, `category`, `title`, `headline`, `detail`. Zone
   3's strength/focus-area split and severity-ranked coaching list are
   display-layer work over data that already exists — filter on `polarity`,
   sort by `severity`.
2. **Current + peak rating** — NEW, small. No existing query returns
   either. `get_rating_trajectory()` (`dashboard/data/overview.py:4`) only
   returns yearly averages. Needs one small new query, natural home
   alongside it.
3. **Current win/loss streak** — NEW, small-medium. `achievements.py:202`'s
   `_longest_win_streak_end()` computes the longest-EVER streak for
   achievement-threshold checks, not the active/current streak, and isn't
   exposed to the dashboard data layer. Needs a new query.
4. **Milestones row** — NEW, medium, **with a dependency check that must
   happen before this is scoped as "just a query."** The achievements write
   path (`achievements.py`'s catalog + the `achievements_unlocked` table via
   migration `0039`) exists in the working tree and appears live
   (`backfill_achievements.py` + tests reference it), but **zero dashboard
   code reads it today** — grep confirmed no references to
   `achievements_unlocked` or the catalog anywhere under `dashboard/`. Per
   project memory, an "Achievements Service" build was completed but NOT
   YET MERGED/PUSHED as of 2026-07-11. **Before building on this: confirm
   whether `achievements.py`/migration `0039` are actually committed on
   `feature/eval-dedup-cache`, or whether this is that same unmerged work
   still sitting in the working tree.** If confirmed available, this needs
   one new `get_unlocked_achievements`-style join (catalog + unlock table,
   ordered by `unlocked_at`). If not confirmed, cut the milestones row from
   the first implementation pass rather than building on unmerged ground.
5. **Identity trait tags** — NEW, but deliberately cheap by design (see
   Non-goals): reuse the top 2-3 `polarity`-sorted findings' own titles from
   item 1, no new derivation logic.
6. **Recent-form ticker** — MOSTLY READY. `get_game_explorer_table()`
   (`dashboard/data/game_explorer.py:87`) already returns
   `outcome_for_player`, `opponent_name`, `utc_date`. It does not currently
   select the player's own post-game `player_rating`, so a per-game rating
   delta needs one small addition (select the column, compute delta against
   the prior game).

## Technical approach

- Styled native Streamlit — CSS injection via the same mechanism `theme.py`
  already uses app-wide, not a new custom component.
- All new CSS scoped under one Overview-only wrapper class (e.g.
  `.cw-overview-eng`), so it cannot leak into or override any other page,
  and so the existing global `theme.py` tokens (WCAG ratios already
  measured and documented) stay untouched for every other page's charts and
  metrics.
- Eval-rail fill percentage computed in Python from real per-game data,
  rendered as an inline `style` attribute; the animation itself is a pure
  CSS `@keyframes`/transition, no JS.
- The mockup's sticky scroll-fade effect needs a quick live check against
  Streamlit's actual scrolling DOM structure before being relied on —
  the static mockup's `.main` scroll container is a stand-in, not a
  guarantee Streamlit's real block-container nests the same way.

## Open items for the implementation plan to resolve

- Resolve the achievements-table commit-status question (Data requirements
  #4) before deciding whether the milestones row ships in the first pass.
- Decide whether "current streak" should be all-games or analyzed-games-only
  — this app has an established pattern of disclosing analysis-coverage
  skew explicitly (see Overview's existing ACPL/progress-by-month coverage
  captions); a streak stat should follow the same honesty discipline rather
  than silently picking one.
- Confirm the eval rail's data source (per-move win-probability/eval) is
  actually populated for whichever game Overview would feature at render
  time — same coverage-honesty check the rest of the app already applies.
- Consider splitting implementation into two passes: (a) visual/layout
  re-skin using only already-ready data (findings/polarity, existing
  charts, existing game-explorer fields), and (b) the four small-to-medium
  new queries (current/peak rating, streak, milestones, rating-delta
  ticker column) as a deliberate follow-up, rather than one large unit.
