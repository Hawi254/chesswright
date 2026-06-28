"""Phase 6c.4: Game Endings -- unchanged content from the old tab, just
relocated to its own page and restyled. This section was already a
clean, distinct question ("how do my games actually end") with no
overlap to merge away."""
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


@st.cache_data
def cached_game_end_type_breakdown(_duck_conn):
    return data.get_game_end_type_breakdown(_duck_conn)


def render():
    _sqlite_conn, duck_conn = get_connections()
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
            st.plotly_chart(charts.bar_chart(overall_df, "game_end_type", "n", theme.ACCENT_GOLD),
                             theme=None)

    with st.container(border=True):
        st.subheader("Game end type % by time control")
        if by_tc_df is None or by_tc_df.empty:
            st.info(theme.thin_data_message(0, 1))
        else:
            by_tc_df = by_tc_df.rename(columns=lambda c: _END_TYPE_LABELS.get(c, c))
            st.plotly_chart(charts.heatmap(by_tc_df, theme.SEQUENTIAL_GOLD_COLORSCALE, value_suffix="%"),
                             theme=None)
