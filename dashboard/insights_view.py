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

Chip/action rendering (_common.finding_chips_html / .render_finding_actions)
moved to _common.py in the Training Queue MVP (2026-07-10) once that page
needed the exact same rendering for the same finding dicts -- see
_common.py's own comment for why that module, not a new one.
"""
import streamlit as st

import claude_narrative
import data
import theme
from _common import finding_chips_html, get_connections, render_finding_actions, SEVERITY_ORDER
from cached_queries import cached_career_findings, cached_headline_stats


def _render_hero_insight(finding, drill_export_page, prep_page) -> None:
    """Gold-accented callout for the single top-severity finding, mirroring
    overview_view.py's Focus Card pattern (_render_focus_card)."""
    theme.render_metric_card(
        eyebrow=f"🌟 Top insight — {finding['title']}",
        headline=finding["headline"],
        detail=finding["detail"],
    )
    chips_html = finding_chips_html(finding)
    if chips_html:
        st.markdown(chips_html, unsafe_allow_html=True)
    render_finding_actions(finding, drill_export_page, prep_page)


def _render_strengths_weaknesses(findings) -> None:
    """Splits findings into a 2-column strengths/weaknesses panel by their
    polarity field. Findings tagged "mixed" (already show both a good and
    bad data point in one card, e.g. thinking-time's best/worst bucket) or
    "neutral" (purely informational, e.g. the tactical highlights round-up)
    don't fit a 2-column strength/weakness split and are deliberately left
    out of this panel -- they're still visible in the list above."""
    strengths = [f for f in findings if f.get("polarity") == "strength"]
    weaknesses = [f for f in findings if f.get("polarity") == "weakness"]
    if not strengths and not weaknesses:
        return

    def _render_strength_list():
        st.subheader("💪 Strengths")
        if not strengths:
            st.caption("Nothing tagged as a clear strength yet with the data analyzed so far.")
            return
        for f in strengths:
            st.write(f"**{f['title']}** — {f['headline']}")

    def _render_weakness_list():
        st.subheader("🎯 Areas to work on")
        if not weaknesses:
            st.caption("Nothing tagged as a clear weakness yet with the data analyzed so far.")
            return
        for f in weaknesses:
            st.write(f"**{f['title']}** — {f['headline']}")

    st.subheader("Strengths & Weaknesses")
    theme.render_comparison_panel(
        [{"render": _render_strength_list}, {"render": _render_weakness_list}],
        mode="side_by_side",
        shared_caption="Findings split by direction where the comparison has one -- mixed "
                        "or purely informational findings aren't shown here, see the full "
                        "list above for those.",
    )


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

    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 1))

    hero, rest = findings[0], findings[1:]
    _render_hero_insight(hero, drill_export_page, prep_page)

    if rest:
        st.caption("Other findings")

    for finding in rest:
        with st.container(border=True):
            st.subheader(finding["title"])
            st.write(f"**{finding['headline']}**")
            st.caption(finding["detail"])

            chips_html = finding_chips_html(finding)
            if chips_html:
                st.markdown(chips_html, unsafe_allow_html=True)

            render_finding_actions(finding, drill_export_page, prep_page)

    _render_strengths_weaknesses(findings)

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
