"""Drill Export — build a training set from your analysed games.

Three position sources:
  - Missed tactical motifs (fork, pin, skewer, discovered attack, back-rank, hanging)
  - Decisive moments (biggest win-prob drop per loss in contested positions)
  - Repertoire holes (positions played inconsistently with high CPL)

Two export targets:
  - Lichess Study PGN (multi-chapter, one position per chapter)
  - Anki flash-card CSV (tab-separated: FEN | Side | Engine best | Source | Context)
"""
import streamlit as st

import analytics
import data
from cached_queries import cached_headline_stats
from chess_display import drills_to_pgn_study, drills_to_anki_csv
from _common import get_connections
from theme import thin_data_message

# Slider ceiling for "Max positions per source" -- the decisive-moments
# cache below fetches this many once per session, so the slider's own max
# must never exceed it.
_TOP_N_MAX = 50


@st.cache_data(show_spinner="Collecting missed-tactic positions…")
def _cached_motif_drills_full(_sqlite_conn):
    """One full fetch per session (every motif, no LIMIT -- ~1.2k rows);
    the render body applies the motif filter and top_n slice in pandas.
    Previously this was a duck scan (~0.8s measured) re-run on EVERY rerun
    of this page -- every checkbox/slider/selectbox interaction."""
    return data.get_motif_drill_positions(_sqlite_conn, motif=None, top_n=None)


@st.cache_data(show_spinner="Collecting decisive-moment positions…")
def _cached_decisive_moments(_duck_conn):
    """Fetched once per session at the slider ceiling; sliced per rerun.
    Same reasoning as _cached_motif_drills_full (~0.6s per uncached call)."""
    return data.get_decisive_moment_positions(_duck_conn, top_n=_TOP_N_MAX)


_MOTIF_OPTIONS = [
    ("", "All motifs"),
    ("fork", "Fork"),
    ("pin", "Pin"),
    ("skewer", "Skewer"),
    ("discovered_attack", "Discovered Attack"),
    ("back_rank_mate", "Back-Rank Mate"),
    ("hanging", "Hanging Piece"),
]


