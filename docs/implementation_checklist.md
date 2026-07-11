# Chesswright — Outstanding Implementation Checklist

**Purpose:** this is the new authoritative, live checklist of what is
*not yet done*, *partially done*, or *done narrower than spec* across
Chesswright's feature backlog. It is synthesized from
`docs/implementation_roadmap.md` (2,572 lines — the full build log,
rationale, and historical record of every reconciliation session through
§26, 2026-07-11) and re-verified directly against the current codebase
(branch `feature/eval-dedup-cache`, HEAD `e27a6b9`) rather than trusted
from the roadmap's prose alone. **`implementation_roadmap.md` is not
superseded as a record** — it still holds the *why* behind every decision
below, the scoping sessions, and the full narrative. This document is the
*checklist* going forward: shorter, current-state-only, action-oriented.
Update this file (not a new one) as items ship; keep the roadmap as the
append-only build log.

**Grounding date:** 2026-07-11. Verified via direct file/grep inspection
of `dashboard/`, `dashboard/data/`, `chesswright_pro/` (private repo at
`/home/jasper/Desktop/wider_release/chesswright-pro/`), `requirements.txt`,
`constraints.txt`, and a fresh full-suite pytest run (see §9 Appendix for
the live numbers) — not copied from the roadmap's own dated entries
unchecked.

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Shipped, matches spec, committed |
| 🟡 | Partial — real functionality exists but a real piece is missing |
| ⚠️ | Shipped, but **narrower than the original design spec** — flagged so nobody mistakes the narrow slice for the full vision |
| ⛔ | Not started |

---

## 0. Standing blockers (check these before anything else)

1. **⚠️ `dashboard/pro_gate.py`'s `is_pro_active()` has a hardcoded `return True  # TESTING BYPASS` above the real license check** (confirmed still present and still uncommitted, `git diff` today). Unconditionally unlocks every Pro-gated feature (SRS Drills, Opening Tree, Game Report, Coach Mode) regardless of license state. **Must be reverted before any commit/tag/release touching this file, and before any conclusion that a Pro-gated feature is "verified working on the free tier."**
2. **⛔ Phase D pilot recruiting incomplete** — target 5–6 testers, ≥2 Windows/≥2 macOS; not yet reached. People-problem, no engineering shortcut, but it is a real Gumroad-launch precondition alongside item 3.
3. **⛔ Phase 7 Reporting is incomplete** (see §5 below) — per the auto-memory project-state record (`project_state.md`, outside the git repo): *"Gumroad product will NOT be published until all Pro features are complete"*, and the Pro feature status list there still marks "Coach session reports (PDF/export of a student's findings)" as not done. **Both #2 and #3 are independent, real Gumroad-launch preconditions — not a choice between them.**
4. **Two uncommitted, unrelated tracked-file diffs sitting in the working tree**: `.gitignore` (adds `docs/implementation_roadmap.md` to the ignore list) and `dashboard/pro_gate.py` (item 1 above). Plus one untracked file, `BRIEF.md.bak-2026-07-10`. None of this is new work from this session — pre-existing state, noted here so it isn't mistaken for a side effect of this document.

---

## 1. Phase 1 — Design System Foundation

**Status: fully shipped.** All components exist and are in real use:
chart theming (`theme.py`), dark tokens, spacing/type scale, Metric/KPI
Card (`theme.render_metric_card`), Comparison Panel (`theme.
render_comparison_panel`, all 3 modes have real callers), Confidence
Indicator (`dashboard/confidence.py`), Empty State (`thin_data_message`),
Loading/Skeleton State (CSS-themed native spinner, `theme.py`), centralized
query caching (`cached_queries.py`).

