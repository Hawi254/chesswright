"""Grounding data for AI Coach prompts (both the free tier's single-shot
"Ask" prompt and Chesswright Pro's multi-turn AI Coach system prompt).

The AI Coach's "STRICT RULES"/"STRICT FACTUAL RULES" text already forbids
stating an ungrounded *statistic* -- this module is the same discipline
applied to the app's own navigation and capability claims. Without it, when
a question falls outside what the app can answer, the model has to guess at
a plausible-sounding page name and a plausible-sounding capability, and can
get both wrong (confirmed live: it invented a "sort by move time" feature
on the wrong page). `PAGE_CAPABILITIES` below is the real, fact-checked
alternative to guessing -- read from each page's own view module, not
written from memory of what a page "probably" does.

**Keep this in sync with `dashboard/app.py`'s real `st.Page(...)` list.**
`tests/unit/test_app_capabilities.py` enforces this both ways: every
`url_path` here must exist in `app.py`, and every `url_path` in `app.py`
must be represented here. If you add, remove, or rename a page, update
this file in the same change -- the test will fail otherwise, which is the
point (a drifted registry is exactly the bug this file exists to prevent).

Note: `chesswright_pro`'s "Coach Mode" (Student Profiles) page is
intentionally NOT listed here -- its `st.Page(...)` is constructed inside
`chesswright_pro/__init__.py`, not `dashboard/app.py`, so it falls outside
what this registry (and its sync test) can verify against. See the Phase 1
implementation notes for this call.
"""

