"""
Phase 6c.4: Openings & Repertoire -- the old Openings tab plus
"most-repeated positions" from the old Position Explorer tab. Both
answer the same question: what do you actually play, and how does it
work for you? (Material-structure win-rate, Position Explorer's OTHER
panel, moved to Patterns & Tendencies instead -- see that module's
docstring for why.)
"""
import pandas as pd
import streamlit as st

import claude_narrative
import data
from _common import get_connections


@st.cache_data
def cached_openings_table(_duck_conn, _sqlite_conn, min_games):
    return data.get_openings_table(_duck_conn, _sqlite_conn, min_games=min_games)


@st.cache_data
def cached_most_repeated_positions(_duck_conn, top_n):
    return data.get_most_repeated_positions(_duck_conn, top_n=top_n)


@st.cache_data
def cached_headline_stats(_duck_conn, _sqlite_conn):
    return data.get_headline_stats(_duck_conn, _sqlite_conn)


def render():
    sqlite_conn, duck_conn = get_connections()
    st.title("Openings & Repertoire")

    with st.container(border=True):
        st.subheader("Openings (sortable, min-games filter)")
        min_games = st.slider("Minimum games", 1, 50, 5)
        openings_df = cached_openings_table(duck_conn, sqlite_conn, min_games)
        # win_pct/draw_pct/loss_pct/n are always populated (ingest-time,
        # no engine needed); acpl needs analyzed games specifically in
        # that opening, and with only 185 of 32,295 games analyzed so
        # far, most openings show NaN here -- caught by checking real
        # output (55 of 78 rows), not assumed fine. A bare NaN reads as
        # broken, not "not analyzed yet" -- same fix as the Patterns &
        # Tendencies material-structure table.
        n_unanalyzed = int((openings_df.n_analyzed == 0).sum())
        if n_unanalyzed:
            st.caption(f"ACPL is blank for {n_unanalyzed} of {len(openings_df)} openings above "
                       f"-- no analyzed games have reached them yet, not a data error.")
        display_df = openings_df.copy()
        display_df["acpl"] = display_df["acpl"].apply(lambda v: "--" if pd.isna(v) else f"{v:.1f}")
        st.dataframe(display_df, width='stretch')

        if not openings_df.empty:
            opening_labels = [f"{r.opening_family} ({r.player_color})"
                               for r in openings_df.itertuples()]
            chosen_label = st.selectbox("Tell me about this opening", opening_labels,
                                         key="opening_commentary_select")
            chosen_row = openings_df.iloc[opening_labels.index(chosen_label)]
            subject_key = f"{chosen_row.opening_family}|{chosen_row.player_color}"

            cached = data.get_cached_narrative(sqlite_conn, "opening", subject_key)
            if cached:
                response_text, generated_at = cached
                st.caption(f"Generated {generated_at}")
                st.markdown(response_text)
            button_label = "Regenerate commentary (Claude API)" if cached else "Generate commentary (Claude API)"

            if not claude_narrative.api_key_available():
                st.info("Add your own Anthropic API key on the Settings page to enable this.")
            if st.button(button_label, key="opening_commentary_button",
                         disabled=not claude_narrative.api_key_available()):
                stats = cached_headline_stats(duck_conn, sqlite_conn)
                with st.spinner("Asking Claude..."):
                    try:
                        response_text = claude_narrative.generate_opening_commentary(
                            chosen_row, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
                        data.save_narrative(sqlite_conn, "opening", subject_key,
                                             response_text, claude_narrative.MODEL)
                        st.rerun()
                    except claude_narrative.MissingApiKeyError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Claude API call failed: {e}")

    with st.container(border=True):
        st.subheader("Most-repeated positions")
        st.caption("Positions you've reached more than once (matched by exact board state, "
                   "not just opening name) -- shows whether your most-repeated lines are "
                   "actually working out, win/loss-wise.")
        top_n_positions = st.slider("Show top N", 5, 50, 20, key="positions_top_n")
        positions_df = cached_most_repeated_positions(duck_conn, top_n_positions)
        st.dataframe(positions_df, width='stretch')
