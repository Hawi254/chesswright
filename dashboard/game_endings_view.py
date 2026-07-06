"""Phase 6c.4: Game Endings -- unchanged content from the old tab, just
relocated to its own page and restyled. This section was already a
clean, distinct question ("how do my games actually end") with no
overlap to merge away."""
import pandas as pd
import streamlit as st

import charts
import data
import theme
from _common import get_connections

_END_TYPE_LABELS = {
    "resignation":           "Resignation",
    "time_forfeit":          "Time forfeit",
    "checkmate":             "Checkmate",
    "draw_repetition":       "Repetition draw",
    "abandoned":             "Abandoned",
    "insufficient_material": "Insufficient material",
    "draw_agreement":        "Draw by agreement",
    "stalemate":             "Stalemate",
    "draw_50_move_rule":     "50-move rule",
    "unknown":               "Unknown",
}

_RESIGN_REASON_LABELS = {
    "hung_piece":     "Hung a piece",
    "faced_mate":     "Faced a forced mate",
    "time_pressure":  "Time pressure",
    "other":          "Other / gradual decline",
}


@st.cache_data(show_spinner="Loading how your games end…")
def cached_game_end_type_breakdown(_duck_conn):
    return data.get_game_end_type_breakdown(_duck_conn)


@st.cache_data(show_spinner="Computing your endgame results…")
def cached_endgame_type_performance(_sqlite_conn):
    return data.get_endgame_type_performance(_sqlite_conn)


@st.cache_data(show_spinner="Working out why your resignation losses happened…")
def cached_resignation_loss_causes(_duck_conn):
    return data.get_resignation_loss_causes(_duck_conn)


@st.cache_data(show_spinner="Tracking your time-pressure resignations over time…")
def cached_resignation_time_pressure_trend(_duck_conn):
    return data.get_resignation_time_pressure_trend(_duck_conn)


