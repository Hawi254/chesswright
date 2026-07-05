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
import chess_display
import data
import theme
from _common import get_connections


@st.cache_data(show_spinner="Computing blunder rates under time pressure…")
def cached_blunder_rate_by_time_pressure(_duck_conn):
    return data.get_blunder_rate_by_time_pressure(_duck_conn)


@st.cache_data(show_spinner="Computing accuracy by time control…")
def cached_acpl_by_time_control(_sqlite_conn):
    return data.get_acpl_by_time_control(_sqlite_conn)


@st.cache_data(show_spinner="Computing accuracy in sharp positions…")
def cached_sharpness_blunder_correlation(_duck_conn):
    return data.get_sharpness_blunder_correlation(_duck_conn)


@st.cache_data(show_spinner="Computing accuracy by thinking time…")
def cached_thinking_time_blunder_correlation(_duck_conn):
    return data.get_thinking_time_blunder_correlation(_duck_conn)


@st.cache_data(show_spinner="Computing accuracy by game phase…")
def cached_phase_accuracy(_sqlite_conn):
    return data.get_phase_accuracy(_sqlite_conn)


@st.cache_data(show_spinner="Comparing games after a win vs. after a loss…")
def cached_prior_outcome_performance(_sqlite_conn):
    return data.get_prior_outcome_performance(_sqlite_conn)


@st.cache_data(show_spinner="Computing accuracy across playing sessions…")
def cached_session_position_performance(_sqlite_conn):
    return data.get_session_position_performance(_sqlite_conn)


@st.cache_data(show_spinner="Building your day-and-hour win-rate map…")
def cached_day_hour_heatmap(_duck_conn):
    return data.get_day_hour_heatmap(_duck_conn)


@st.cache_data(show_spinner="Computing results by position type…")
def cached_material_structure_table(_sqlite_conn, structure_type):
    return data.get_material_structure_table(_sqlite_conn, structure_type=structure_type)


@st.cache_data(show_spinner="Computing accuracy piece by piece…")
def cached_piece_movement_patterns(_duck_conn):
    return data.get_piece_movement_patterns(_duck_conn)


@st.cache_data(show_spinner="Computing piece blunders by game phase…")
def cached_piece_blunder_by_phase(_sqlite_conn):
    return data.get_piece_blunder_by_phase(_sqlite_conn)


@st.cache_data(show_spinner="Computing piece blunders by position sharpness…")
def cached_piece_blunder_by_sharpness(_duck_conn):
    return data.get_piece_blunder_by_sharpness(_duck_conn)


@st.cache_data(show_spinner="Analyzing bishop square-color patterns…")
def cached_bishop_square_color_performance(_duck_conn):
    return data.get_bishop_square_color_performance(_duck_conn)


@st.cache_data(show_spinner="Analyzing back-rank patterns…")
def cached_rook_king_backrank_performance(_duck_conn):
    return data.get_rook_king_backrank_performance(_duck_conn)


@st.cache_data(show_spinner="Comparing castled vs. uncastled games…")
def cached_castling_performance(_duck_conn):
    return data.get_castling_performance(_duck_conn)


@st.cache_data(show_spinner="Finding the moments your losses were decided…")
def cached_decisive_moments(_duck_conn):
    return data.get_decisive_moments(_duck_conn)


def render():
    sqlite_conn, duck_conn = get_connections()
    st.title("Patterns & Tendencies")
    st.caption("ACPL (average centipawn loss) measures move accuracy -- lower is better. "
               "Every panel below asks the same question under a different condition: when "
               "do you actually play worse, and when do you play better?")

    tab_clock, tab_rhythm, tab_position, tab_pieces, tab_turning = st.tabs(
        ["Clock & Time", "Game Context", "Positions", "Piece Handling", "Turning Points"])

    # Each tab body is its own @st.fragment: st.tabs doesn't scope
    # reruns by itself (every tab's code runs on every rerun regardless
    # of which one is visually active), so without this, adjusting the
    # "Structure type" radio in Positions (or "View by" in Piece
    # Handling) would re-run and re-render all five tabs' charts, not
    # just the one whose widget changed. No cross-tab state/data
    # dependency between any of the five (confirmed before converting,
    # unlike openings_view.py -- see BRIEF.md §6h's Tier 2 plan).
    with tab_clock:
        _render_tab_clock(sqlite_conn, duck_conn)
    with tab_rhythm:
        _render_tab_rhythm(sqlite_conn, duck_conn)
    with tab_position:
        _render_tab_position(sqlite_conn, duck_conn)
    with tab_pieces:
        _render_tab_pieces(sqlite_conn, duck_conn)
    with tab_turning:
        _render_tab_turning(duck_conn)


