"""Insights -- a live "what stands out" digest, computed from however
much of the career is currently analyzed. Replaces, in spirit, the old
findings_view.py dropped in Phase A (BRIEF.md S6a): that page depended on
a hand-curated FINDINGS.md and an analysis/ subprocess specific to the
original project's own dataset; this one has no curated file at all,
every finding is recomputed live from data/insights.py.

Refresh is deliberately manual, the same as every other page: the
sidebar "Refresh data" button in app.py already clears st.cache_data and
rebuilds the structure/session caches, which is all this page needs to
pick up newly analyzed games. No separate polling here.
"""
import streamlit as st

import claude_narrative
import data
import theme
from _common import get_connections


@st.cache_data
def cached_headline_stats(_duck_conn, _sqlite_conn):
    return data.get_headline_stats(_duck_conn, _sqlite_conn)


@st.cache_data
def cached_career_findings(_duck_conn, baseline_blunder_rate):
    return data.get_career_findings(_duck_conn, baseline_blunder_rate)


def render():
    sqlite_conn, duck_conn = get_connections()
    st.title("Insights")
    st.write("A live digest of what stands out in your analyzed games so far -- "
             "no curated write-up, just whatever the numbers currently show. "
             "It fills in and changes as more games are analyzed; hit \"Refresh data\" "
             "in the sidebar after a new batch finishes to see the latest.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total games", f"{stats['total_games']:,}")
    col2.metric("Analyzed games", f"{stats['analyzed_games']:,}")
    col3.metric("Win rate", f"{stats['win_pct']:.1f}%" if stats['win_pct'] is not None else "--")
    col4.metric("ACPL (analyzed)", f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "--")

    findings = cached_career_findings(duck_conn, stats["blunder_rate"])

    if not findings:
        st.info(theme.thin_data_message(stats["analyzed_games"], 1))
        return

    for finding in findings:
        with st.container(border=True):
            st.subheader(finding["title"])
            st.write(f"**{finding['headline']}**")
            st.caption(finding["detail"])

    with st.container(border=True):
        st.subheader("Synthesis")
        st.caption("Asks Claude to read the findings above and call out what they add up "
                   "to, rather than just listing them again.")
        cached = data.get_cached_narrative(sqlite_conn, "findings", "summary")
        if cached:
            response_text, generated_at = cached
            st.caption(f"Generated {generated_at}")
            st.markdown(response_text)
        button_label = "Regenerate synthesis" if cached else "Generate synthesis"

        if not claude_narrative.api_key_available():
            st.info("Add your own Anthropic API key on the Settings page to enable this.")
        if st.button(button_label, disabled=not claude_narrative.api_key_available()):
            with st.spinner("Asking Claude..."):
                try:
                    response_text = claude_narrative.generate_insights_synthesis(
                        findings, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
                    data.save_narrative(sqlite_conn, "findings", "summary",
                                         response_text, claude_narrative.MODEL)
                    st.rerun()
                except claude_narrative.MissingApiKeyError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Claude API call failed: {e}")
