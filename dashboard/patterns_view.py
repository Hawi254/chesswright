"""
Phase 6c.4: Patterns & Tendencies -- merges the old Time & Pressure and
Patterns tabs (both were really the same question: "when do I play worse,
and when do I play better") and brings in material-structure win-rate
from the old Position Explorer tab (moved here after a real
inconsistency was caught: "do queenless middlegames favor me" is a
tendency question about my own play, not about an opponent -- it doesn't
belong in Matchups & Opponents just because it used to sit next to
Position Explorer's other panel).
"""
import pandas as pd
import streamlit as st

import charts
import data
import theme
from _common import get_connections


@st.cache_data
def cached_blunder_rate_by_time_pressure(_duck_conn):
    return data.get_blunder_rate_by_time_pressure(_duck_conn)


@st.cache_data
def cached_acpl_by_time_control(_sqlite_conn):
    return data.get_acpl_by_time_control(_sqlite_conn)


@st.cache_data
def cached_sharpness_blunder_correlation(_duck_conn):
    return data.get_sharpness_blunder_correlation(_duck_conn)


@st.cache_data
def cached_thinking_time_blunder_correlation(_duck_conn):
    return data.get_thinking_time_blunder_correlation(_duck_conn)


@st.cache_data
def cached_phase_accuracy(_sqlite_conn):
    return data.get_phase_accuracy(_sqlite_conn)


@st.cache_data
def cached_prior_outcome_performance(_sqlite_conn):
    return data.get_prior_outcome_performance(_sqlite_conn)


@st.cache_data
def cached_session_position_performance(_sqlite_conn):
    return data.get_session_position_performance(_sqlite_conn)


@st.cache_data
def cached_day_hour_heatmap(_duck_conn):
    return data.get_day_hour_heatmap(_duck_conn)


@st.cache_data
def cached_material_structure_table(_sqlite_conn, structure_type):
    return data.get_material_structure_table(_sqlite_conn, structure_type=structure_type)


@st.cache_data
def cached_piece_movement_patterns(_duck_conn):
    return data.get_piece_movement_patterns(_duck_conn)


@st.cache_data
def cached_piece_blunder_by_phase(_sqlite_conn):
    return data.get_piece_blunder_by_phase(_sqlite_conn)


@st.cache_data
def cached_piece_blunder_by_sharpness(_duck_conn):
    return data.get_piece_blunder_by_sharpness(_duck_conn)


@st.cache_data
def cached_bishop_square_color_performance(_duck_conn):
    return data.get_bishop_square_color_performance(_duck_conn)


@st.cache_data
def cached_rook_king_backrank_performance(_duck_conn):
    return data.get_rook_king_backrank_performance(_duck_conn)


@st.cache_data
def cached_castling_performance(_duck_conn):
    return data.get_castling_performance(_duck_conn)