def render():
    st.title("Drill Export")
    st.write(
        "Build a training set from your analysed games. "
        "Select which position sources to include, preview the results, "
        "then download as a Lichess Study or Anki deck."
    )

    # Preset injected by insights_view when navigating from a finding's
    # "Export practice positions" button -- consumed once, then cleared.
    preset = st.session_state.pop("_drill_preset", {})

    sqlite_conn, duck_conn = get_connections()

    # Reuses the app-wide headline-stats cache entry instead of a
    # per-rerun duck COUNT (see cached_queries.py).
    n_analyzed = cached_headline_stats(duck_conn, sqlite_conn)["analyzed_games"]

    if n_analyzed < 10:
        st.warning(thin_data_message(n_analyzed, 10))

    # ---------- Source selection ----------
    st.subheader("Sources")
    col1, col2, col3 = st.columns(3)
    with col1:
        include_motifs = st.checkbox(
            "Missed tactics", value=preset.get("include_motifs", True),
            help="Positions where you missed a fork, pin, skewer, etc."
        )
    with col2:
        include_moments = st.checkbox(
            "Decisive moments", value=preset.get("include_moments", True),
            help="The single ply per loss with the biggest win-probability drop in a contested position."
        )
    with col3:
        include_holes = st.checkbox(
            "Repertoire holes", value=preset.get("include_holes", True),
            help="Positions where you play inconsistently and with high CPL."
        )

    top_n = st.slider("Max positions per source", min_value=5, max_value=_TOP_N_MAX,
                      value=20, step=5)

    motif_filter = None
    if include_motifs:
        motif_keys = [k for k, _ in _MOTIF_OPTIONS]
        motif_labels = [label for _, label in _MOTIF_OPTIONS]
        preset_motif = preset.get("motif_filter") or ""
        default_motif_idx = next(
            (i for i, k in enumerate(motif_keys) if k == preset_motif), 0
        )
        chosen_idx = st.selectbox(
            "Motif filter",
            range(len(_MOTIF_OPTIONS)),
            index=default_motif_idx,
            format_func=lambda i: motif_labels[i],
        )
        motif_filter = motif_keys[chosen_idx] or None

    # ---------- Build drill groups ----------
    drill_groups = {}

    if include_motifs:
        df = _cached_motif_drills_full(sqlite_conn)
        if motif_filter:
            df = df[df.motif == motif_filter]
        df = df.head(top_n)
        if not df.empty:
            drill_groups["Missed Tactics"] = df
        else:
            # A checked source silently contributing nothing looks broken --
            # say why. The common cause on a real database is that motif
            # classification has never been run on older analyzed games
            # (same state Tactical Highlights explains with its backfill
            # notice), not that the user has no missed tactics.
            st.info("No missed-tactic positions found. If you have analyzed games but "
                    "see none here, tactic detection may not have run on them yet — "
                    "open Analysis Jobs and use \"Run annotation pass now\".")

    if include_moments:
        df = _cached_decisive_moments(duck_conn).head(top_n)
        if not df.empty:
            drill_groups["Decisive Moments"] = df

    if include_holes:
        with st.spinner("Indexing your repertoire — happens once per new batch of analyzed games…"):
            analytics.ensure_repertoire_holes_cache(sqlite_conn)
        df = data.get_repertoire_holes(sqlite_conn, min_appearances=5, top_n=top_n)
        if not df.empty:
            # most_played_san is the "correct" move for repertoire holes
            df = df.rename(columns={"most_played_san": "best_move_san"})
            drill_groups["Repertoire Holes"] = df

    # ---------- Empty state ----------
    if not drill_groups:
        st.info(
            "No drill positions found yet. "
            "Run more Stockfish analysis and annotation first, then return here."
        )
        return

    # ---------- Preview ----------
    total = sum(len(df) for df in drill_groups.values())
    st.subheader(f"Preview — {total} position(s)")
    for source, df in drill_groups.items():
        with st.expander(f"{source} ({len(df)} positions)"):
            preview_cols = [
                c for c in [
                    "opening", "move_number", "phase", "motif",
                    "cpl", "wp_drop", "hole_score", "best_move_san",
                ]
                if c in df.columns
            ]
            st.dataframe(df[preview_cols], width='stretch', hide_index=True,
                         column_config={
                             "opening": "Opening",
                             "move_number": st.column_config.NumberColumn(
                                 "Move #", help="Move number where the drill position occurs."),
                             "phase": "Phase",
                             "motif": "Tactic type",
                             "cpl": st.column_config.NumberColumn(
                                 "Centipawn loss", format="%d",
                                 help="What the mistake cost, in centipawns (100 = one pawn)."),
                             "wp_drop": st.column_config.NumberColumn(
                                 "Win % dropped", format="percent",
                                 help="How much win probability the move gave away."),
                             "hole_score": st.column_config.NumberColumn(
                                 "Hole score", format="%.0f",
                                 help="Inconsistency × average CPL — bigger = a position you "
                                      "both keep playing differently and keep paying for."),
                             "best_move_san": "Best move",
                         })

    # ---------- Export buttons ----------
    st.subheader("Export")
    col_pgn, col_anki = st.columns(2)

    with col_pgn:
        pgn_str = drills_to_pgn_study(drill_groups)
        st.download_button(
            "Download Lichess Study PGN",
            data=pgn_str,
            file_name="chesswright_drills.pgn",
            mime="text/plain",
            width='stretch',
            disabled=not pgn_str,
        )
        st.caption(
            "Lichess → Study → Import PGN. "
            "Each drill position becomes a separate chapter."
        )

    with col_anki:
        csv_str = drills_to_anki_csv(drill_groups)
        st.download_button(
            "Download Anki CSV",
            data=csv_str,
            file_name="chesswright_drills.txt",
            mime="text/plain",
            width='stretch',
            disabled=not csv_str,
        )
        st.caption(
            "Anki: File → Import, separator: Tab. "
            "Fields: FEN | Side to move | Engine best | Source | Context."
        )