@st.fragment
def _render_tab_clock(sqlite_conn, duck_conn):
    with st.container(border=True):
        st.subheader("Blunder rate vs. time pressure (clock remaining)")
        tp_df = cached_blunder_rate_by_time_pressure(duck_conn)
        st.plotly_chart(charts.bar_chart(tp_df, "bucket", "blunder_rate", theme.NEGATIVE,
                                          x_title="Clock remaining", y_title="Blunder rate (% of moves)"),
                         theme=None)

    with st.container(border=True):
        st.subheader("ACPL by time control")
        tc_df = cached_acpl_by_time_control(sqlite_conn)
        st.plotly_chart(charts.bar_chart(tc_df, "time_control", "acpl", theme.NEGATIVE,
                                          x_title="Time control", y_title="ACPL (lower = more accurate)"),
                         theme=None)

    with st.container(border=True):
        st.subheader("Blunder rate vs. thinking time")
        st.caption("Time spent on this move before playing it. Counter-intuitively, longer "
                   "thinking time doesn't always mean fewer blunders -- hard positions tend "
                   "to get more thought AND produce more mistakes.")
        think_df = cached_thinking_time_blunder_correlation(duck_conn)
        st.plotly_chart(charts.bar_chart(think_df, "bucket", "blunder_rate", theme.NEGATIVE,
                                          x_title="Time spent on the move", y_title="Blunder rate (% of moves)"),
                         theme=None)


@st.fragment
def _render_tab_rhythm(sqlite_conn, duck_conn):
    with st.container(border=True):
        st.subheader("ACPL by game phase")
        phase_df = cached_phase_accuracy(sqlite_conn)
        st.plotly_chart(charts.bar_chart(phase_df, "phase", "acpl", theme.NEGATIVE,
                                          x_title="Game phase", y_title="ACPL (lower = more accurate)"),
                         theme=None)

    with st.container(border=True):
        st.subheader("Performance after a win vs. after a loss")
        outcome_df = cached_prior_outcome_performance(sqlite_conn).copy()
        # Display-layer relabel only -- the cached DataFrame keeps the raw
        # 'first_game_of_session' bucket value used for ordering.
        outcome_df["bucket"] = outcome_df["bucket"].replace(
            {"first_game_of_session": "first game of session"})
        st.plotly_chart(charts.bar_chart(outcome_df, "bucket", "acpl", theme.NEGATIVE,
                                          x_title="Situation", y_title="ACPL (lower = more accurate)"),
                         theme=None)

    with st.container(border=True):
        st.subheader("Performance by position within a session")
        session_df = cached_session_position_performance(sqlite_conn)
        st.plotly_chart(charts.bar_chart(session_df, "position", "acpl", theme.NEGATIVE,
                                          x_title="Game within the playing session", y_title="ACPL (lower = more accurate)"),
                         theme=None)

    with st.container(border=True):
        st.subheader("Win rate heatmap: day of week × hour of day (UTC)")
        heatmap_df = cached_day_hour_heatmap(duck_conn)
        # day_of_week is stored 0=Monday .. 6=Sunday (migrations/0001_init.sql)
        # -- rename for display only, the cached pivot is untouched.
        heatmap_df = heatmap_df.rename(index={0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu",
                                              4: "Fri", 5: "Sat", 6: "Sun"})
        st.plotly_chart(
            charts.heatmap(heatmap_df, theme.DIVERGING_COLORSCALE, value_suffix="%",
                           x_title="Hour of day (UTC)", y_title="Day of week",
                           colorbar_title="Win %"),
            theme=None)


