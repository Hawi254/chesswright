"""Training Queue -- a severity-ranked list of weakness-polarity findings
from data/insights.py's get_career_findings(), each with a one-click
practice action where one exists. The MVP slice of roadmap Phase 5
"Training Center" (docs/implementation_roadmap.md S17 Q4 / S19): a real,
small, first Training Center page built from data/rendering that already
exists (severity, polarity, the drill-preset/scout-opponent action
buttons) rather than new trainer infrastructure.

Deliberately narrow, not a placeholder for the rest of Phase 5: this page
only surfaces "weakness" polarity findings (the same filter
insights_view.py's Strengths & Weaknesses panel already applies) sorted
by severity, reusing _common.finding_chips_html/.render_finding_actions
so a weakness card here renders identically to the same finding's card on
Insights. "mixed"/"neutral"/"strength" findings are not queue material --
they either bundle both directions in one card already (thinking time,
clock pressure, giant-killing) or have no practice target at all
(tactical highlights round-up, game endings distribution).

Motif-backfill caveat (docs/implementation_roadmap.md S17 Q4): on the
real dev DB as of 2026-07-10, moves.motif is 0/2.29M rows, so any
weakness whose action is a motif-filtered Drill Export preset currently
returns zero positions. Handled here as a one-line proactive banner (not
a silent dead button, and not deferred to Drill Export's own empty-state
message) -- see _motif_gated_titles below.
"""
import streamlit as st

import theme
from _common import DRILL_PRESETS, finding_chips_html, get_connections, render_finding_actions, SEVERITY_ORDER
from cached_queries import cached_career_findings, cached_headline_stats, cached_motif_backfill_needed

# Finding titles whose DRILL_PRESETS entry is motif-filtered -- these are
# the ones a motif backfill actually affects. "Toughest opponent"'s scout
# button and any future non-motif preset are unaffected.
_MOTIF_GATED_TITLES = {title for title, preset in DRILL_PRESETS.items() if preset.get("include_motifs")}


def render(drill_export_page=None, prep_page=None, analysis_jobs_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.title("Training Queue")
    st.write("Your current weaknesses, ranked by severity, with a one-click practice "
             "action where one exists. Same live findings as Insights -- just filtered "
             "to what's worth practicing and sorted by how much it's costing you.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    findings = cached_career_findings(duck_conn, stats["blunder_rate"])

    if not findings:
        st.info(theme.thin_data_message(stats["analyzed_games"], 1))
        return

    weaknesses = [f for f in findings if f.get("polarity") == "weakness"]
    if not weaknesses:
        st.info("Nothing tagged as a clear weakness yet with the data analyzed so far -- "
                 "check back as more games are analyzed, or see the full findings list on "
                 "the Insights page.")
        return

    weaknesses = sorted(weaknesses, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 1))

    gated_queued = [f["title"] for f in weaknesses if f["title"] in _MOTIF_GATED_TITLES]
    if gated_queued and cached_motif_backfill_needed(duck_conn):
        noun = "weakness" if len(gated_queued) == 1 else "weaknesses"
        with st.container(border=True):
            st.warning(
                f"{len(gated_queued)} queued {noun} below "
                f"({', '.join(gated_queued)}) export practice positions from tactical motif "
                "data (fork/pin/skewer/etc.), which hasn't been computed for your analyzed "
                "games yet -- their export button will return 0 positions until then."
            )
            if analysis_jobs_page and st.button("→ Run annotation pass now",
                                                 key="training_queue_run_annotation",
                                                 help="Open Analysis Jobs to backfill motif "
                                                      "data for your already-analyzed games."):
                st.switch_page(analysis_jobs_page)

    for finding in weaknesses:
        with st.container(border=True):
            st.subheader(finding["title"])
            st.write(f"**{finding['headline']}**")
            st.caption(finding["detail"])

            chips_html = finding_chips_html(finding)
            if chips_html:
                st.markdown(chips_html, unsafe_allow_html=True)

            render_finding_actions(finding, drill_export_page, prep_page)
