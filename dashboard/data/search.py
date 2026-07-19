"""Global Search (roadmap §25) -- candidate-list construction and fuzzy
ranking. Streamlit-free, matching this package's data/*.py convention
(the data layer never imports streamlit; dashboard/ modules do), so this
is testable without a Streamlit runtime.

The searchable universe is small (~121 items max: 20 pages + ~1 Pro page,
~81 opening families, <=13 findings, 6 settings sections) -- confirmed in
the §25 scoping session against the real dev chess.db. That's well inside
the range where a linear rapidfuzz scan is sub-millisecond, so there is
no persisted index, no new database schema, and no indexing job here.

Each candidate is a dict:
    {"category": "page" | "opening" | "finding" | "setting",
     "title": str,
     "url_path": str,
     "preset": dict | None}
"page"/"setting" candidates have no "preset" key set by this module
(app.py's UI code uses .get("preset")); "opening"/"finding" candidates
always carry one (None for findings -- they land on the Insights page
itself, no item-level deep link, same page-level granularity every other
cross-link in this codebase uses).
"""
from rapidfuzz import fuzz, process

# Static, one entry per real sidebar page, titles/url_paths copied
# exactly from app.py's st.Page(...) calls. Deliberately excludes:
#   - detail_page ("Game Detail"): visibility="hidden", reachable only
#     via st.switch_page from a row click, no stable sidebar identity to
#     search on -- same reasoning app.py's own nav dict comment gives for
#     leaving it out of the sidebar.
#   - onboarding_page ("Setup"/"Sync Games"): title is computed at
#     runtime (NEEDS_ONBOARDING-dependent), and it's a wizard flow with
#     its own explicit navigation ("Go to dashboard" button), not a
#     stable search destination -- excluded for a different reason than
#     detail_page, but the same category of exclusion.
PAGE_CANDIDATES = [
    {"category": "page", "title": "Overview", "url_path": "overview"},
    {"category": "page", "title": "Patterns & Tendencies", "url_path": "patterns"},
    {"category": "page", "title": "Openings & Repertoire", "url_path": "openings"},
    {"category": "page", "title": "Matchups & Opponents", "url_path": "matchups"},
    {"category": "page", "title": "Game Endings", "url_path": "game-endings"},
    {"category": "page", "title": "Tactical Highlights", "url_path": "tactical-highlights"},
    {"category": "page", "title": "Insights", "url_path": "insights"},
    {"category": "page", "title": "Where Your Points Go", "url_path": "points"},
    {"category": "page", "title": "Repertoire Evolution", "url_path": "evolution"},
    {"category": "page", "title": "Game Explorer", "url_path": "game-explorer"},
    {"category": "page", "title": "Drill Export", "url_path": "drill-export"},
    {"category": "page", "title": "Training Queue", "url_path": "training-queue"},
    {"category": "page", "title": "SRS Drills ✦", "url_path": "srs-drills"},
    {"category": "page", "title": "Opening Tree ✦", "url_path": "opening-tree"},
    {"category": "page", "title": "Opponent Prep", "url_path": "opponent-prep"},
    {"category": "page", "title": "Ask", "url_path": "ask"},
    {"category": "page", "title": "Settings", "url_path": "settings"},
    {"category": "page", "title": "Analysis Jobs", "url_path": "analysis-jobs"},
    {"category": "page", "title": "Batch Impact", "url_path": "batch-impact"},
]

# Static, one entry per st.subheader(...) in settings_view.py. All land on
# the same page -- Settings has no per-section URL fragment/anchor, so
# every hit here just navigates to "settings" (same page-level, not
# item-level, granularity as every other cross-link in this codebase).
SETTINGS_CANDIDATES = [
    {"category": "setting", "title": "Anthropic API key", "url_path": "settings"},
    {"category": "setting", "title": "Live engine settings", "url_path": "settings"},
    {"category": "setting", "title": "Import an existing database", "url_path": "settings"},
    {"category": "setting", "title": "Chess.com account", "url_path": "settings"},
    {"category": "setting", "title": "Chesswright Pro", "url_path": "settings"},
    {"category": "setting", "title": "Support this project", "url_path": "settings"},
]


def build_dynamic_candidates(openings_df, findings):
    """The data-dependent half of the candidate list -- pure, no
    duck_conn/sqlite_conn params. Callers pass already-fetched values:
    openings_df is cached_openings_table_full()'s return value as-is
    (one row per (opening_family, player_color) pair), findings is
    cached_career_findings()'s return value as-is (a list of dicts, each
    with a "title" key). No new SQL query is needed here -- both are
    free byproducts of caches that already exist and are already warm on
    the pages most users visit first.
    """
    candidates = []
    seen_families = set()
    for family in openings_df["opening_family"]:
        if family in seen_families:
            continue
        seen_families.add(family)
        candidates.append({
            "category": "opening",
            "title": family,
            "url_path": "openings",
            "preset": {"opening_family": family},
        })
    for finding in findings:
        candidates.append({
            "category": "finding",
            "title": finding["title"],
            "url_path": "insights",
            "preset": None,
        })
    return candidates


def rank_candidates(query, candidates, limit=8, score_cutoff=50):
    """Fuzzy-rank candidates by title against query, returning the
    original candidate dicts (not just matched title strings) in ranked
    order. Empty/whitespace-only query short-circuits to [] without
    calling rapidfuzz at all -- there's nothing meaningful to rank a
    blank query against, and it avoids surfacing an arbitrary top-N on
    every page load before the user has typed anything.
    """
    if not query or not query.strip():
        return []
    titles = [c["title"] for c in candidates]
    matches = process.extract(
        query, titles, scorer=fuzz.WRatio, limit=limit, score_cutoff=score_cutoff)
    return [candidates[index] for _, _, index in matches]