@st.fragment
def _render_tab_position(sqlite_conn, duck_conn):
    with st.container(border=True):
        st.subheader("Blunder rate vs. position sharpness")
        st.caption("How forced was the position -- the engine's gap between its best and "
                   "second-best move. A larger gap means fewer reasonable alternatives, "
                   "putting more pressure on finding the right one.")
        sharp_df = cached_sharpness_blunder_correlation(duck_conn)
        st.plotly_chart(charts.bar_chart(sharp_df, "bucket", "blunder_rate", theme.NEGATIVE,
                                          x_title="Position sharpness (engine best-move gap)", y_title="Blunder rate (% of moves)"),
                         theme=None)

    with st.container(border=True):
        st.subheader("Material structure win rate")
        st.caption("Win/draw/loss record and ACPL grouped by the kind of position you ended up "
                   "in (rook endgame, opposite-colored bishops, queenless middlegame, etc.) -- "
                   "a tendency in your own play, not about who you were facing.")
        structure_type = st.radio("Structure type", ["endgame", "middlegame"], horizontal=True,
                                   key="material_structure_type")
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
        # Display-layer only -- chess_utils.material_signature()'s raw
        # "Q1R1B1P6vQ1R1B1P6" encoding is accurate but not meant for a
        # reader; cached_material_structure_table's own DataFrame (and
        # its st.cache_data entry) is untouched.
        display_df["material_sig"] = display_df["material_sig"].apply(
            chess_display.material_sig_str)
        st.dataframe(display_df, width='stretch', hide_index=True, column_config={
            "material_sig": "Position Type",
            "n_games": "Games",
            "win_pct": st.column_config.NumberColumn("Win %", format="%.1f"),
            "draw_pct": st.column_config.NumberColumn("Draw %", format="%.1f"),
            "loss_pct": st.column_config.NumberColumn("Loss %", format="%.1f"),
            "acpl": st.column_config.Column(
                "ACPL", help="Average centipawn loss across your analyzed moves in this "
                             "position type -- lower is more accurate."),
            "n_analyzed": st.column_config.Column(
                "Analyzed games", help="How many of these games have engine analysis -- "
                                       "ACPL only counts analyzed games."),
        })


@st.fragment
def _render_tab_pieces(sqlite_conn, duck_conn):
    with st.container(border=True):
        st.subheader("Piece-handling: which piece do you misplay most")
        st.caption("Blunder rate and accuracy broken down by which piece was moved.")
        piece_df = cached_piece_movement_patterns(duck_conn)
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                charts.bar_chart(piece_df, "piece_name", "acpl", theme.NEGATIVE,
                                  x_title="Piece moved", y_title="ACPL (lower = more accurate)"), theme=None)
        with col2:
            st.plotly_chart(
                charts.bar_chart(piece_df, "piece_name", "blunder_rate", theme.NEGATIVE,
                                  x_title="Piece moved", y_title="Blunder rate (% of moves)"),
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
                charts.grouped_bar_chart(piece_phase_df, "piece_name", "phase", "blunder_rate",
                                          x_title="Piece moved", y_title="Blunder rate (% of moves)"),
                theme=None)
        else:
            sharp_piece_df = cached_piece_blunder_by_sharpness(duck_conn)
            st.plotly_chart(
                charts.grouped_bar_chart(
                    sharp_piece_df, "piece_name", "bucket", "blunder_rate",
                    x_title="Piece moved", y_title="Blunder rate (% of moves)"),
                theme=None)

    with st.container(border=True):
        st.subheader("Bishop square color and rook/king back-rank handling")
        st.caption("Bishop blunder rate split by whether it moves to its own square colour "
                   "(\"bad bishop\" positioning) vs. the opposite colour. Back-rank: rook and "
                   "king blunder rates split by whether the piece is on the back rank or elsewhere.")
        bishop_df = cached_bishop_square_color_performance(duck_conn)
        st.plotly_chart(
            charts.bar_chart(bishop_df, "square_color", "blunder_rate", theme.ACCENT_GOLD,
                              x_title="Destination square color", y_title="Blunder rate (% of moves)"),
            theme=None)
        backrank_df = cached_rook_king_backrank_performance(duck_conn)
        st.plotly_chart(
            charts.grouped_bar_chart(backrank_df, "piece_name", "location", "acpl",
                                     colors={"back rank": theme.POSITIVE,
                                             "elsewhere": theme.NEGATIVE},
                                     x_title="Piece", y_title="ACPL (lower = more accurate)"),
            theme=None)

    with st.container(border=True):
        st.subheader("Castling and king safety")
        st.caption("Restricted to games lasting 30+ plies (the 95th percentile of the real "
                   "castling-ply distribution), so short games that ended before castling was "
                   "realistic aren't miscounted as \"chose not to castle.\"")
        castle_win_df, castle_acpl_df = cached_castling_performance(duck_conn)
        st.plotly_chart(
            charts.bar_chart(castle_win_df, "status", "win_pct", theme.POSITIVE,
                              x_title="Castling", y_title="Win rate (%)"), theme=None)
        n_no_castle_analyzed = int(castle_acpl_df.loc[
            castle_acpl_df.status == "did not castle", "n_games"].sum())
        st.caption(
            f"ACPL: {', '.join(f'{r.status}={r.acpl:.1f} ({r.n_games} games)' for r in castle_acpl_df.itertuples())} "
            f"-- the \"did not castle\" side ({n_no_castle_analyzed} games) is a thin sample, "
            f"treat as suggestive.")


