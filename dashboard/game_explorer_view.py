"""
Phase 6c.3: Game Explorer, rebuilt as its own module (was inline in
app.py) as part of the multi-page restructure from 6c.1's information
architecture proposal -- drill-down navigation (click a row -> Game
Detail page) via Streamlit's NATIVE st.dataframe(on_select=...) +
st.switch_page(), not a custom session_state simulation.
"""
import streamlit as st

import chess_display
import data
import theme
from _common import get_connections


@st.cache_data(show_spinner="Loading your games…")
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
        st.caption(theme.BADGE_LEGEND)
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
    display_cols = ["game_id", "site", "utc_date", "opponent_name", "player_color",
                     "outcome_for_player", "time_control_category", "opening_family",
                     "badge_count", "drama_score"]
    # reset_index so the selection event's row positions map directly onto
    # this exact dataframe via .iloc -- filtered's original index is
    # whatever survived the badge-filter slicing above, not contiguous.
    display_df = filtered[display_cols].head(200).reset_index(drop=True)
    # The raw game_id ("ODeMleHV") isn't meaningful on its own -- Date +
    # Opponent + Result already identify the game to a reader, so its only
    # real value is as a link back to the original. Real for lichess
    # (games.site is that game's own canonical URL, straight from the PGN
    # header); None for chess.com for now (see chess_display.lichess_game_url's
    # docstring for why that one isn't guessed at). game_id/site stay in
    # display_df (needed below for the row-click lookup and n_no_link) but
    # are left out of column_order, so they're never shown as their own
    # columns.
    # or-"" (empty string), not bare None: this Streamlit version's
    # LinkColumn renders EVERY null flavor (None, NaN, pd.NA) as the
    # literal dim text "None" -- only an empty string gives the intended
    # empty cell (confirmed live with a minimal repro of all five cases
    # against a two-platform database; only reachable with chess.com
    # games present, which is why no lichess-only session ever saw it).
    display_df["lichess_url"] = display_df.apply(
        lambda r: chess_display.lichess_game_url(r.game_id, r.site) or "", axis=1)
    n_no_link = int((display_df["lichess_url"] == "").sum())
    if n_no_link:
        st.caption(f"{n_no_link} game(s) above are from Chess.com and don't have a "
                   f"clickable link back to the original yet.")
    # Platform column (BRIEF §6e's deferred display-only addition): derived
    # from games.site with the same discriminator lichess_game_url uses.
    # Only shown when the database actually holds chess.com games -- for a
    # lichess-only user a column that always reads "Lichess" is noise.
    # Conditioned on the full unfiltered table, not the current view, so
    # the column doesn't appear/vanish as filters change.
    two_platforms = (explorer_df["site"] == chess_display.CHESSCOM_SITE_HEADER).any()
    display_df["platform"] = display_df["site"].map(
        lambda s: "Chess.com" if s == chess_display.CHESSCOM_SITE_HEADER else "Lichess")
    column_order = ["lichess_url", "utc_date", "opponent_name",
                    "player_color", "outcome_for_player",
                    "time_control_category", "opening_family",
                    "badge_count", "drama_score"]
    if two_platforms:
        column_order.insert(1, "platform")
    selection = st.dataframe(display_df, width='stretch', on_select="rerun",
                              hide_index=True,
                              selection_mode="single-row", key="explorer_table",
                              column_order=column_order,
                              column_config={
                                  "lichess_url": st.column_config.LinkColumn(
                                      "Game", display_text="View ↗", width="small"),
                                  "platform": st.column_config.TextColumn(
                                      "Platform", width="small"),
                                  "utc_date": "Date",
                                  "opponent_name": "Opponent",
                                  "player_color": "Color",
                                  "outcome_for_player": "Result",
                                  "time_control_category": "Time Control",
                                  "opening_family": "Opening",
                                  "badge_count": st.column_config.NumberColumn(
                                      "Badges", help="How many story badges this game earned "
                                                     "(see the filter above for what each means)."),
                                  "drama_score": st.column_config.NumberColumn(
                                      "Drama score", format="%d",
                                      help="Composite of badges and evaluation swings -- "
                                           "bigger = more story-worthy. Use it to rank "
                                           "games, not as a precise measure."),
                              })
    st.caption("Tick the checkbox at the left of a row to open that game's full story. "
               "\"View ↗\" opens the original game on lichess (click once to focus, "
               "again to open).")

    selected_rows = selection.selection.rows if selection and selection.selection else []
    if selected_rows:
        game_id = display_df.iloc[selected_rows[0]].game_id
        st.session_state["selected_game_id"] = game_id
        st.session_state["return_page"] = self_page
        st.session_state["return_page_label"] = "Game Explorer"
        st.switch_page(detail_page)
