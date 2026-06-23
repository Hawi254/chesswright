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


@st.cache_data
def cached_win_rate_by_rating_diff(_duck_conn):
    return data.get_win_rate_by_rating_diff(_duck_conn)


@st.cache_data
def cached_giant_killing_counts(_duck_conn):
    return data.get_giant_killing_counts(_duck_conn)


@st.cache_data
def cached_comeback_collapse_counts(_duck_conn):
    return data.get_comeback_collapse_counts(_duck_conn)


@st.cache_data
def cached_color_performance_by_rating(_duck_conn):
    return data.get_color_performance_by_rating(_duck_conn)


@st.cache_data
def cached_nemesis_opponents(_duck_conn, min_games):
    return data.get_nemesis_opponents(_duck_conn, min_games=min_games)


@st.cache_data
def cached_headline_stats(_duck_conn, _sqlite_conn):
    return data.get_headline_stats(_duck_conn, _sqlite_conn)


def _clickable_game_ids(game_ids, key, detail_page, self_page):
    """One consistent drill-down pattern for a bare list of game_ids,
    reused by both the comeback and collapse tables below."""
    if not game_ids:
        st.write("None.")
        return
    df = pd.DataFrame({"game_id": game_ids})
    navigate_on_row_click(df, key, detail_page, self_page, "Matchups & Opponents")


def render(self_page, detail_page):
    sqlite_conn, duck_conn = get_connections()
    st.title("Matchups & Opponents")

    with st.container(border=True):
        st.subheader("Win rate vs. rating differential")
        rd_df = cached_win_rate_by_rating_diff(duck_conn)
        st.plotly_chart(charts.bar_chart(rd_df, "band", "win_pct", theme.POSITIVE), theme=None)

    with st.container(border=True):
        st.subheader("Win rate by color, rating-adjusted")
        st.caption("Confirms White's edge holds at every rating bucket, not just on average.")
        color_rating_df = cached_color_performance_by_rating(duck_conn)
        st.dataframe(color_rating_df, width='stretch')

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
        col1.metric("Giant-killing wins (300+ underdog)",
                    f"{gk['n_upsets']} / {gk['n_underdog_games']}",
                    f"{upset_pct:.1f}%" if upset_pct is not None else None)
        col2.metric("Collapse losses (300+ favorite)",
                    f"{gk['n_collapses']} / {gk['n_favorite_games']}",
                    f"{collapse_pct:.1f}%" if collapse_pct is not None else None)

    with st.container(border=True):
        st.subheader("Comebacks and collapses (eval-based)")
        st.caption("Click a row to open that game's full story.")
        cc = cached_comeback_collapse_counts(duck_conn)
        col1, col2 = st.columns(2)
        col1.metric("Comebacks", cc["n_comebacks"])
        col2.metric("Collapses", cc["n_collapses"])
        with st.expander(f"Comeback games ({cc['n_comebacks']})"):
            _clickable_game_ids(cc["comeback_game_ids"], "comeback_games", detail_page, self_page)
        with st.expander(f"Collapse games ({cc['n_collapses']})"):
            _clickable_game_ids(cc["collapse_game_ids"], "collapse_games", detail_page, self_page)

    with st.container(border=True):
        st.subheader("Nemesis and favorite opponents")
        st.caption("Ranked by score% (win + 0.5*draw, standard tournament scoring) so repeated "
                   "draws aren't misread as losses. Real finding: 17.1% score over 41 games "
                   "against a single opponent -- one of the largest single-opponent samples in "
                   "the whole dataset, not a small-sample fluke.")
        nem_min_games = st.slider("Minimum games against this opponent", 3, 50, 5)
        nem_df = cached_nemesis_opponents(duck_conn, nem_min_games)

        col1, col2 = st.columns(2)
        with col1:
            st.write("Toughest opponents (lowest score%)")
            st.dataframe(nem_df.sort_values("score_pct").head(10), width='stretch')
        with col2:
            st.write("Favorite opponents (highest score%)")
            st.dataframe(nem_df.sort_values("score_pct", ascending=False).head(10), width='stretch')

        st.write("Most-played opponents overall")
        st.dataframe(nem_df.sort_values("n", ascending=False).head(10), width='stretch')

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
            button_label = "Regenerate commentary (Claude API)" if cached else "Generate commentary (Claude API)"

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
                        st.rerun()
                    except claude_narrative.MissingApiKeyError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Claude API call failed: {e}")
