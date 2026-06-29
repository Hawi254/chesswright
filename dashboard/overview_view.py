"""
Phase 6c.4: Overview, redesigned per the approved 6c.1 information
architecture -- the landing page now opens with an auto-generated
career-level narrative (mirroring the per-game story, applied to the
whole career) and a "most dramatic game" teaser that links straight into
Game Detail, instead of a bare stats dump.
"""
import streamlit as st

import charts
import data
import narrative
import theme
from _common import get_connections
from game_explorer_view import cached_game_explorer_table


@st.cache_data
def cached_headline_stats(_duck_conn, _sqlite_conn):
    return data.get_headline_stats(_duck_conn, _sqlite_conn)


@st.cache_data
def cached_rating_trajectory(_duck_conn):
    return data.get_rating_trajectory(_duck_conn)


@st.cache_data
def cached_acpl_trajectory(_duck_conn):
    return data.get_acpl_trajectory(_duck_conn)


@st.cache_data
def cached_win_rate_by_color(_duck_conn):
    return data.get_win_rate_by_color(_duck_conn)


@st.cache_data
def cached_progress_by_month(_duck_conn):
    return data.get_progress_by_month(_duck_conn)


def render(self_page, detail_page):
    sqlite_conn, duck_conn = get_connections()
    st.title("Overview")

    if st.session_state.pop("just_completed_onboarding", False):
        st.info("Your starter batch is analyzed and ready. Use the sidebar to explore — "
                "each section looks at your games from a different angle.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    rating_df = cached_rating_trajectory(duck_conn)
    explorer_df = cached_game_explorer_table(duck_conn)
    top_game = explorer_df.iloc[0] if len(explorer_df) else None

    st.markdown(f'<div class="narrative-quote">'
                f'{narrative.generate_career_narrative(stats, rating_df, top_game)}</div>',
                unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total games", f"{stats['total_games']:,}")
    col2.metric("Analyzed games", f"{stats['analyzed_games']:,}")
    col3.metric("Win rate", f"{stats['win_pct']:.1f}%" if stats['win_pct'] is not None else "--")
    col4.metric("ACPL", f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "--",
                help="Average centipawn loss — measures move accuracy across analyzed games. Lower is better.")

    if top_game is not None:
        with st.container(border=True):
            chips_html = theme.chip_row_html(top_game)
            st.subheader("Most dramatic game on record")
            if chips_html:
                st.markdown(chips_html, unsafe_allow_html=True)
            st.write(f"vs. {top_game.opponent_name} on {top_game.utc_date} "
                     f"({top_game.outcome_for_player})")
            if st.button("View this game →"):
                st.session_state["selected_game_id"] = top_game.game_id
                st.session_state["return_page"] = self_page
                st.session_state["return_page_label"] = "Overview"
                st.switch_page(detail_page)

    with st.container(border=True):
        st.subheader("Rating trajectory")
        st.plotly_chart(charts.line_chart(rating_df, "year", "avg_rating", theme.ACCENT_GOLD),
                         theme=None)

        acpl_df = cached_acpl_trajectory(duck_conn)
        st.caption(f"ACPL (average centipawn loss -- lower is more accurate play) trend, "
                    f"analyzed games only: based on {acpl_df.n_games.sum()} analyzed games "
                    f"across {len(acpl_df)} years, treat as preliminary given the small sample.")
        st.plotly_chart(charts.line_chart(acpl_df, "year", "acpl", theme.NEGATIVE), theme=None)

    with st.container(border=True):
        st.subheader("Win rate by color")
        color_df = cached_win_rate_by_color(duck_conn)
        st.plotly_chart(charts.bar_chart(color_df, "player_color", "win_pct", theme.POSITIVE),
                         theme=None)

    progress_df = cached_progress_by_month(duck_conn)
    if len(progress_df) >= 2:
        with st.container(border=True):
            st.subheader("Progress over time")
            st.caption("Monthly averages across analyzed games — months with fewer than 3 analyzed "
                       "games are excluded to avoid single-game noise.")
            acpl_col, win_col = st.columns(2)
            with acpl_col:
                st.caption("ACPL by month (lower = more accurate)")
                st.plotly_chart(
                    charts.line_chart(progress_df, "period", "acpl", theme.NEGATIVE, height=240),
                    theme=None, use_container_width=True)
            with win_col:
                st.caption("Win rate % by month")
                st.plotly_chart(
                    charts.line_chart(progress_df, "period", "win_pct", theme.POSITIVE, height=240),
                    theme=None, use_container_width=True)
