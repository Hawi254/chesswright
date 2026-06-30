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

import data
from chess_display import drills_to_pgn_study, drills_to_anki_csv
from _common import get_connections
from theme import thin_data_message


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

    _, duck_conn = get_connections()

    n_analyzed = duck_conn.execute(
        "SELECT COUNT(*) FROM db.games WHERE analysis_status='done'"
    ).fetchone()[0]

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

    top_n = st.slider("Max positions per source", min_value=5, max_value=50, value=20, step=5)

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
        df = data.get_motif_drill_positions(duck_conn, motif=motif_filter, top_n=top_n)
        if not df.empty:
            drill_groups["Missed Tactics"] = df

    if include_moments:
        df = data.get_decisive_moment_positions(duck_conn, top_n=top_n)
        if not df.empty:
            drill_groups["Decisive Moments"] = df

    if include_holes:
        df = data.get_repertoire_holes(duck_conn, min_appearances=5, top_n=top_n)
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
            st.dataframe(df[preview_cols], width='stretch')

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