PAGE_CAPABILITIES = [
    {
        "title": "Game Detail",
        "url_path": "game-detail",
        "capability": (
            "Full move-by-move detail for one selected game: an evaluation "
            "graph (click a point to jump to that move), per-move engine "
            "eval/best line, a move-quality filter, and an AI-generated "
            "game narrative. Reached only by clicking a row on another page "
            "(Game Explorer, Tactical Highlights, Matchups & Opponents, "
            "Where Your Points Go, Batch Impact, or the Overview teaser) -- "
            "there is no sidebar entry and no way to browse to it directly."
        ),
    },
    {
        "title": "Overview",
        "url_path": "overview",
        "capability": (
            "Career-wide summary: badge legend, ACPL trend over time, "
            "analysis-coverage-by-year and by-month charts, and a 'most "
            "dramatic game' teaser link. No sortable/filterable table and "
            "no drill-down beyond that one teaser."
        ),
    },
    {
        "title": "Patterns & Tendencies",
        "url_path": "patterns",
        "capability": (
            "Accuracy (ACPL) and results broken down by move time, "
            "day/hour heatmap, position complexity, pawn structure, "
            "castling side, and capture side, with a structure-type "
            "(endgame/middlegame) toggle. Plain results tables, not "
            "row-clickable; no drill-down to individual games."
        ),
    },
    {
        "title": "Openings & Repertoire",
        "url_path": "openings",
        "capability": (
            "A sortable openings table (click a column header to sort) "
            "with a minimum-games slider, plus an opening picker for an "
            "AI-generated blurb. Also a 'most-repeated positions' table and "
            "a 'repertoire holes' table, each row-selectable to preview the "
            "position on an inline board with engine eval -- selecting a "
            "row shows the board inline, it does not open Game Detail."
        ),
    },
    {
        "title": "Matchups & Opponents",
        "url_path": "matchups",
        "capability": (
            "Rating-difference and color-based win-rate charts, "
            "comeback/collapse quarterly trends, a toughest-opponents "
            "table (click a row to open that opponent's most notable game "
            "in Game Detail), a minimum-games slider for nemesis stats, "
            "and an opponent picker for an AI-generated rivalry blurb."
        ),
    },
    {
        "title": "Game Endings",
        "url_path": "game-endings",
        "capability": (
            "How your games end (resignation, checkmate, time, etc.), "
            "including a resignation-while-still-winning breakdown by "
            "material/piece count and a time-forfeit-while-ahead "
            "breakdown, each with a quarterly trend chart. Plain results "
            "tables; no row click-through to individual games."
        ),
    },
    {
        "title": "Tactical Highlights",
        "url_path": "tactical-highlights",
        "capability": (
            "Flagged positions across five categories -- missed puzzle-"
            "like sequences, brilliant sacrifice candidates, best-move "
            "streaks, blown forced mates, and hallucinated blunders -- "
            "each a top-N table (N adjustable by slider) where clicking a "
            "row opens that game in Game Detail. Also a selectbox for an "
            "AI-generated blurb on missed-tactic themes."
        ),
    },
    {
        "title": "Insights",
        "url_path": "insights",
        "capability": (
            "AI-generated 'what these findings add up to' narrative and "
            "concrete practice recommendations, plus shortcut buttons into "
            "Drill Export and Opponent Prep (e.g. 'Scout this opponent'). "
            "No data table of its own -- not a place to look up a "
            "specific game or stat directly."
        ),
    },
    {
        "title": "Where Your Points Go",
        "url_path": "points",
        "capability": (
            "Score-vs-advantage-leak trend and a breakdown of failed "
            "conversions by peak advantage/phase/clock, plus a 'worst "
            "games' table -- tick a row's checkbox to open that game in "
            "Game Detail. Time-control selectbox filter."
        ),
    },
    {
        "title": "Repertoire Evolution",
        "url_path": "evolution",
        "capability": (
            "How your results for a chosen opening family have changed "
            "over time (quarterly win-rate trend), with time-control and "
            "grouping selectboxes and a color toggle. The trend table is "
            "not row-clickable; no drill-down to individual games."
        ),
    },
    {
        "title": "Game Explorer",
        "url_path": "game-explorer",
        "capability": (
            "The full game list as a sortable, filterable table (opponent-"
            "name text search, click a column header to sort) -- tick a "
            "row's checkbox to open that game's full detail. The only page "
            "built for browsing/searching every game directly. Does not "
            "currently support sorting or filtering by a computed metric "
            "that isn't already a shown column, e.g. average move time."
        ),
    },
    {
        "title": "Drill Export",
        "url_path": "drill-export",
        "capability": (
            "Builds a printable/exportable set of practice positions from "
            "your flagged mistakes, with a max-positions-per-source slider "
            "and a source picker, and shows a preview table. Not a page "
            "for browsing or analyzing games generally."
        ),
    },
    {
        "title": "SRS Drills",
        "url_path": "srs-drills",
        "capability": (
            "Pro feature. In-app spaced-repetition drill sessions over "
            "your own flagged mistake positions, shown again at growing "
            "intervals as you answer correctly. The core page is only an "
            "upsell gate for non-Pro users -- the real drill UI lives in "
            "the Pro package."
        ),
    },
    {
        "title": "Opening Tree",
        "url_path": "opening-tree",
        "capability": (
            "Pro feature. An interactive tree of your opening repertoire "
            "showing win rate and accuracy at every branch, with a way to "
            "push weak positions into the SRS drill queue. The core page "
            "is only an upsell gate for non-Pro users -- the real tree UI "
            "lives in the Pro package."
        ),
    },
    {
        "title": "Opponent Prep",
        "url_path": "opponent-prep",
        "capability": (
            "Fetches and analyzes one specific opponent's recent games "
            "(username + a games-to-fetch slider) and reports their "
            "opening repertoire and blunder rate by opening. A single-"
            "opponent deep dive, not a way to browse your own game history."
        ),
    },
    {
        "title": "Ask",
        "url_path": "ask",
        "capability": (
            "The app's AI Q&A page. Free tier: a single text box for one "
            "question at a time (plus preset examples), answered once "
            "from a fixed pre-assembled stats brief -- no memory across "
            "questions, no tool calls, no per-game or per-move lookup. "
            "When Chesswright Pro is active, this same page instead runs "
            "the full multi-turn AI Coach (conversation memory, live tool "
            "calls, thumbs up/down feedback) -- this prompt IS that "
            "Pro-tier experience if you're reading this as the Pro system "
            "prompt."
        ),
    },
    {
        "title": "Settings",
        "url_path": "settings",
        "capability": (
            "Configuration: Claude API key, database file path and "
            "lichess username, license key, and engine settings. Not a "
            "data or analysis page."
        ),
    },
    {
        "title": "Analysis Jobs",
        "url_path": "analysis-jobs",
        "capability": (
            "Start, stop, and monitor a Stockfish analysis batch (progress "
            "caption, cache hit-rate and ETA), with a link into Batch "
            "Impact once a batch finishes. Not a place to look up existing "
            "analysis results."
        ),
    },
    {
        "title": "Batch Impact",
        "url_path": "batch-impact",
        "capability": (
            "Before/after comparison for one specific completed analysis "
            "batch (picked via a selectbox): ACPL/blunder-rate by phase, "
            "tactical motifs, and a new-blunders table -- click a row to "
            "open that game in Game Detail."
        ),
    },
    {
        "title": "Setup",
        "url_path": "setup",
        "capability": (
            "First-run onboarding (lichess username, a games-to-analyze-"
            "now slider) before any data exists yet; once set up, this "
            "same page ('Sync Games') is used to pull new games from "
            "lichess. Not a stats or analysis-browsing page."
        ),
    },
]


def format_capabilities_block(page_capabilities=None) -> str:
    """Render PAGE_CAPABILITIES (or a caller-supplied list of the same
    shape) as "- {title}: {capability}" lines, one per page -- the shared
    formatting used by both dashboard/claude_narrative.py's free-tier
    prompt and chesswright_pro/ai_coach.py's Pro system prompt, so the two
    tiers never drift into differently-worded (or differently-wrong)
    descriptions of the same page.
    """
    if page_capabilities is None:
        page_capabilities = PAGE_CAPABILITIES
    return "\n".join(
        f"- {page['title']}: {page['capability']}"
        for page in page_capabilities
    )