@st.fragment
def _render_tab_turning(duck_conn):
    with st.container(border=True):
        st.subheader("When do your losses get decided?")
        st.caption("For each loss, this finds the single move in a contested position "
                   "(win probability between 30–70%) where the most win probability was "
                   "dropped in one move. Aggregating across losses reveals whether your "
                   "games slip away in the opening, middlegame, or endgame — and whether "
                   "it happens when the clock is full or when you're under pressure.")
        dm_df = cached_decisive_moments(duck_conn)
        if dm_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            dm_df = dm_df.copy()
            n_losses = len(dm_df)
            median_move = int(dm_df.move_number.median())
            most_common_phase = dm_df.phase.mode().iloc[0] if not dm_df.phase.mode().empty else "—"
            st.metric(
                f"Decisive moment profile ({n_losses} losses with a contested position)",
                f"Typically move {median_move} ({most_common_phase})")

            col_mn, col_ph = st.columns(2)
            with col_mn:
                st.write("**By move number**")
                bins = [0, 6, 11, 16, 21, 26, 31, 41, 60, 9999]
                labels = ["1–5", "6–10", "11–15", "16–20", "21–25",
                          "26–30", "31–40", "41–60", "60+"]
                dm_df["move_bucket"] = pd.cut(
                    dm_df.move_number, bins=bins, labels=labels, right=False)
                mn_df = (dm_df.groupby("move_bucket", observed=True)
                         .size().reset_index(name="n_losses"))
                st.plotly_chart(
                    charts.bar_chart(mn_df, "move_bucket", "n_losses",
                                     theme.NEGATIVE, height=240,
                                     x_title="Move number", y_title="Losses"),
                    theme=None)

            with col_ph:
                st.write("**By game phase**")
                phase_order = ["opening", "middlegame", "endgame"]
                ph_df = (dm_df.groupby("phase").size().reset_index(name="n_losses")
                         .set_index("phase").reindex(phase_order).dropna()
                         .reset_index())
                st.plotly_chart(
                    charts.bar_chart(ph_df, "phase", "n_losses",
                                     theme.NEGATIVE, height=240,
                                     x_title="Game phase", y_title="Losses"),
                    theme=None)

            clock_df = dm_df.dropna(subset=["clock_fraction"])
            if not clock_df.empty:
                st.write("**By clock remaining at the decisive moment**")
                clock_rows = []
                for label, lo, hi in data.TIME_PRESSURE_BUCKETS:
                    n = int(((clock_df.clock_fraction >= lo) &
                             (clock_df.clock_fraction < hi)).sum())
                    if n:
                        clock_rows.append({"bucket": label, "n_losses": n})
                if clock_rows:
                    st.plotly_chart(
                        charts.bar_chart(
                            pd.DataFrame(clock_rows), "bucket", "n_losses",
                            theme.NEGATIVE, height=220,
                            x_title="Clock remaining", y_title="Losses"),
                        theme=None)
                n_no_clock = n_losses - len(clock_df)
                if n_no_clock:
                    st.caption(f"{n_no_clock} of {n_losses} losses excluded from clock "
                               "chart — no clock data for those games.")
