"""
Phase 6c.4: Matchups & Opponents -- merges the old Matchups and Opponents
tabs (rating-band performance and named-opponent performance are the
same question -- "who do I struggle against" -- at different
granularity). "Win rate by color, rating-adjusted" moved here from
Overview: it's about rating-adjusted performance specifically, which is
this page's whole theme, not a landing-page fact.

Comeback/collapse game lists were a raw game-ID text dump in an
st.expander before 6c.4 -- now a real clickable table, per 6c.1's
drill-down-navigation principle: every game_id anywhere should lead to
that game's full story, not just more text inline.
"""
import pandas as pd
import streamlit as st

import charts
import claude_narrative
import data
import theme
from _common import get_connections, navigate_on_row_click
from cached_queries import cached_headline_stats


@st.cache_data(show_spinner="Computing win rates by rating difference…")
def cached_win_rate_by_rating_diff(_duck_conn):
    return data.get_win_rate_by_rating_diff(_duck_conn)


@st.cache_data(show_spinner="Counting upset wins and losses…")
def cached_giant_killing_counts(_duck_conn):
    return data.get_giant_killing_counts(_duck_conn)


@st.cache_data(show_spinner="Finding comebacks and collapses…")
def cached_comeback_collapse_counts(_duck_conn):
    return data.get_comeback_collapse_counts(_duck_conn)


@st.cache_data(show_spinner="Comparing your White and Black results…")
def cached_color_performance_by_rating(_duck_conn):
    return data.get_color_performance_by_rating(_duck_conn)


@st.cache_data(show_spinner="Ranking your opponents…")
def cached_nemesis_opponents(_duck_conn, min_games):
    return data.get_nemesis_opponents(_duck_conn, min_games=min_games)




def _clickable_game_ids(game_ids, key, detail_page, self_page):
    """One consistent drill-down pattern for a bare list of game_ids,
    reused by both the comeback and collapse tables below."""
    if not game_ids:
        st.write("None.")
        return
    df = pd.DataFrame({"game_id": game_ids})
    navigate_on_row_click(df, key, detail_page, self_page, "Matchups & Opponents",
                          column_config={"game_id": "Game"})


