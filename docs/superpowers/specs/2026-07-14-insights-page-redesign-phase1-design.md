# Insights Page Redesign — Phase 1 (real-data-only)

Status: pending user review
Branch: worktree-frontend-spike

## Context

`Insights Page Redesign.txt` (dropped at repo root, not committed source)
proposes a 13-section redesign of the Insights page: a hero "insight of
the week", a richer performance summary, severity-grouped and
category-grouped findings, confidence bars, per-finding Elo-impact
estimates, trend arrows, an interactive relationship graph between
findings, a consolidated training queue with time estimates, and an
"achievements/recent improvements" section.

`docs/frontend_migration_status.md` lists `insights_view.py` as `⛔` not
started — this is the page's first React port, done at the same time as
the redesign rather than as a separate literal-port-then-restyle pass.

Checked against the real codebase before scoping: `insights.py`'s
`get_career_findings()` already computes `severity`/`confidence`/
`polarity`/`category` per finding, and the Streamlit page already has a
hero callout, a strengths/weaknesses panel, and two Claude-backed
sections (`Synthesis`, `What to practice`). `/api/overview/career-findings`
and `/api/overview/headline-stats` already serve this exact data to
Overview's `CoachingZone`/`EvolutionZone`. Four of the proposal's 13
sections have **no backend basis at all** today and would require new
methodology, not just UI, to build honestly:

- **Estimated Rating Impact** ("+35 Elo if fixed") — no predictive model
  exists anywhere in the codebase. This conflicts with an explicit,
  deliberate house norm (`BRIEF.md` / `confidence.py`'s own comments):
  omit a stat rather than fabricate one — see `confidence_badge_html`'s
  "no entry for 'insufficient'" comment and the "confidence deliberately
  omitted, not fabricated" line in the §15 build-log entry.
- **Trend indicators** ("▼0.8% last 90 days") — every finding is
  recomputed live over full history; there is no historical snapshot
  store to diff against.
- **Interactive relationship graph** (finding → finding causal links) —
  no correlation/causal analysis exists between findings today.
- **"Recent Improvements"** conflates the Achievements Service (binary
  unlock badges, built backend-only 2026-07-11, zero UI consumer yet)
  with period-over-period metric deltas (same trend-snapshot gap as
  above) — two different unbuilt things, not one.

This spec covers only what's buildable now from real data: the
structural/visual redesign (hero, performance summary, severity and
category grouping, strengths/weaknesses, confidence bars, curated
discoveries, ported Claude sections, a training-queue teaser). The four
items above are explicitly deferred, not silently dropped — see
Non-goals.

## Goals

- Port Insights to React for the first time, redesigned per the
  proposal's information hierarchy (prioritized hero → summary →
  critical findings → strengths/weaknesses → categorized browse →
  discoveries → synthesis → coaching → training-queue teaser), using
  only fields the backend already computes or can honestly expose.
- Reuse existing infrastructure: `/api/overview/career-findings` and
  `/api/overview/headline-stats` (already built for Overview), the
  `get_cached_narrative`/`claude_narrative` + generate-endpoint pattern
  already proven for Openings' commentary.
- Make each insight card's confidence claim backed by a real number
  (sample size), not just a tier label.

## Key decisions (from this session's brainstorm)

1. **Categories are relabeled, not remapped.** The proposal's taxonomy
   (Tactical/Positional/Time Management/Psychology/Opening/Endgames)
   doesn't fit the real data — no finding is tagged "Opening" or
   "Endgames" today, and forcing `matchup`/`giant_killer` into
   "Psychology" would misrepresent what those findings actually measure.
   Phase 1 keeps the real 6 categories and gives each a clearer display
   label: `tactical` → "Tactical", `time` → "Time Management", `defense`
   → "King Safety", `matchup` → "Matchups & Opponents", `giant_killer` →
   "Giant-Killing & Collapses", `general` → "General". Empty categories
   are omitted, not shown as placeholders.
2. **Two views of the same list, not two datasets.** "Critical Findings"
   (severity `high`) and "Categorized Insights" (all findings grouped by
   category) both read the same `findings` array fetched once — Critical
   Findings is a prominence cut, Categorized Insights is the full browse
   view. No separate query or filtering endpoint.
