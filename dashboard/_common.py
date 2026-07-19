"""Shared helpers for the Phase 6 dashboard -- the Streamlit-coupled
remainder after the largest-file modularization split (2026-07-17) moved
the DuckDB-over-SQLite connection machinery to root-level connections.py
(that file has no `streamlit` import at all; this one does throughout).
Re-exports connections's names below so every existing call site
(`from _common import get_config`, `from _common import resolve_db_path`,
etc.) keeps working unchanged.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

import confidence

from connections import (
    DiskSpaceError, open_fresh_connections,
    _LockedDuckDBResult, _LockedDuckDBConnection,
    _duck_snapshot_path, _cleanup_stale_snapshots, _build_duck_snapshot,
    _bundled_sqlite_extension_path, _load_duckdb_sqlite_extension,
    get_duckdb_connection, get_sqlite_connection, resolve_db_path, get_config,
)


@st.cache_resource(show_spinner="Opening your game database…")
def get_connections():
    """One SQLite connection + one DuckDB connection for the whole server
    session (st.cache_resource, not cache_data -- these are live
    connections, not serializable results). Moved here from app.py in
    Phase 6c.3 (multi-page restructure) specifically so every page module
    (game_explorer_view.py, game_detail_view.py, app.py itself) shares the
    SAME cached singleton -- two separately-defined get_connections()
    functions in different modules would each get their OWN cache entry
    (Streamlit keys st.cache_resource by function identity), silently
    reopening the connection and re-triggering the ~94s structure_ctx
    rebuild cost this caching exists to avoid in the first place."""
    db_path = resolve_db_path()
    try:
        return open_fresh_connections(db_path)
    except DiskSpaceError as e:
        st.error(str(e))
        st.stop()


def game_labels(game_ids) -> dict:
    """game_id -> a label a player recognizes ('vs masterkim (W, win) 2025.05.16').
    Point lookups on the games PK via the plain sqlite connection -- never
    routed through duck_conn (see the audit-dashboard-queries recipe)."""
    ids = [g for g in dict.fromkeys(game_ids) if g]
    if not ids:
        return {}
    sqlite_conn, _ = get_connections()
    qmarks = ",".join("?" * len(ids))
    rows = sqlite_conn.execute(
        f"SELECT id, opponent_name, player_color, outcome_for_player, utc_date "
        f"FROM games WHERE id IN ({qmarks})", ids).fetchall()
    out = {}
    for gid, opp, color, outcome, date in rows:
        c = {"white": "W", "black": "B"}.get(color, "?")
        out[gid] = f"vs {opp or 'unknown'} ({c}, {outcome or '?'}) {date or ''}".strip()
    return out


def navigate_on_row_click(df, key, detail_page, self_page, return_label, column_config=None):
    """One shared drill-down mechanism (Phase 6c.4): renders df with
    native st.dataframe row selection, and on a click, stores the
    selected row's game_id + where to return to, then switches to Game
    Detail. df MUST have a game_id column. Used by every Tactical
    Highlights/Matchups & Opponents panel that lists individual games --
    avoids re-typing the same on_select/session_state wiring per panel.

    Display transforms applied here so every drill-down table behaves the
    same way (UX review 2026-07-05):
    - game_id values are shown as a human game label (opponent, color,
      result, date) -- a raw platform id like 'ODeMleHV' identifies
      nothing to a player. The real id still drives the click handler.
    - ply/blunder_ply columns are converted to chess move numbers
      ((ply+1)//2, kept numeric so column sorting still works).
    - the pandas index is hidden (it's meaningless row positions)."""
    ids = df["game_id"].tolist() if "game_id" in df.columns else []
    display_df = df.reset_index(drop=True).copy()
    if ids:
        labels = game_labels(ids)
        display_df["game_id"] = [labels.get(g, g) for g in display_df["game_id"]]
    for ply_col in ("ply", "blunder_ply"):
        if ply_col in display_df.columns:
            display_df[ply_col] = display_df[ply_col].map(
                lambda p: (int(p) + 1) // 2 if pd.notna(p) else p)
    selection = st.dataframe(display_df, width='stretch', on_select="rerun",
                              selection_mode="single-row", key=key,
                              hide_index=True, column_config=column_config)
    st.caption("Tick the checkbox at the left of a row to open that game's full detail.")
    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        st.session_state["selected_game_id"] = ids[rows[0]]
        st.session_state["return_page"] = self_page
        st.session_state["return_page_label"] = return_label
        st.switch_page(detail_page)


# ---------- get_career_findings() rendering (shared by Insights + Training Queue) ----------
# Promoted from insights_view.py (2026-07-10, Training Queue MVP) once a
# second page needed the exact same chip/action-button rendering for the
# same finding dicts -- same "promote to the one shared home, don't fork a
# second copy" convention as data/_shared.py's _classify_endgame_type
# promotion. Kept in _common.py rather than a new module: this file
# already plays the "cross-page view helper" role for finding-adjacent
# rendering (see game_labels/navigate_on_row_click above), so a second
# shared-helpers module would just split one convention into two homes.

# Severity tier -> sort rank. Insights sorts its full findings list by
# this; Training Queue sorts its weakness-only subset the same way.
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Severity tier -> (chip CSS class, label). Same pattern as
# confidence._TIER_CHIPS, kept here since it's a different axis
# (magnitude, not sample size).
_SEVERITY_CHIPS = {
    "high": ("chip-negative", "High impact"),
    "medium": ("chip-neutral", "Medium impact"),
    "low": ("chip-muted", "Low impact"),
}

# Category -> display label for the small category chip.
CATEGORY_LABELS = {
    "tactical": "Tactics",
    "time": "Time management",
    "defense": "King safety",
    "matchup": "Matchups",
    "giant_killer": "Giant-killing",
    "general": "General",
}

# Findings whose title maps to a Drill Export preset.
# Keys match finding["title"] exactly; values are passed as _drill_preset
# into session_state so drill_export_view can pre-select sources + motif filter.
DRILL_PRESETS = {
    "Piece blunder hot-spot": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": None,
    },
    "Tactical highlights so far": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": None,
    },
    "King moves off the back rank": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": "back_rank_mate",
    },
}


