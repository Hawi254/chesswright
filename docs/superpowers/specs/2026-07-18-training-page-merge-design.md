# Fold Drill Export, Training Queue, and SRS Drills into one "Training" page — Design

Status: approved by user, pending self-review + doc-review gate
Date: 2026-07-18
Branch: `feature/eval-dedup-cache` (current branch)

## Context

Chesswright today has three separate Explore-group pages that form one
conceptual pipeline: spot a weakness (**Training Queue**), turn it into a
practice set (**Drill Export**), and drill it with spaced repetition
(**SRS Drills**, Pro-only). All three currently exist only in the legacy
Streamlit dashboard (`dashboard/training_queue_view.py`,
`dashboard/drill_export_view.py`, `dashboard/srs_drill_view.py` — the last
is a Pro-gate stub whose real UI is `chesswright_pro/srs_drills.py` in the
private repo). None of the three has been ported to the React/Vite
rewrite yet — they're still `PageStub` placeholders in
`worktree-frontend-spike`'s `navConfig.ts`/`navCandidates.ts`. This design
replaces what would otherwise have been three separate React ports with one
merged page, and also renames the user-facing "SRS Drills" term.

Investigation turned up one important existing gap: `drill_export_view.py`
and `dashboard/data/srs.py` are entirely disconnected today. Exported
positions only ever become PGN/Anki downloads
(`drills_to_pgn_study`/`drills_to_anki_csv`); nothing calls `add_cards()`
from the export flow. `dashboard/data/drills.py` already has a
`build_drill_cards()` function whose docstring describes "add_cards()-ready"
output, but it has zero production callers anywhere (main worktree, spike
worktree, or `api/`) — only exercised by
`tests/integration/test_drills.py`. This design finishes that wiring as
part of the merge, since it's the actual point of putting these three in
one flow.

## Goals

- One page, nav-labeled **"Training"**, replaces the three separate Explore
  nav entries (Drill Export, Training Queue, SRS Drills ✦).
- Three tabs — **Weaknesses**, **Build Set**, **Review** — mirroring the
  find → build → drill pipeline, with **Review** as the default tab (highest-
  frequency return action: "drill today's due cards").
- Rename the user-facing term "SRS Drills" to **"Review"** throughout nav,
  tab labels, and surrounding copy (empty states, upsell text).
- Wire Build Set → Review together: a new Pro-only "Add to Review deck"
  action on the Build Set tab calls `build_drill_cards()` → `add_cards()`,
  finishing the connection that was clearly anticipated but never built.
- Preserve today's free/Pro boundary exactly (Weaknesses + Build Set free,
  Review Pro-gated) — just move the ✦ badge from the nav item onto the
  Review tab specifically, since most of the merged page is free.

## Non-goals (explicit)

- **No changes to the SM-2 algorithm or the Pro review-taking UI.**
  `chesswright_pro/srs_drills.py`'s board/reveal/rating flow is reused
  as-is.
- **No backend schema changes** beyond the one new Build→Review wiring
  call (`add_cards()` already exists and is exercised by tests).
- **No changes to Insights.** It keeps its full finding-action set
  (including non-drill actions like "Scout opponent"); those actions are
  dropped only from the new Weaknesses tab, not from Insights itself.
- **No internal renaming.** `srs.py`, `chesswright_pro/srs_drills.py`,
  `add_cards()`, DB table/column names, and other code identifiers keep
  the "SRS" name — only user-facing text changes. Renaming internals is a
  separate, higher-risk operation this design doesn't force.
- **No rework of existing React code.** Since none of the three source
  pages have been ported yet, there is no prior React implementation to
  reconcile with.

## Architecture

### Nav & routing

One nav entry, **"Training"**, in the Explore group (where the three
separate entries used to sit), no ✦ badge on the nav item itself. The page
owns three tabs, most likely `?tab=weaknesses|build|review` for
shareability, defaulting to `review` when no query param is present.

### Tab 1 — Weaknesses (replaces Training Queue)

Same severity-sorted findings list, sourced from
`get_career_findings()` — no data-layer changes. Narrowed compared to
today's Training Queue: only the drill-relevant action ("Build practice
set from this weakness") is shown per finding. Clicking it pre-fills the
Build Set tab via the existing `_drill_preset` mechanism and switches tabs.
Other finding actions (Scout opponent, etc.) are dropped from this tab —
they remain available on Insights, which shows the same findings.

### Tab 2 — Build Set (replaces Drill Export)

Unchanged from today: three position-source checkboxes (missed
tactics/motifs, decisive moments, repertoire holes), max-positions slider,
preview, backed by `dashboard/data/drills.py`'s existing position builders
(`get_motif_drill_positions`, `get_decisive_moment_positions`, repertoire-
hole equivalent). Both existing downloads (Lichess Study PGN, Anki CSV)
stay free for all users, unchanged.

**New:** a Pro-only "Add to Review deck" button, visible next to the
existing download buttons. It runs the built positions through
`build_drill_cards()` and calls `srs.py`'s `add_cards()`, then switches to
the Review tab. Free users don't see this button — same free/Pro boundary
as today's SRS Drills gate, just applied to this one new action instead of
a whole page.

### Tab 3 — Review (replaces SRS Drills)

Free users: the existing Pro-gate upsell stub, with copy relabeled from
"SRS Drills" to "Review" / "spaced repetition."

Pro users: a stats strip (due-card count, recent recall/streak, reusing
existing `srs.py` analytics — `weekly_recall`, `learning_curve`,
`recall_by_source` — no new data-layer work) above the existing
`chesswright_pro/srs_drills.py` board/SM-2/reveal flow, reused unmodified.

### Terminology sweep

User-facing "SRS" / "SRS Drills" text becomes "Review" / "spaced
repetition" wherever a user reads it: nav, tab label, Pro upsell copy,
empty states. Code identifiers, file names, table/column names are
unaffected — see Non-goals.

## Open questions for the implementation plan

- Exact shape of the new "Add to Review deck" wiring: does it call
  `build_drill_cards()` directly from the Build Set tab's already-fetched
  preview data, or re-fetch positions server-side on click? (Affects
  whether this needs a new API endpoint or reuses an existing one.)
- Whether tab state should be a URL query param (deep-linkable, e.g. a
  Training Queue/Insights link could land directly on
  `?tab=build&preset=...`) or purely component state — leaning query
  param given the existing `_drill_preset` pass-through use case, but not
  finalized here.
- Whether the Weaknesses tab's 0-position warning banner (documented in
  BRIEF.md §19 — some weakness exports return 0 positions until the
  `moves.motif` backfill runs) still needs its "Run annotation pass now"
  button on this merged page, or whether that belongs solely on Insights
  now that Weaknesses is narrowed.