def render(self_page, detail_page, prep_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.title("Matchups & Opponents")

    with st.container(border=True):
        st.subheader("Win rate vs. rating differential")
        st.caption("Your rating minus the opponent's: bars left of 0 are games against "
                   "higher-rated opponents, right of 0 against lower-rated ones.")
        rd_df = cached_win_rate_by_rating_diff(duck_conn)
        st.plotly_chart(charts.bar_chart(rd_df, "band", "win_pct", theme.POSITIVE,
                                          x_title="Rating difference (you minus opponent)",
                                          y_title="Win rate (%)"), theme=None)

    with st.container(border=True):
        st.subheader("Win rate by color, rating-adjusted")
        st.caption("Confirms White's edge holds at every rating bucket, not just on average.")
        color_rating_df = cached_color_performance_by_rating(duck_conn).rename_axis("Rating Bucket")
        st.dataframe(color_rating_df, width='stretch', column_config={
            "black": st.column_config.NumberColumn("Black (win %)", format="%.1f"),
            "white": st.column_config.NumberColumn("White (win %)", format="%.1f"),
        })

    with st.container(border=True):
        st.subheader("Giant-killing and collapses (rating-based)")
        st.caption("Distinct from the eval-based comebacks/collapses below -- this is purely "
                   "about rating differential: did you beat a much stronger opponent, or lose "
                   "to a much weaker one.")
        gk = cached_giant_killing_counts(duck_conn)
        # No 300+ rating-gap games yet is the common case on a fresh
        # install with few synced games, not a rare edge case -- avoid
        # dividing by zero rather than assuming there's always at least
        # one underdog/favorite game (true of the original project's
        # large existing dataset, not true of a small starter batch).
        upset_pct = (100.0 * gk['n_upsets'] / gk['n_underdog_games']
                     if gk['n_underdog_games'] else None)
        collapse_pct = (100.0 * gk['n_collapses'] / gk['n_favorite_games']
                         if gk['n_favorite_games'] else None)
        col1, col2 = st.columns(2)
        # Plain sentences, not st.metric deltas -- the delta arrow reads as
        # "up vs. some earlier period", which these shares are not.
        col1.metric("Giant-killing wins (300+ underdog)",
                    f"{gk['n_upsets']} / {gk['n_underdog_games']}",
                    help="Games won when the opponent was rated 300+ points above you, "
                         "out of all games against such opponents.")
        if upset_pct is not None:
            col1.caption(f"You win {upset_pct:.1f}% of games as a heavy underdog.")
        col2.metric("Collapse losses (300+ favorite)",
                    f"{gk['n_collapses']} / {gk['n_favorite_games']}",
                    help="Games lost when the opponent was rated 300+ points below you, "
                         "out of all games against such opponents.")
        if collapse_pct is not None:
            col2.caption(f"You lose {collapse_pct:.1f}% of games as a heavy favorite.")

    with st.container(border=True):
        st.subheader("Comebacks and collapses (eval-based)")
        st.caption("Comeback: you won or drew a game the engine judged clearly lost for you "
                   "at some point. Collapse: the reverse. Open a list and tick a row's "
                   "checkbox to see that game's full story.")
        cc = cached_comeback_collapse_counts(duck_conn)
        col1, col2 = st.columns(2)
        col1.metric("Comebacks", cc["n_comebacks"])
        col2.metric("Collapses", cc["n_collapses"])
        with st.expander(f"Comeback games ({cc['n_comebacks']})"):
            _clickable_game_ids(cc["comeback_game_ids"], "comeback_games", detail_page, self_page)
        with st.expander(f"Collapse games ({cc['n_collapses']})"):
            _clickable_game_ids(cc["collapse_game_ids"], "collapse_games", detail_page, self_page)

    with st.container(border=True):
        _render_nemesis_section(sqlite_conn, duck_conn, prep_page)


def _scout_on_row_click(nem_subset, key, prep_page, col_order, col_config):
    """Renders one nemesis table with single-row selection; ticking a row
    deep-links to Opponent Prep with that opponent's username pre-filled
    (the same _prep_username handoff insights_view's "Scout this opponent"
    button already uses -- prep_view pops it into its form). Selection is
    offered on every row, but only all-lichess opponents navigate: prep's
    fetch is lichess-only, and st.dataframe can't disable individual rows,
    so a chess.com opponent's row explains instead of silently scouting a
    wrong-platform username."""
    display_df = nem_subset.drop(columns=["all_lichess"]).reset_index(drop=True)
    selection = st.dataframe(display_df, width='stretch', on_select="rerun",
                             selection_mode="single-row", key=key,
                             hide_index=True, column_order=col_order,
                             column_config=col_config)
    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        picked = nem_subset.iloc[rows[0]]
        if picked.all_lichess:
            st.session_state["_prep_username"] = picked.opponent_name
            st.switch_page(prep_page)
        else:
            st.info(f"Opponent Prep scouts lichess players only, and your games "
                    f"against **{picked.opponent_name}** aren't on lichess.")


@st.fragment
def _render_nemesis_section(sqlite_conn, duck_conn, prep_page=None):
    """Its own fragment: the min-games slider, the commentary selectbox,
    and the Claude-commentary button all only affect this one section --
    nothing else on the page reads nem_df or these session_state keys --
    so none of that needs to re-run the rest of Matchups & Opponents."""
    st.subheader("Nemesis and favorite opponents")
    caption = ("Ranked by score% (win + 0.5*draw, standard tournament scoring) so repeated "
               "draws aren't misread as losses. Look for opponents you've played many times "
               "with a consistently lopsided record.")
    if prep_page:
        caption += (" Tick the checkbox at the left of a row to scout that player "
                    "in Opponent Prep.")
    st.caption(caption)
    nem_min_games = st.slider("Minimum games against this opponent", 3, 50, 5)
    nem_df = cached_nemesis_opponents(duck_conn, nem_min_games)

    # One combined W-D-L record column instead of three separate ones --
    # in the side-by-side layout below, three number columns pushed the
    # ranking metric (Score %) off the right edge at a normal window
    # width, which is the one column these tables exist to show.
    nem_display = nem_df.copy()
    nem_display["record"] = (nem_display.wins.fillna(0).astype(int).astype(str) + "-"
                             + nem_display.draws.fillna(0).astype(int).astype(str) + "-"
                             + nem_display.losses.fillna(0).astype(int).astype(str))
    nem_display = nem_display.drop(columns=["wins", "draws", "losses"])
    _nem_col_config = {
        "opponent_name": "Opponent",
        "n": st.column_config.NumberColumn("Games", width="small"),
        "record": st.column_config.TextColumn(
            "W-D-L", width="small", help="Wins-Draws-Losses against this opponent."),
        # width="small": the row-selection checkbox column (Opponent Prep
        # deep link) eats the slack the §6r W-D-L collapse freed up -- without
        # a fixed width, Score % clips off the right edge of the side-by-side
        # tables again at a normal window width.
        "score_pct": st.column_config.NumberColumn(
            "Score %", format="%.1f", width="small",
            help="Tournament scoring: a win = 100%, a draw = 50%. 0% means you have "
                 "never taken a point off this opponent."),
    }
    _nem_col_order = ["opponent_name", "n", "record", "score_pct"]

    def _nem_table(subset, key):
        if prep_page:
            _scout_on_row_click(subset, key, prep_page, _nem_col_order, _nem_col_config)
        else:
            st.dataframe(subset.drop(columns=["all_lichess"]), width='stretch',
                         hide_index=True, column_order=_nem_col_order,
                         column_config=_nem_col_config)

    col1, col2 = st.columns(2)
    with col1:
        st.write("Toughest opponents (lowest score%)")
        _nem_table(nem_display.sort_values("score_pct").head(10), "nem_toughest")
    with col2:
        st.write("Favorite opponents (highest score%)")
        _nem_table(nem_display.sort_values("score_pct", ascending=False).head(10),
                   "nem_favorite")

    st.write("Most-played opponents overall")
    _nem_table(nem_display.sort_values("n", ascending=False).head(10), "nem_most_played")

    if not nem_df.empty:
        opponent_names = nem_df.opponent_name.tolist()
        chosen_name = st.selectbox("Tell me about this rivalry", opponent_names,
                                    key="opponent_commentary_select")
        chosen_row = nem_df.loc[nem_df.opponent_name == chosen_name].iloc[0]

        cached = data.get_cached_narrative(sqlite_conn, "opponent", chosen_name)
        if cached:
            response_text, generated_at = cached
            st.caption(f"Generated {generated_at}")
            st.markdown(response_text)
        button_label = "Regenerate commentary" if cached else "Generate commentary"

        if not claude_narrative.api_key_available():
            st.info("Add your own Anthropic API key on the Settings page to enable this.")
        if st.button(button_label, key="opponent_commentary_button",
                     disabled=not claude_narrative.api_key_available()):
            stats = cached_headline_stats(duck_conn, sqlite_conn)
            with st.spinner("Asking Claude..."):
                try:
                    response_text = claude_narrative.generate_opponent_commentary(
                        chosen_row, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
                    data.save_narrative(sqlite_conn, "opponent", chosen_name,
                                         response_text, claude_narrative.MODEL)
                    # Scoped, not a full app rerun -- only this fragment's
                    # own cached-narrative display needs to reflect the
                    # write, nothing else on the page reads it.
                    st.rerun(scope="fragment")
                except claude_narrative.MissingApiKeyError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Claude API call failed: {e}")