def finding_chips_html(finding) -> str:
    """Confidence + severity + category chips for one finding, as HTML. Empty string if none apply."""
    chips = []
    if finding.get("confidence"):
        badge = confidence.confidence_badge_html(finding["confidence"])
        if badge:
            chips.append(badge)
    severity_entry = _SEVERITY_CHIPS.get(finding.get("severity"))
    if severity_entry:
        cls, label = severity_entry
        chips.append(f'<span class="chip {cls}">{label}</span>')
    category_label = CATEGORY_LABELS.get(finding.get("category"))
    if category_label:
        chips.append(f'<span class="chip chip-neutral">{category_label}</span>')
    return "".join(chips)


def render_finding_actions(finding, drill_export_page, prep_page) -> None:
    drill_preset = DRILL_PRESETS.get(finding["title"])
    if drill_preset and drill_export_page:
        if st.button("→ Export practice positions",
                     key=f"drill_{finding['title']}",
                     help="Open Drill Export with this weakness pre-selected."):
            st.session_state["_drill_preset"] = drill_preset
            st.switch_page(drill_export_page)

    if (finding["title"] == "Toughest opponent"
            and prep_page
            and finding.get("opponent_name")
            # Opponent Prep's fetch is lichess-only -- don't offer to
            # scout a chess.com username (see get_nemesis_opponents).
            and finding.get("opponent_on_lichess", True)):
        if st.button("→ Scout this opponent",
                     key="scout_nemesis",
                     help="Open Opponent Prep with this player's username pre-filled."):
            st.session_state["_prep_username"] = finding["opponent_name"]
            st.switch_page(prep_page)


def render_where_next(links) -> None:
    """Bottom-of-page cross-link panel (roadmap §28 Q1). `links` is a
    list of (label, target_page) pairs; entries whose target_page is
    None are skipped (same "page might not be wired in yet" guard as
    render_finding_actions above)."""
    live_links = [(label, page) for label, page in links if page is not None]
    if not live_links:
        return
    st.divider()
    st.subheader("Where next?")
    cols = st.columns(len(live_links))
    for col, (label, page) in zip(cols, live_links):
        with col:
            if st.button(label, key=f"where_next_{label}", width="stretch"):
                st.switch_page(page)


def persist_filter(key: str) -> None:
    """Mirror a keyed widget's current value into a plain (non-widget)
    session_state entry so it survives st.navigation's page-switch
    widget-state garbage collection -- confirmed live 2026-07-11 (roadmap
    §28 Q3): keyed widget state does NOT survive page-away-and-back on
    its own in this app. Call this right after creating a keyed widget
    whose value should persist across navigation."""
    st.session_state[f"_persist_{key}"] = st.session_state[key]


def restore_filter_default(key: str, fallback) -> None:
    """Call BEFORE a keyed widget is created (Streamlit requires a
    widget's key be set in session_state before the widget call, not
    after). Seeds session_state[key] from the mirror persist_filter()
    wrote the last time this filter was touched, but only if
    session_state[key] isn't already present this run -- i.e. exactly
    the nav-away-and-back case; a value already present this run (e.g.
    from the widget's own rerun) must not be clobbered."""
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(f"_persist_{key}", fallback)
