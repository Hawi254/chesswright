# Frontend migration status (Streamlit → React/Vite + FastAPI)

**Purpose**: a live, current-state-only tracker of which of the 21
Streamlit `dashboard/*_view.py` pages have a React/FastAPI counterpart on
`worktree-frontend-spike`, so a session doesn't have to reconstruct
"what's ported so far" from `git log` and scattered memory notes. Update
this file (not a new one) as slices ship — see the `port-view-slice`
skill for the recipe each row's port should follow.

**Grounding date**: 2026-07-14, checked directly against
`frontend/src/pages/` and `api/main.py`'s route table, not copied from
memory unchecked.

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Ported — real FastAPI endpoint(s) + React component(s), live-verified against the real dev `chess.db` |
| 🟡 | Partial — some sections of the page ported, others still pending |
| ⛔ | Not started — Streamlit-only, React side is just `PageStub` |

## Pages

| Streamlit module | Page | Status | Notes |
|---|---|---|---|
| `overview_view.py` | Overview | ✅ | All zones ported: engine-status strip, IdentityZone (win rate by color), MilestonesRow, EvolutionZone (rating + ACPL trajectory), CareerHighlight (top 3 games), CoachingZone (strengths/mixed/focus-areas preview). See `git log` on this branch for the full slice-by-slice history. |
| `insights_view.py` | Insights | ⛔ | |
| `openings_view.py` | Openings & Repertoire | ✅ | Four tabs (Your openings, Most-repeated positions, Repertoire holes, Where does accuracy drop) via a new `Tabs` primitive — lazy-mounted panels, only the active tab's data hook fires. Master-detail row-click + arrow-key nav (sections 2-3) via a shared `PositionInspector` board+eval panel. Win/draw/loss and hole_score render as intensity bars (Game Explorer's `drama_score` idiom). Drill-export and Global Search deep-linking intentionally not ported (see the design spec's decisions 7-8). |
| `evolution_view.py` | Repertoire Evolution | ⛔ | Not to be confused with Overview's `EvolutionZone` component, which only covers the rating/ACPL trajectory charts — this is the full standalone page (opening-family time dimension). |
| `opening_tree_view.py` | Opening Tree | ⛔ | Pro-gated. |
| `game_explorer_view.py` | Game Explorer | ✅ | Filter (badges/opponent/analyzed-only) + semantic data table, drama score shown as a copper intensity bar. Row click drills into Game Detail. |
| `game_detail_view.py` | Game Detail | 🟡 | Core viewing only: header, badge chips, board (new read-only plain-React component, replacing the Streamlit-bridge-coupled one for this slice), move list, win-probability eval graph -- all synced on one shared `ply` state, arrow-key navigable. Variation mode, annotations (incl. Claude), saved variations, Board Chat, and the Pro-gated Game Report are NOT ported yet. |
| `game_endings_view.py` | Game Endings | ⛔ | |
| `matchups_view.py` | Matchups & Opponents | ✅ | Two tabs (Rating & Form, Named Opponents) via the shared `Tabs` primitive — one bundled `/api/matchups/rating-form` endpoint for the six argument-less queries, `/api/matchups/nemesis` + 3 per-opponent endpoints for the rest. All 4 nemesis tables (Toughest/Favorite/Most-played/Biggest-surprises) and the inline `cmdk`-based `OpponentPicker` funnel into one shared `selectedOpponent` state driving a single `OpponentProfilePanel`. `ConfidenceBadge` extracted from `InsightCard` for reuse on the nemesis tables. Hidden `matchups/:gameId` drill-down reuses `GameDetailPage`. Live-verified against the real dev `chess.db`, including a real Claude-generated opponent commentary round-trip.
| `patterns_view.py` | Patterns & Tendencies | ✅ | All 7 of 7 slices shipped: `TendencyScorecard` (7 of 7 cards) + Clock & Time (4 panels), Turning Points (1 panel, no accordion), Piece Handling (5 accordion panels), Positions (7 accordion panels), Game Context (2 panels, no accordion), Comparisons (6 accordion panels), Playing Sessions (9 accordion panels, full-tab empty state) via `/api/patterns/summary` + `/api/patterns/clock-time` + `/api/patterns/turning-points` + `/api/patterns/pieces` + `/api/patterns/positions` + `/api/patterns/game-context` + `/api/patterns/comparisons` + `/api/patterns/sessions`. `overlayBarChart()` (built in the parent spec, unused until this slice) now used by Comparisons. No new chart primitives added by this slice. Patterns & Tendencies migration complete. |
| `points_view.py` | Where Your Points Go | ✅ | Hero Sankey (`sankeyChart()`, new primitive) + 4-tile numeric readout replace the old four metric tiles and three-card bucket row; headline callout, monthly actual-vs-ceiling trend, conversion breakdown (3 bar charts), conversion causes (3 bar charts), and a costliest-games table are all unchanged in substance from the Streamlit page. New interaction: clicking a Sankey bucket node/link filters the costliest-games table (client-side only, no new endpoint), with an auto-clearing "Showing: X ✕" chip. One bundled `/api/points/summary` endpoint, zero new pandas/SQL. Hidden `points/:gameId` drill-down reuses `GameDetailPage`. Live-verified against the real dev `chess.db`, including the click-to-filter interaction. |
| `tactical_highlights_view.py` | Tactical Highlights | ⛔ | |
| `training_queue_view.py` | Training Queue | ⛔ | |
| `drill_export_view.py` | Drill Export | ⛔ | |
| `srs_drill_view.py` | SRS Drill Mode | ⛔ | Pro-gated. |
| `prep_view.py` | Opponent Prep | ⛔ | |
| `analysis_jobs_view.py` | Analysis Jobs | ✅ | Built 2026-07-15 as a fresh "Command Center" two-column layout, not a widget-by-widget port — see BRIEF.md's 2026-07-15 entry. |
| `batch_impact_view.py` | Batch Impact | ⛔ | |
| `ask_view.py` | Ask | ✅ | Built as Answer Cards (not a chat thread) with SSE streaming + localStorage history — see docs/superpowers/specs/2026-07-17-ask-page-design.md and BRIEF.md's entry for this date. |
| `onboarding_view.py` | Onboarding | ⛔ | First-run wizard — likely wants its own design pass rather than a literal port, given the React app's shell/nav is already a different information architecture. |
| `settings_view.py` | Settings | ⛔ | Holds the bring-your-own Claude API key flow (`keyring` + fallback) — security-sensitive, port carefully. |

**21 pages total: 3 done (Overview, Game Explorer, Openings & Repertoire),
1 partial (Game Detail), 17 not started.** No page is
scoped as "next" here — that's a product/sequencing decision, not
implied by this table's order (which just follows the Streamlit nav).
