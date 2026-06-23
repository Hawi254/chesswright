"""
Phase 6c.3: Game Explorer, rebuilt as its own module (was inline in
app.py) as part of the multi-page restructure from 6c.1's information
architecture proposal -- drill-down navigation (click a row -> Game
Detail page) via Streamlit's NATIVE st.dataframe(on_select=...) +
st.switch_page(), not a custom session_state simulation.
"""
import streamlit as st

import data
import theme
from _common import get_connections


@st.cache_data
def cached_game_explorer_table(_duck_conn):
    return data.get_game_explorer_table(_duck_conn)


def render(self_page, detail_page):
    """self_page: this view's own st.Page object, detail_page: Game
    Detail's st.Page -- both passed in by app.py (the single owner of
    the navigation structure) rather than this module constructing its
    own references. self_page is stored as the "return to" target so
    Game Detail's Back button goes to wherever the user actually came
    from, not a hardcoded default."""
    _sqlite_conn, duck_conn = get_connections()

    st.title("Game Explorer")
    explorer_df = cached_game_explorer_table(duck_conn)

    st.write(f"{len(explorer_df):,} games total "
             f"({int(explorer_df.badge_count.gt(0).sum()):,} with at least one badge)")

    with st.container(border=True):
        st.subheader("Filter")
        badge_labels = {label: col for col, (label, _cls) in theme.BADGE_CHIPS.items()}
        st.caption("Comeback: won/drew after being clearly lost. Giant-killing: beat a "
                   "much higher-rated opponent. Brilliant find: a real sacrifice that "
                   "worked. Blunder-fest: several big mistakes in one game. Nail-biter: "
                   "result stayed in doubt until late.")
        selected_badges = st.pills("Filter by story badge", list(badge_labels.keys()),
                                    selection_mode="multi")
        opponent_search = st.text_input("Opponent name contains")

    filtered = explorer_df
    for label in selected_badges:
        filtered = filtered[filtered[badge_labels[label]]]
    if opponent_search:
        filtered = filtered[filtered.opponent_name.str.contains(opponent_search, case=False, na=False)]

    st.write(f"Showing {len(filtered):,} games, sorted by drama score (most dramatic first)")
    st.caption("Drama score: a composite of this game's badges and eval swings -- the "
               "default sort surfaces the most story-worthy games first, not just the "
               "most recent.")
    display_cols = ["game_id", "utc_date", "opponent_name", "player_color", "outcome_for_player",
                     "time_control_category", "opening_family", "badge_count", "drama_score"]
    # reset_index so the selection event's row positions map directly onto
    # this exact dataframe via .iloc -- filtered's original index is
    # whatever survived the badge-filter slicing above, not contiguous.
    display_df = filtered[display_cols].head(200).reset_index(drop=True)
    selection = st.dataframe(display_df, width='stretch', on_select="rerun",
                              selection_mode="single-row", key="explorer_table")
    st.caption("Click a row to open that game's full story.")

    selected_rows = selection.selection.rows if selection and selection.selection else []
    if selected_rows:
        game_id = display_df.iloc[selected_rows[0]].game_id
        st.session_state["selected_game_id"] = game_id
        st.session_state["return_page"] = self_page
        st.session_state["return_page_label"] = "Game Explorer"
        st.switch_page(detail_page)