3. **Confidence bars need one real backend field.** Finding dicts
   already carry a `confidence` tier but the underlying sample size is
   only embedded in the `detail` prose string today (e.g. "over 8,977
   analyzed Pawn moves"). Rather than parse text, `insights.py`'s ~10
   finding functions each get one new `sample_size` int in their return
   dict, sourced from a local value they already compute (`row.n_moves`,
   `toughest.n`, etc.) — no new query, no new gating logic, just
   surfacing what's already there.
4. **Card action buttons are omitted entirely.** The Streamlit page's
   "Export practice positions"/"Scout this opponent" buttons deep-link to
   Drill Export/Opponent Prep, neither of which exists in React yet.
   Same precedent as the Openings & Repertoire port (decision 7 there):
   drop the dead link, re-add once the target page exists.
5. **Training Queue is a teaser, not embedded.** Top 2-3 weakness
   findings by severity + a link to a future, separately-ported Training
   Queue page — mirrors how Overview's `CoachingZone` already teases into
   Insights. Avoids duplicating the full weakness-queue render logic in
   two places before either has a stable home.
6. **Interesting Discoveries reuses existing data only.** Findings with
   `polarity === 'neutral'` (tactical highlights round-up, game-endings
   distribution) plus any finding with an unusually large surprise gap
   (`nemesis`/`best_matchup`'s `expected_score_pct` vs. `score_pct`
   delta, already computed), relabeled "Did you know?" No new queries —
   the proposal's specific example facts (e.g. "your strongest opening
   isn't your most-played") aren't computed anywhere and aren't built
   here.
7. **Synthesis and coaching recommendations are ported as-is.** Same
   cached-narrative + generate/regenerate button, same
   `claude_narrative.api_key_available()` gating and degrade-gracefully
   message as the Streamlit page — these two Claude-backed sections
   predate this redesign and aren't mentioned in the proposal, but
   dropping them would be a real feature regression.

## Backend: `insights.py` changes

Add `sample_size` to every finding dict in `get_career_findings()`
(decision 3). Each function already has the value in scope — this is a
mechanical addition, one line per function, no new computation:

```python
# _piece_hotspot / _safest_piece
"sample_size": int(row.n_moves),

# _sharpness / _thinking_time / _time_pressure
"sample_size": int(min(flat.n_moves, forcing.n_moves)),  # or worst/best pair, matching that function's existing confidence_tier() call

# _castling
"sample_size": int(min(castled.n_games, not_castled.n_games)),

# _backrank
"sample_size": int(min(elsewhere.n_moves, back.n_moves)),

# _nemesis / _best_matchup
"sample_size": int(toughest.n),  # or best.n

# _bishop_color_endings
"sample_size": int(min(opp.n_moves, same.n_moves)),
```

`_giant_killing`, `_tactical_highlights`, `_game_endings` have no
existing sample-size gate (per `get_career_findings`'s own docstring) —
no `sample_size` field is added for these three, same convention as
their already-absent `confidence` field. Cards for these three findings
render without a confidence bar, not a fabricated one.

`dashboard/_common.py`'s `finding_chips_html` is unaffected — the React
cards build their own chip markup from the JSON fields directly, same as
every other ported page (React does not consume server-rendered HTML
chip strings).

## Backend: FastAPI endpoints (`api/main.py`)

`career-findings` and `headline-stats` already exist and need no
changes beyond the `sample_size` field flowing through automatically
(both are thin wrappers over `data.get_career_findings`/
`data.get_headline_stats`). Two new endpoint pairs, following the exact
pattern already proven for Openings' commentary
(`/api/openings/{family}/{color}/narrative` + `/generate`):

```python
_insights_synthesis_cache = _TTLCache(60)   # add alongside the existing _TTLCache instances; add to reset_caches()
_insights_coaching_cache = _TTLCache(60)


def _narrative_response(cached):
    if cached is None:
        return {"narrative": None, "generated_at": None}
    response_text, generated_at = cached
    return {"narrative": response_text, "generated_at": generated_at}


@app.get("/api/insights/synthesis")
def insights_synthesis():
    sqlite_conn, _ = get_db_connections()
    return _narrative_response(data.get_cached_narrative(sqlite_conn, "findings", "summary"))


@app.post("/api/insights/synthesis/generate")
def generate_insights_synthesis():
    sqlite_conn, duck_conn = get_db_connections()
    stats = data.get_headline_stats(duck_conn, sqlite_conn)
    findings = _career_findings_cache.get(
        lambda: data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate")))
    try:
        response_text = claude_narrative.generate_insights_synthesis(
            findings, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "findings", "summary", response_text, claude_narrative.MODEL)
    return {"narrative": response_text}


@app.get("/api/insights/coaching")
def insights_coaching():
    sqlite_conn, _ = get_db_connections()
    return _narrative_response(data.get_cached_narrative(sqlite_conn, "coaching", "recommendations"))


@app.post("/api/insights/coaching/generate")
def generate_insights_coaching():
    sqlite_conn, duck_conn = get_db_connections()
    stats = data.get_headline_stats(duck_conn, sqlite_conn)
    findings = _career_findings_cache.get(
        lambda: data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate")))
    try:
        response_text = claude_narrative.generate_coaching_recommendations(
            findings, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "coaching", "recommendations", response_text, claude_narrative.MODEL)
    return {"narrative": response_text}
```

Notes:
- `subject_type`/`subject_key` (`"findings"|"summary"`,
  `"coaching"|"recommendations"`) match `insights_view.py`'s own calls
  exactly, so a narrative generated from either frontend against the
  same `chess.db` lands in the same `narratives` row — same convergence
  benefit as the Openings narrative endpoints.
- `/api/overview/coaching-plan-status` (existing, `{"cached": bool}`
  only) stays as-is — it's a lightweight existence check for Overview's
  CTA label, not replaced by the new full-text endpoint.
- No caching wrapper around the two `/generate` POSTs — same convention
  as the Openings narrative generate endpoint (only runs on a manual
  button click).

## Frontend

### Hooks (`frontend/src/hooks/`)

- **`useInsightsData()`** — thin composition hook, mirrors
  `useOverviewData`'s shape: calls the existing `/api/overview/
  headline-stats` and `/api/overview/career-findings` in parallel,
  returns `{ stats, findings, loading, error }`. Not a new fetch of
  different data — same two endpoints Overview already uses, fetched
  again independently (matches this codebase's existing per-page-fetch
  convention; no cross-page data cache exists yet).
- **`useInsightsSynthesis()`** / **`useInsightsCoaching()`** — two
  instances of the exact `useOpeningNarrative`-shaped hook (loading /
  error / generating / generateError / generate()), pointed at
  `/api/insights/synthesis` and `/api/insights/coaching` instead of the
  per-opening path. Given the shape is identical to
  `useOpeningNarrative` apart from the URL and having no path params,
  factor the common polling/generate logic into a small internal helper
  both hooks call, rather than copy-pasting the whole hook twice.
- `Finding` type gains one optional field: `sample_size?: number`
  (matches the backend's per-function conditional presence — absent for
  `giant_killing`/`tactical_highlights`/`game_endings`).

### Shared/new components

- **`InsightCard.tsx`** — the card used by every findings-driven section
  (Critical Findings, Categorized Insights, Interesting Discoveries).
  Props: `finding: Finding`. Renders title, severity chip (Critical/
  Moderate/Minor — `negative`/`cwCopper`/`cwCyan` tokens for high/medium/
  low, direct swap of the existing three-token severity scheme, no new
  colors), headline, detail, category chip (display-label lookup table
  per decision 1), and a confidence bar (rendered only when both
  `confidence` and `sample_size` are present — 3-level width by tier,
  since there's no continuous confidence score to interpolate: low
  ≈33%, medium ≈66%, high 100%, labeled `"{Tier} confidence — {sample_size} games"`).
  No action button (decision 4).
- **`HeroInsight.tsx`** — large single-card variant of `InsightCard` for
  the top-severity finding, restyled per the proposal's larger callout
  treatment (bigger type, no card border, matches the existing Focus
  Card gold-accent idiom already used on Overview).
- **`PerformanceSummary.tsx`** — 5 stat tiles, all derived client-side
  from `stats`/`findings` already in hand: Analyzed Games, Coverage %
  (`stats.analyzed_games / stats.total_games`), Insights Generated
  (`findings.length`), Critical Findings (`severity === 'high'` count),
  Training Opportunities (`polarity === 'weakness'` count). No new
  backend field.
- **`StrengthsWeaknesses.tsx`** — 2-column panel, direct port of
  `insights_view.py`'s `_render_strengths_weaknesses` filtering
  (`polarity === 'strength'` / `'weakness'`, `mixed`/`neutral` excluded
  same as today), full lists (not `CoachingZone`'s capped-at-2 preview).
- **`CategorizedInsights.tsx`** — groups `findings` by `category`, one
  `InsightCard` list per non-empty category, display labels per decision
  1.
- **`InterestingDiscoveries.tsx`** — filters `findings` per decision 6,
  renders as `InsightCard`s under a "Did you know?" heading.
- **`TrainingQueueTeaser.tsx`** — top 2-3 `polarity === 'weakness'`
  findings by severity + a `Link` to `/training-queue` (per decision 5;
  the route itself is not created by this spec — see Non-goals).
- **`NarrativePanel.tsx`** — shared by Synthesis and Coaching sections
  (decision 7): cached-text display + generate/regenerate button +
  `useClaudeKeyStatus`-gated "Add your own Anthropic API key..." message,
  parameterized by which of the two hooks/labels it wraps. One component,
  two call sites, rather than duplicating the gating logic.

### Page composition (`InsightsPage.tsx`)

Single-column page (not tabs — unlike Openings, these sections are read
top-to-bottom, not independently selected), matching the Suggested
Layout order from the proposal:

```
HeroInsight
PerformanceSummary
CriticalFindings (InsightCard list, severity === 'high')
StrengthsWeaknesses
CategorizedInsights
InterestingDiscoveries
NarrativePanel (synthesis)
NarrativePanel (coaching)
TrainingQueueTeaser
```

Wired into `App.tsx`'s `PAGE_COMPONENTS` lookup (`insights: InsightsPage`,
replacing the current `PageStub` fallback — `navConfig.ts` already has
the `insights: 'Career'` group entry, no nav changes needed).

## Non-goals

- Estimated Rating Impact, trend indicators, interactive relationship
  graph, Achievements-as-"Recent Improvements" UI — all four need real
  new methodology/infrastructure (a predictive model, historical
  snapshotting, correlation analysis, an achievements UI surface
  respectively), not just layout work. Candidates for their own future
  specs once/if that groundwork is scoped.
- Remapping categories to the proposal's Tactical/Positional/Time
  Management/Psychology/Opening/Endgames taxonomy (decision 1).
- Per-card practice-action buttons / Drill Export / Opponent Prep deep
  links (decision 4).
- A full embedded Training Queue page (decision 5) — tracked separately
  as its own future port in `docs/frontend_migration_status.md`.
- Any change to `dashboard/insights_view.py` itself — left as-is, same
  posture as every other ported page's Streamlit source.
- Streaming/progressive rendering of the Claude narrative responses —
  matches every other Claude-backed feature in this codebase (blocking
  POST).

## Testing

- `tests/unit/test_insights.py` (existing) — extend with `sample_size`
  assertions for the functions that gain it; confirm it's absent for
  `_giant_killing`/`_tactical_highlights`/`_game_endings`.
- `tests/integration/test_api_insights.py` (new): `TestClient` +
  `migrated_db_path` fixture; synthesis/coaching get (empty/populated)
  + generate (happy path, `MissingApiKeyError` → 503, generic exception
  → 502) for both endpoint pairs; `reset_caches()` between tests.
- Hook tests: `useInsightsData.test.ts` (loading → success/error),
  `useInsightsSynthesis.test.ts` / `useInsightsCoaching.test.ts`
  (mirroring `useOpeningNarrative.test.ts`'s cases).
- Component tests: `InsightCard.test.tsx` (severity/category chip
  mapping, confidence bar present/absent, no action button rendered),
  `PerformanceSummary.test.tsx` (tile math against a hand-built findings
  array), `StrengthsWeaknesses.test.tsx` / `CategorizedInsights.test.tsx`
  / `InterestingDiscoveries.test.tsx` (filtering logic), `NarrativePanel.
  test.tsx` (cached/uncached/generating/API-key-missing states),
  `InsightsPage.test.tsx` (section presence, empty-findings state).
- Live verification (`verify` skill): both dev servers against the
  worktree's real `chess.db`; screenshot the full page, confirm
  category grouping matches real category values in the data, confirm
  confidence bars show real sample sizes, exercise both generate
  buttons, confirm zero console errors.

## Open items for the implementation plan to resolve

- Exact tile layout/breakpoints for `PerformanceSummary`'s 5 stats
  (proposal shows them stacked; likely a responsive grid matching
  Overview's existing 4-metric-tile row pattern — confirm against that
  component at implementation time).
- Whether `CategorizedInsights` needs its own empty-state message when
  zero categories have findings (thin-data case, mirrors `insights_view.
  py`'s existing `thin_data_message` gate) — likely yes, decide the exact
  copy at implementation time.
- Severity-bar width constants (33%/66%/100% suggested above) — confirm
  visually once `InsightCard` is live, adjust if the 3-level jump looks
  too coarse next to the real chip/color treatment.
