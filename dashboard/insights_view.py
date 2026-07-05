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

Action buttons (drill_export_page / prep_page): findings that have a
natural practice target get a one-click "Export drill positions" or
"Scout this opponent" button that navigates to the relevant page with
the appropriate preset pre-selected. Pages are optional so callers that
don't wire them (e.g. tests) continue to work unchanged.
"""
import streamlit as st

import claude_narrative
import data
import theme
from _common import get_connections
from cached_queries import cached_career_findings, cached_headline_stats

# Findings whose title maps to a Drill Export preset.
# Keys match finding["title"] exactly; values are passed as _drill_preset
# into session_state so drill_export_view can pre-select sources + motif filter.
_DRILL_PRESETS = {
    "Piece blunder hot-spot": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": None,
    },
    "Tactical highlights so far": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": None,
    },
    "King moves off the back rank": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": "back_rank_mate",
    },
}


def render(drill_export_page=None, prep_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.title("Insights")
    st.write("A live digest of what stands out in your analyzed games so far -- "
             "no curated write-up, just whatever the numbers currently show. "
             "It fills in and changes as more games are analyzed; hit \"Refresh data\" "
             "in the sidebar after a new batch finishes to see the latest.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total games", f"{stats['total_games']:,}",
                help="Every game synced from your online accounts.")
    col2.metric("Analyzed games", f"{stats['analyzed_games']:,}",
                help="Games your engine has analyzed — the findings below only "
                     "count these.")
    col3.metric("Win rate", f"{stats['win_pct']:.1f}%" if stats['win_pct'] is not None else "--",
                help="Wins as a share of all games. Online pairing aims for even "
                     "matches, so most players sit near 50%.")
    col4.metric("ACPL (analyzed)", f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "--",
                help="Average centipawn loss — measures move accuracy across "
                     "analyzed games. Lower is better.")

    findings = cached_career_findings(duck_conn, stats["blunder_rate"])

    if not findings:
        st.info(theme.thin_data_message(stats["analyzed_games"], 1))
        return

    for finding in findings:
        with st.container(border=True):
            st.subheader(finding["title"])
            st.write(f"**{finding['headline']}**")
            st.caption(finding["detail"])

            drill_preset = _DRILL_PRESETS.get(finding["title"])
            if drill_preset and drill_export_page:
                if st.button("→ Export practice positions",
                             key=f"drill_{finding['title']}",
                             help="Open Drill Export with this weakness pre-selected."):
                    st.session_state["_drill_preset"] = drill_preset
                    st.switch_page(drill_export_page)

            if (finding["title"] == "Toughest opponent"
                    and prep_page
                    and finding.get("opponent_name")):
                if st.button("→ Scout this opponent",
                             key="scout_nemesis",
                             help="Open Opponent Prep with this player's username pre-filled."):
                    st.session_state["_prep_username"] = finding["opponent_name"]
                    st.switch_page(prep_page)

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

    with st.container(border=True):
        st.subheader("What to practice")
        st.caption("Concrete, specific practice recommendations grounded in the findings above — "
                   "not just what's wrong, but what to actually do about it.")
        # subject_type='coaching' was added in migration 0017 specifically
        # for this kind of actionable-recommendation output, distinct from
        # the 'findings' synthesis stored under subject_key='summary'.
        cached_coaching = data.get_cached_narrative(sqlite_conn, "coaching", "recommendations")
        if cached_coaching:
            coaching_text, coaching_at = cached_coaching
            st.caption(f"Generated {coaching_at}")
            st.markdown(coaching_text)
        coaching_btn_label = "Regenerate recommendations" if cached_coaching else "Generate coaching recommendations"

        if not claude_narrative.api_key_available():
            st.info("Add your own Anthropic API key on the Settings page to enable this.")
        if st.button(coaching_btn_label, disabled=not claude_narrative.api_key_available(),
                     key="coaching_btn"):
            with st.spinner("Asking Claude..."):
                try:
                    coaching_text = claude_narrative.generate_coaching_recommendations(
                        findings, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
                    data.save_narrative(sqlite_conn, "coaching", "recommendations",
                                         coaching_text, claude_narrative.MODEL)
                    st.rerun()
                except claude_narrative.MissingApiKeyError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Claude API call failed: {e}")