def render():
    sqlite_conn, duck_conn = get_connections()
    st.title("Patterns & Tendencies")
    st.caption("ACPL (average centipawn loss) measures move accuracy -- lower is better. "
               "Every panel below asks the same question under a different condition: when "
               "do you actually play worse, and when do you play better?")

    tab_clock, tab_rhythm, tab_position, tab_pieces = st.tabs(
        ["Clock & Time", "Game Context", "Positions", "Piece Handling"])

    with tab_clock:
        with st.container(border=True):
            st.subheader("Blunder rate vs. time pressure (clock remaining)")
            tp_df = cached_blunder_rate_by_time_pressure(duck_conn)
            st.plotly_chart(charts.bar_chart(tp_df, "bucket", "blunder_rate", theme.NEGATIVE),
                             theme=None)

        with st.container(border=True):
            st.subheader("ACPL by time control")
            tc_df = cached_acpl_by_time_control(sqlite_conn)
            st.plotly_chart(charts.bar_chart(tc_df, "time_control", "acpl", theme.NEGATIVE),
                             theme=None)

        with st.container(border=True):
            st.subheader("Blunder rate vs. thinking time")
            st.caption("Time spent on this move before playing it. Counter-intuitively, longer "
                       "thinking time doesn't always mean fewer blunders -- hard positions tend "
                       "to get more thought AND produce more mistakes.")
            think_df = cached_thinking_time_blunder_correlation(duck_conn)
            st.plotly_chart(charts.bar_chart(think_df, "bucket", "blunder_rate", theme.NEGATIVE),
                             theme=None)

    with tab_rhythm:
        with st.container(border=True):
            st.subheader("ACPL by game phase")
            phase_df = cached_phase_accuracy(sqlite_conn)
            st.plotly_chart(charts.bar_chart(phase_df, "phase", "acpl", theme.NEGATIVE),
                             theme=None)

        with st.container(border=True):
            st.subheader("Performance after a win vs. after a loss")
            outcome_df = cached_prior_outcome_performance(sqlite_conn)
            st.plotly_chart(charts.bar_chart(outcome_df, "bucket", "acpl", theme.NEGATIVE),
                             theme=None)

        with st.container(border=True):
            st.subheader("Performance by position within a session")
            session_df = cached_session_position_performance(sqlite_conn)
            st.plotly_chart(charts.bar_chart(session_df, "position", "acpl", theme.NEGATIVE),
                             theme=None)

        with st.container(border=True):
            st.subheader("Win rate heatmap: day of week × hour of day (UTC)")
            heatmap_df = cached_day_hour_heatmap(duck_conn)
            st.plotly_chart(
                charts.heatmap(heatmap_df, theme.DIVERGING_COLORSCALE, value_suffix="%"),
                theme=None)

    with tab_position:
        with st.container(border=True):
            st.subheader("Blunder rate vs. position sharpness")
            st.caption("How forced was the position -- the engine's gap between its best and "
                       "second-best move. A larger gap means fewer reasonable alternatives, "
                       "putting more pressure on finding the right one.")
            sharp_df = cached_sharpness_blunder_correlation(duck_conn)
            st.plotly_chart(charts.bar_chart(sharp_df, "bucket", "blunder_rate", theme.NEGATIVE),
                             theme=None)

        with st.container(border=True):
            st.subheader("Material structure win rate")
            st.caption("Win/draw/loss record and ACPL grouped by the kind of position you ended up "
                       "in (rook endgame, opposite-colored bishops, queenless middlegame, etc.) -- "
                       "a tendency in your own play, not about who you were facing.")
            structure_type = st.radio("Structure type", ["endgame", "middlegame"], horizontal=True)
            structure_df = cached_material_structure_table(sqlite_conn, structure_type)
            # win_pct/draw_pct/loss_pct come from ALL games (ingest-time, no
            # engine needed) and are always populated; acpl/n_analyzed need an
            # engine pass, so most structures show acpl=NaN right now (185 of
            # 32,295 games analyzed) -- caught by looking at real output, not
            # assumed fine: a bare NaN in a table reads as broken, not as
            # "not analyzed yet". Explicit text instead, only where it's
            # actually missing.
            n_unanalyzed = int((structure_df.n_analyzed == 0).sum())
            if n_unanalyzed:
                st.caption(f"ACPL is blank for {n_unanalyzed} of {len(structure_df)} structures "
                           f"-- no analyzed games have reached them yet, not a data error.")
            display_df = structure_df.copy()
            display_df["acpl"] = display_df["acpl"].apply(
                lambda v: "--" if pd.isna(v) else f"{v:.1f}")
            st.dataframe(display_df, width='stretch', column_config={
                "material_sig": "Position Type",
                "n_games": "Games",
                "win_pct": st.column_config.NumberColumn("Win %", format="%.1f"),
                "draw_pct": st.column_config.NumberColumn("Draw %", format="%.1f"),
                "loss_pct": st.column_config.NumberColumn("Loss %", format="%.1f"),
                "acpl": "ACPL",
                "n_analyzed": "Analyzed",
            })

    with tab_pieces:
        with st.container(border=True):
            st.subheader("Piece-handling: which piece do you misplay most")
            st.caption("Blunder rate and accuracy broken down by which piece was moved.")
            piece_df = cached_piece_movement_patterns(duck_conn)
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(
                    charts.bar_chart(piece_df, "piece_name", "acpl", theme.NEGATIVE), theme=None)
            with col2:
                st.plotly_chart(
                    charts.bar_chart(piece_df, "piece_name", "blunder_rate", theme.NEGATIVE),
                    theme=None)

        with st.container(border=True):
            st.subheader("Piece-handling by game phase and position sharpness")
            st.caption("How each piece's blunder rate varies by game phase and position sharpness -- "
                       "look for whether the piece patterns above hold in every context or shift "
                       "depending on when in the game you're playing.")
            view_by = st.radio("View by", ["game phase", "position sharpness"], horizontal=True,
                                key="piece_view_by")
            if view_by == "game phase":
                piece_phase_df = cached_piece_blunder_by_phase(sqlite_conn)
                st.plotly_chart(
                    charts.grouped_bar_chart(piece_phase_df, "piece_name", "phase", "blunder_rate"),
                    theme=None)
            else:
                sharp_piece_df = cached_piece_blunder_by_sharpness(duck_conn)
                st.plotly_chart(
                    charts.grouped_bar_chart(
                        sharp_piece_df, "piece_name", "bucket", "blunder_rate"),
                    theme=None)

        with st.container(border=True):
            st.subheader("Bishop square color and rook/king back-rank handling")
            st.caption("Bishop blunder rate split by whether it moves to its own square colour "
                       "(\"bad bishop\" positioning) vs. the opposite colour. Back-rank: rook and "
                       "king blunder rates split by whether the piece is on the back rank or elsewhere.")
            bishop_df = cached_bishop_square_color_performance(duck_conn)
            st.plotly_chart(
                charts.bar_chart(bishop_df, "square_color", "blunder_rate", theme.ACCENT_GOLD),
                theme=None)
            backrank_df = cached_rook_king_backrank_performance(duck_conn)
            st.plotly_chart(
                charts.grouped_bar_chart(backrank_df, "piece_name", "location", "acpl",
                                         colors={"back rank": theme.POSITIVE,
                                                 "elsewhere": theme.NEGATIVE}),
                theme=None)

        with st.container(border=True):
            st.subheader("Castling and king safety")
            st.caption("Restricted to games lasting 30+ plies (the 95th percentile of the real "
                       "castling-ply distribution), so short games that ended before castling was "
                       "realistic aren't miscounted as \"chose not to castle.\"")
            castle_win_df, castle_acpl_df = cached_castling_performance(duck_conn)
            st.plotly_chart(
                charts.bar_chart(castle_win_df, "status", "win_pct", theme.POSITIVE), theme=None)
            n_no_castle_analyzed = int(castle_acpl_df.loc[
                castle_acpl_df.status == "did not castle", "n_games"].sum())
            st.caption(
                f"ACPL: {', '.join(f'{r.status}={r.acpl:.1f} ({r.n_games} games)' for r in castle_acpl_df.itertuples())} "
                f"-- the \"did not castle\" side ({n_no_castle_analyzed} games) is a thin sample, "
                f"treat as suggestive.")