def render():
    sqlite_conn, duck_conn = get_connections()
    st.title("Game Endings")

    with st.container(border=True):
        st.subheader("Game end type breakdown")
        overall_df, by_tc_df = cached_game_end_type_breakdown(duck_conn)
        # Guard against an empty/missing result -- e.g. no games with a
        # known game_end_type analyzed yet. df[x] on a None/empty frame
        # is exactly what crashed here live (TypeError: 'NoneType' object
        # is not subscriptable); same "don't render a broken chart on
        # thin data" philosophy theme.thin_data_message() already exists
        # for, just never wired up to this panel.
        if overall_df is None or overall_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            overall_df = overall_df.copy()
            overall_df["game_end_type"] = overall_df["game_end_type"].map(
                lambda x: _END_TYPE_LABELS.get(x, x))
            st.plotly_chart(charts.bar_chart(overall_df, "game_end_type", "n", theme.ACCENT_GOLD,
                                              x_title="How the game ended", y_title="Games"),
                             theme=None)

    with st.container(border=True):
        st.subheader("Game end type % by time control")
        if by_tc_df is None or by_tc_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            by_tc_df = by_tc_df.rename(columns=lambda c: _END_TYPE_LABELS.get(c, c))
            st.plotly_chart(charts.heatmap(by_tc_df, theme.SEQUENTIAL_GOLD_COLORSCALE, value_suffix="%",
                                            x_title="How the game ended", y_title="Time control",
                                            colorbar_title="% of games"),
                             theme=None)

    with st.container(border=True):
        st.subheader("Performance by endgame type")
        st.caption("Classified at the first ply where the total non-pawn piece count "
                   "drops to the endgame threshold. Queen: at least one queen remains. "
                   "Rook: no queens, at least one rook. Minor piece: bishops or knights "
                   "only. King & pawn: bare kings plus pawns.")
        eg_df = cached_endgame_type_performance(sqlite_conn)
        if eg_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            melted = eg_df[["endgame_type", "win_pct", "draw_pct", "loss_pct"]].melt(
                id_vars="endgame_type", var_name="outcome", value_name="pct")
            melted["outcome"] = melted["outcome"].str.replace("_pct", "", regex=False)
            st.plotly_chart(
                charts.grouped_bar_chart(
                    melted, "endgame_type", "outcome", "pct",
                    colors={"win": theme.POSITIVE, "draw": theme.ACCENT_GOLD,
                            "loss": theme.NEGATIVE},
                    height=300, x_title="Endgame type", y_title="% of games"),
                theme=None)

            stats = eg_df[["endgame_type", "n_games", "acpl", "blunder_rate"]].copy()
            stats["acpl"] = stats["acpl"].apply(
                lambda v: "--" if v is None or pd.isna(v) else f"{v:.1f}")
            stats["blunder_rate"] = stats["blunder_rate"].apply(
                lambda v: "--" if v is None or pd.isna(v) else f"{v:.1f}%")
            st.dataframe(stats, hide_index=True, column_config={
                "endgame_type": "Type",
                "n_games":      st.column_config.NumberColumn(
                    "Games", help="Games that reached this endgame type."),
                "acpl":         st.column_config.Column(
                    "Endgame ACPL", help="Average centipawn loss of your moves inside the "
                                         "endgame -- lower is more accurate."),
                "blunder_rate": st.column_config.Column(
                    "Blunder rate", help="Share of your endgame moves classified as blunders."),
            })

    with st.container(border=True):
        st.subheader("Why resignation losses happen")
        st.caption("Of your losses that ended in resignation: how many followed a "
                   "hanging-piece blunder (the same detection Tactical Highlights' "
                   "hallucination section uses) close to the end, vs. a forced mate "
                   "already on the board with no such hang, vs. resigning while "
                   "critically low on the clock against an opponent with a real time "
                   "advantage, vs. neither -- a gradual decline with no single hang, "
                   "detected forced mate, or clock imbalance. The first two need engine "
                   "analysis to exist at all; the clock check doesn't (it reads straight "
                   "off the game's move times), so games that still have no explanation "
                   "of any kind are tracked and excluded separately rather than being "
                   "silently counted as \"gradual decline.\"")
        reason_df, piece_df, mate_df = cached_resignation_loss_causes(duck_conn)
        if reason_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            n_total = int(reason_df.n.sum())
            n_not_analyzed = int(reason_df.loc[reason_df.reason == "not_analyzed", "n"].sum())
            n_explained = n_total - n_not_analyzed
            st.caption(f"{n_explained} of {n_total} resignation losses "
                       f"({100.0 * n_explained / n_total:.0f}%) have some explanation found "
                       "below -- the rest have neither been analyzed by the engine nor show "
                       "a clock-pressure signal, so no cause could be determined yet.")
            if n_explained == 0:
                st.info(theme.thin_data_message(0, 1))
            else:
                explained_df = reason_df[reason_df.reason != "not_analyzed"].copy()
                explained_df["pct"] = 100.0 * explained_df.n / n_explained
                other_pct = explained_df.loc[explained_df.reason == "other", "pct"].sum()
                if other_pct >= 50:
                    st.caption(f"Of explained resignation losses, {other_pct:.0f}% show "
                               "neither signal near the end -- more often a longer material "
                               "or positional squeeze than one clean hanging piece, forced "
                               "mate, or clock imbalance.")
                explained_df["reason"] = explained_df["reason"].map(
                    lambda x: _RESIGN_REASON_LABELS.get(x, x))
                st.plotly_chart(
                    charts.bar_chart(explained_df, "reason", "pct", theme.ACCENT_GOLD,
                                      x_title="Cause",
                                      y_title="% of explained resignation losses"),
                    theme=None)

                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Which piece hung**")
                    if piece_df.empty:
                        st.info(theme.thin_data_message(0, 1))
                    else:
                        piece_plot = piece_df.copy()
                        piece_plot["piece_name"] = piece_plot["hung_piece"].map(
                            lambda p: str(data.PIECE_NAME.get(p, p)).title())
                        order = {p: i for i, p in enumerate(data.PIECE_ORDER)}
                        piece_plot = piece_plot.sort_values(
                            by="hung_piece", key=lambda s: s.map(order))
                        st.plotly_chart(
                            charts.bar_chart(piece_plot, "piece_name", "pct", theme.NEGATIVE,
                                              x_title="Piece hung",
                                              y_title="% of hung-piece resignation losses"),
                            theme=None)
                with col2:
                    st.write("**How many moves to mate**")
                    if mate_df.empty:
                        st.info(theme.thin_data_message(0, 1))
                    else:
                        st.plotly_chart(
                            charts.bar_chart(mate_df, "bucket", "pct", theme.NEGATIVE,
                                              x_title="Forced mate distance",
                                              y_title="% of faced-mate resignation losses"),
                            theme=None)

    with st.container(border=True):
        st.subheader("Time pressure over time")
        st.caption("Share of each quarter's resignation losses where you were "
                   "critically low on the clock against an opponent with a real time "
                   "lead. This is the only cause above that's honest to trend by "
                   "calendar date right now -- it reads straight off clock times "
                   "already in every synced game, unlike the hung-piece/forced-mate/"
                   "other split, which depends on how much of your history the engine "
                   "has analyzed so far, and that coverage is heavily skewed toward "
                   "your most recent games (analysis prioritizes them), not spread "
                   "evenly across your career.")
        trend_df = cached_resignation_time_pressure_trend(duck_conn)
        if trend_df.empty or trend_df["period"].nunique() < 2:
            st.info(theme.thin_data_message(0, 1))
        else:
            st.plotly_chart(
                charts.line_chart(trend_df, "label", "pct", theme.NEGATIVE,
                                   x_title="Quarter",
                                   y_title="% of resignation losses"),
                theme=None)