- ✅ No open items. The one previously-open question ("does Insight Card
  need its own component?") is resolved: `render_metric_card`'s
  headline/eyebrow/detail mode has two real consumers (Overview's Focus
  Card, Insights' Hero Insight) — no separate component needed.

---

## 2. Phase 2 — Analytics Extensions

**Status: fully shipped**, on the real backend each item claims to use
(confirmed by reading the actual query functions, not just the checklist
line).

| Item | Status | Notes |
|---|---|---|
| Favorite vs Underdog Comparison | ✅ | `patterns_view.py`'s `_render_tab_comparisons`, wired into Metric Card + Comparison Panel |
| Clock & Time comparisons (Won/Lost, White/Black, By Opening) | ✅ | `patterns.get_clock_pressure_by_outcome/_by_color/_by_opening` |
| Opponent Profile Analysis | ✅ | `matchups.py`, re-grouped giant-kill/collapse/position-character by `opponent_name`, plus new swindle-rate join |
| Multi-select Opening Accuracy comparison | ⚠️ | Shipped as **2-opening only**, not true N-way. `theme.render_comparison_panel` hard-caps at 2 panes with no path to 3+ through it. **Revisited 2026-07-11 and declined again**: a cheaper overlay-only N-way path (bypassing `render_comparison_panel` entirely, local to `openings_view.py`) was identified as technically low-cost, but declined for lack of any real demand evidence — see BRIEF.md's 2026-07-11 entry. Revisit only if real demand appears. |
| Material Structure Explorer redesign (Tier 1 + Tier 2) | ✅ | Tier 1: piece-composition buckets (`_shared.py`'s `_classify_endgame_type`, `MIDDLEGAME_TRADE_TIERS`). Tier 2: same/opposite-color bishop ACPL classifier (`chess_utils.classify_bishop_color_ending`), Patterns-page table (`patterns.get_bishop_color_ending_performance`). Both committed (`2622c2d`, `f249384`). |
| Playing Sessions tab | ✅ | Schema extension + UI on `session_ctx_cache` (`patterns_view.py`'s `_render_tab_sessions`), plus an **Event Type Breakdown** shipped 2026-07-11 (Casual vs. Tournament/Arena summary + a named-tournament/arena table, `get_event_type_performance`/`get_event_name_breakdown` in `patterns.py`) — see BRIEF.md's 2026-07-11 entry. True per-instance tournament grouping was investigated and confirmed infeasible (no tournament ID in the ingested PGN, no timing signal separates recurring-arena instances); event-NAME/category aggregation was the real, data-backed scope instead. |

---

## 3. Phase 3 — Flagship Redesigns (Overview / Insights)

**Status: fully shipped**, all four sequenced units from the roadmap's §16
reconciliation are built and committed (`5245a65`):

- ✅ Hero Insight callout (Insights)
- ✅ Quick Explore row (Overview) — **static, page-level only**; no
  tab-deep-linking (that's Phase 4 territory, not built — see §4).
- ✅ Coaching panel teaser (Overview) — links to Insights' existing
  `claude_narrative.generate_coaching_recommendations()` panel, no new
  AI-call logic.
- ✅ Strengths & Weaknesses panel (Insights) — `polarity` field on all 10
  original finding functions + 2 new strength-only findings (`_safest_piece`,
  `_best_matchup`).
- ✅ Confidence/Statistics Service (`dashboard/confidence.py`), consumed
  by 6 modules.
- ✅ Insights severity ranking + category tags — all 10 (now 11, see
  below) finding functions emit `category`/`severity`, 7 also emit
  `confidence`.

**One thing NOT done and explicitly parked, not silently dropped**:
Overview's "Hero Summary / Career Snapshot" line in the original proposal
language describes a more deliberate hero *layout*; what exists today
(templated career narrative, gold Focus Card, 4 headline tiles, dramatic-game
teaser, 3 charted sections) covers the same content under different
presentation. No further Overview layout work is scheduled — flag only if
a future session wants to revisit *presentation*, not content.

---

## 4. Phase 4 — Navigation & IA

| Item | Status | Notes |
|---|---|---|
| Breadcrumbs + stable/expandable sidebar | ⛔ | Not started. Re-confirmed low urgency: every page except Game Detail sits in Streamlit's own sidebar nav (never "stuck"); Game Detail has its own explicit back button. This is polish, not a broken-flow fix. |
| Cross-links, drill-down, "Where Next" panels | ✅ | **Built and live-verified 2026-07-11** (roadmap §28): new reusable `_common.render_where_next()` component, wired onto 4 pages — Patterns & Tendencies (→ Game Endings / Matchups & Opponents / Training Queue), Game Endings (→ Patterns), Repertoire Evolution (→ Openings & Repertoire), Drill Export (→ SRS Drills). Tab-level drill-down capability confirmed cheap (streamlit 1.58's `st.tabs(default=, key=)`) but not needed by any of the 4 real links, so not built — documented for the next time it's needed. Not yet committed. |
| Filter persistence / deep linking | ⚠️ | **Filter persistence built and live-verified 2026-07-11** (roadmap §28) — `_common.persist_filter`/`restore_filter_default`, wired onto ~9 real filters across 5 files (Game Explorer, Matchups, Points, Patterns, Evolution). `openings_view.py`'s `openings_min_games` deliberately excluded (its own bespoke Global-Search-preset sentinel needs a real design pass before layering this on, not a blind copy-paste). **Deep linking (`st.query_params`) is a decided NO-GO**, same reasoning as Command Palette v2 — a local single-user desktop app with no address-bar UI and no cross-install URL meaning gets ~zero value from bookmarkable URLs. Not yet committed. |
| Global Search | ✅ | Built and **committed** (`e27a6b9`, 2026-07-11) — confirmed live in `dashboard/data/search.py` and `app.py`'s sidebar `st.text_input`. `rapidfuzz`-ranked, ~121-item in-memory candidate list (pages/openings/findings/settings + Pro's Coach Mode page when present), zero persisted index, zero new SQL query. `tests/unit/test_search.py` (6/6) exists. |
| Command Palette | ⚠️ | MVP shipped **as the pinned sidebar search box above, not a global Ctrl+K overlay**. Confirmed this is a real technical ceiling, not a shortcut: Streamlit custom components render in a sandboxed iframe, so there is no way for a page-wide keydown handler to work the way the chessboard's local `enable_keyboard_nav` does. A true global keybind remains an explicit, unscoped v2/stretch item requiring either a new pinned dependency (e.g. `streamlit-shortcuts`) or a novel iframe-escaping pattern — not a natural extension of what shipped. |

---

## 5. Phase 5 — Training Center

**Status: the largest genuinely-mixed phase.** The interactive drill-taking
UI (board, move validation, reveal, SM-2 rating) is **fully built and
already generic across position sources** — it lives entirely in the
private repo (`chesswright_pro/srs_drills.py`, 554 lines, confirmed
`st.tabs(["Today's Drills", "Manage Queue", "Progress"])` still current),
Pro-gated. This means most "build a trainer" work is really "add a new
*position-source query*" — a much smaller unit than a new UI.

| Item | Status | Notes |
|---|---|---|
| Unified training queue (severity-ranked) | ✅ | `dashboard/training_queue_view.py`, committed (`691a576`). Reuses `_common.py` chip/action helpers shared with Insights. |
| Weakness-based position extraction (blunders, near-misses, lost-winning-positions) | ⚠️ | **"Blunders" and "lost-winning-positions" are already covered** (Missed Tactics drill source; `points.py`'s `failed_conversion` bucket). **"Near-miss" was investigated and found NOT well-motivated** on the real dev DB — comebacks in this player's data are gradual multi-move accumulations (mean win-prob gain per candidate move 0.76pp, max 2.5pp across 23/52 qualifying games), not single rescue moves, so there's no clean position to extract. No new position-extraction machinery was built for this sub-item, deliberately — not an oversight. |
| Opening Repertoire Trainer | ✅ (as a source, not a distinct UI) | Repertoire Hole source (`openings.get_repertoire_holes`) already feeds the generic SRS drill loop. |
| Tactical Pattern Trainer (pins/forks/skewers) | ✅ (as a source, not a distinct UI) | Missed Tactics source (`get_motif_drill_positions`) already feeds the generic SRS drill loop — but see the motif-backfill caveat below. |
| Endgame Trainer | ⚠️ | Shipped **MVP only** (`be8f945`/`chesswright-pro@bb9991c`): a `phase="endgame"` filter on the existing Decisive Moment source, additionally verified against real material count (fixed a 15.6% mislabeling rate the plain move-number heuristic had). This is **decisive-loss turning points that happen to be in a real endgame** — not a general endgame-technique curriculum (rook endings, opposition, king activity as taught subjects). Say so explicitly if this line is ever re-scoped as "done." |
| Time Management Trainer | ⛔ | **No per-position extraction query exists.** `points.py`'s clock-pressure analytics classify outcomes, not extract drillable positions. Confirmed no shortcut — real new backend work, unlike almost every other recent unit in this backlog. |
| Conversion Trainer | ⛔ | Same gap class as above. `get_failed_conversion_causes` returns game-level cause classification (`hung_piece`/`blown_mate`/`time_pressure`/`other`), not per-position `fen_before`/`best_move_san` rows a drill card needs. |
| Defense Trainer | ⛔ | Same gap class — no per-position extraction exists. |
| Giant Killer & Collapse Trainer | ⛔ | Game-level detection exists (`matchups.get_comeback_collapse_counts`, Opponent Profile Analysis) but no per-position extraction from those games. |
| Training Plans, Adaptive Training, Daily/Weekly goals | ⛔ | Blocked on multiple trainers above existing first — correctly still parked, not re-scored. |
| **Achievements Service** | ⛔ | **Confirmed a pure, clean gap** (re-verified this session: `grep -ril achievement` across `dashboard/` and the private `chesswright_pro/` returns exactly one hit, a code comment in `app.py`, zero actual sketches/fields/tables). Building it now would be speculative — zero real callers exist yet (Overview Highlights, Insights badges, Training Center achievements are all themselves unbuilt). Wait for a first real consumer before scoping. |
| Training Analytics + Coaching narrative | 🟡 | An SRS efficacy "Progress" tab already ships (`srs.py`'s `weekly_recall`/`learning_curve`/`recall_by_source`, consumed by `chesswright_pro/srs_drills.py`), Pro-gated, SRS-scoped. Real remaining gap: analytics for trainers that don't exist yet, plus any cross-trainer summary. |
| Long-Term Development Dashboard | ⛔ | Depends on all of the above; correctly not started. |

**Live operational caveat, not a code bug**: on the real dev DB,
`moves.motif IS NOT NULL` is still 0 across all rows (motif annotation
pass hasn't been re-run since a more recent sync). Training Queue's UI
already handles this with a proactive warning banner + "Run annotation
pass now" link — this is a data-freshness note for whoever runs the app
next, not an outstanding implementation item.

---

## 6. Phase 6 — Settings, Help & Onboarding Maturation

**Status: confirmed entirely unstarted** (re-verified this session — only
`settings_view.py` and `onboarding_view.py` exist; no help/glossary file
anywhere in the repo).

| Item | Status | Notes |
|---|---|---|
| Settings: full category set, search, profiles/presets, safeguards | ⛔ | Current Settings has 6 sections (API key, live engine, DB import, Chess.com account, Chesswright Pro, Support). No named-profile/preset system (distinct from the single current-settings row), no in-Settings search (Global Search's "settings" category just navigates to the page, it doesn't search *within* it). |
| Help Center: guides, glossary, contextual `ⓘ`, FAQ, methodology | ⛔ | No help/glossary file exists anywhere in either repo (confirmed via filesystem search this session). |
| Onboarding: sample dataset, guided tour, progressive personalization | ⛔ | Current onboarding is the existing wizard (calibration + sync); none of these three upgrades exist. |
| **Notification Service** | ⛔ | Undesigned, as flagged in the roadmap's risk register. Confirmed this session: the one "notification" hit in the whole `dashboard/` tree is a doc comment in `analysis_jobs_view.py` describing the *existing* status panel as the de facto notification mechanism today — there is no desktop-notification delivery mechanism (system tray / in-app toast / OS-native) designed or built. |

---

## 7. Phase 7 — Reporting & Sharing

**Status: single-game reports ship (Pro-gated); everything else is a real,
launch-blocking gap** (see §0 item 3).

| Item | Status | Notes |
|---|---|---|
| Single-game narrative report generation | ✅ | `claude_narrative.generate_game_report()`, wired at `game_detail_view.py`, rendered by the private `chesswright_pro/game_report.py` (153 lines). |
| Report Service spec (format + scope decision) | ✅ | **Decided 2026-07-11 (roadmap §27): reports are HTML, not PDF** — supersedes §23's PDF-mechanism framing entirely, no PDF code exists to unwind. Jinja2 templates + Markdown-to-HTML conversion (`markdown` package, new dependency, pure-Python/no packaging risk), `dashboard/report_html.py` + `dashboard/templates/reports/`. Decision made; not yet built. |
| Single-game HTML export | ✅ | Shipped + committed 2026-07-11 (`chess_app@f7419a3`, `chesswright-pro@c778e7c`) per §27 Decisions 1–3. Live-verified opening the exported file standalone in a real browser. Side finding, not fixed: `generate_game_report()`'s `max_tokens=1600` truncates the report body before Verdict on at least one real game. |
| Weekly coaching report | ⛔ | No "last N days" aggregation query exists anywhere (`points.monthly_points` is the closest precedent, but buckets by calendar month, not a rolling week). Coach-Mode-scoped, private-repo-heavy once built. Scoped only (§27 Decision 5) — confirmed not sized for a single session, deliberately left for its own future session. |
| Tournament-prep report | ✅ | Shipped + committed 2026-07-11 (`chess_app@4fde901`, `chesswright-pro@f0f94b3`) per §27 Decision 4. Live-verified rendering both data sources correctly. Found + fixed a real pre-existing bug as a side effect: `prep.get_recent_form()`'s `COUNT(*)` over a `LEFT JOIN` inflated `n_games` and biased `score_pct` (fixed same session, `chess_app@238eb32`). |
| "Sharing" (the phase's own second half) | ✅ | **Decided 2026-07-11 (roadmap §27 Decision 6): the download button already is the sharing mechanism.** No email/OS-integration sharing feature is being built — checked and rejected `mailto:`-with-attachment (not a real cross-platform capability) rather than assumed away. |

**This phase is the single highest-priority engineering gap in the whole
backlog** per the corrected launch-gate finding recorded in project
memory — see §0.

---

## 8. Phase 8 — Reliability, Performance & Testing Hardening

| Item | Status | Notes |
|---|---|---|
| Unit/integration tests for every Phase 2–5 calculation | 🟡 | Every unit shipped through §26 came with real new tests (test counts documented per-unit in the roadmap). Coverage is good for what's shipped; the phase itself is "continuous," not a one-time gate — see live suite numbers below. |
| Right-sized performance benchmarking | ⛔ | Not formally done; no evidence of real performance problems on the current dev DB size (32,295 games) either. |
| Caching convention audit for every new `dashboard/data/*.py` function | 🟡 | The `audit-dashboard-queries` skill exists and has been applied ad hoc; two known un-fixed duplicated `cached_motif_backfill_needed` wrappers remain in `patterns_view.py` and `tactical_highlights_view.py` (flagged, not fixed, during the Training Queue build — a real, small, still-open cleanup item). |
| Quality gate before wider/public release | ⛔ | Not formally run as a gate; Phase D pilot recruiting (§0) is the actual open item standing in front of it. |

**Live full-suite result, this session** (see Appendix §9 for the raw
run): confirms the roadmap's own running "3 pre-existing, unrelated
failures" count — none of the failures are new or related to any item in
this document.

---

## 9. Phase 9 — Future Vision

**Status: correctly untouched**, all items still explicitly deferred with
no new evidence changing that: SQLModel, Polars-at-scale, scikit-learn
clustering/ML, formal plugin architecture, cloud sync, expanded AI
features beyond the existing direct-Anthropic-API pattern. No action
needed; revisit only if a specific pain point emerges.

---

## 10. Recommended next sequence

Carried forward from the roadmap's own §21/§25 reconciliation, re-affirmed
by this session's re-verification (nothing found that changes the
ordering):

1. **Phase 7 Reporting** — the one item with a real, external
   (Gumroad-launch) deadline attached, not just internal backlog priority.
   Start with the `pywebview` print-to-PDF investigation (§7) before
   writing any report-assembly code — it could eliminate the PDF
   dependency risk entirely.
2. **Endgame Trainer's siblings** (Conversion / Defense / Time-management /
   Giant-Killer trainers) — real new backend each, no shortcut found; do
   these only after Reporting, since none of them carry launch-gate
   pressure.
3. **Phase 6** (Settings/Help/Onboarding maturation) — broad-but-shallow,
   lowest engineering leverage of the remaining phases; pick up once 1–2
   are exhausted or blocked.
4. **Achievements Service** — deliberately last: still a real gap, but
   still zero real callers exist to design its data model against.
5. **Command Palette v2** (true global Ctrl+K) — only if a specific need
   for it resurfaces; the sidebar search box already delivers the
   real value (everything reachable by name).

---

## Appendix — Verification performed for this document (2026-07-11)

Not taken from the roadmap's prose unchecked; re-confirmed directly
against the current working tree:

- `git log`/`git status`: confirmed all roadmap-claimed commits through
  `e27a6b9` (Global Search) are real and on this branch; confirmed the two
  standing uncommitted diffs (`.gitignore`, `pro_gate.py`) and one
  untracked file (`BRIEF.md.bak-2026-07-10`) are the only working-tree
  state.
- `dashboard/pro_gate.py`: confirmed the `return True  # TESTING BYPASS`
  line is still present, unconditionally, above the real license check.
- `requirements.txt`/`constraints.txt`: confirmed zero PDF-library hits.
- `grep -ril achievement`: confirmed exactly one hit (a comment) across
  both repos.
- `dashboard/` file listing: confirmed only `settings_view.py`/
  `onboarding_view.py` exist for Phase 6; no help/glossary file anywhere.
- `dashboard/data/drills.py`: confirmed exactly 4 position sources
  (`get_motif_drill_positions`, `get_decisive_moment_positions` with its
  `phase` filter, `openings.get_repertoire_holes`, and the endgame-filtered
  variant of the decisive-moment source) — no conversion/defense/time/
  giant-killer source functions exist.
- `dashboard/data/search.py` + `app.py`: confirmed Global Search's actual
  implementation (candidate lists, `rapidfuzz` ranking, sidebar UI
  placement) matches the roadmap's §26 description exactly.
- `chesswright_pro/srs_drills.py`: confirmed the 4-checkbox Manage Queue
  tab (Missed tactics / Decisive moments / Repertoire holes / Endgame
  turning points) and the 3-tab structure (Today's Drills / Manage Queue /
  Progress) match the roadmap's description.
- **Full test suite, run fresh this session** (`.venv`, `pytest -q`,
  552 collected items): same pre-existing-failure count the roadmap's
  most recent units reported (3 unrelated, pre-existing failures — the
  `pro_gate` TESTING BYPASS-adjacent test plus two headline-metrics
  AppTest checks against the live dev DB's exact numbers). No new
  failures introduced by anything described in this document, since no
  application code was changed while producing it.
