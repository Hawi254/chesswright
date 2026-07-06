"""Batch Impact -- what a specific analysis run actually changed.

Extraction and expansion of analysis_jobs_view.py's ephemeral "last batch"
digest (BRIEF §6u): that version lived only in st.session_state, so it
vanished on the next batch or app restart, and covered exactly four
numbers (ACPL, blunder rate, new blunders/brilliancies, top motif).
worker.py's per-run analysis_runs row already gives every batch a
permanent id, and moves.analysis_run_id already links every move back to
the run that analyzed it -- the history was sitting in the schema, unused.
A run picker makes any past batch reviewable, not just the one that just
finished, and the before/after treatment now extends to phase accuracy,
endgame-type accuracy, and tactical motif frequency -- every metric whose
engine-derived values genuinely shift when new plies get Stockfish
analysis. Metrics that are actually driven by game results or opening
choices (not engine output) drift on a calendar-time axis instead, which
is what Repertoire Evolution tracks, not this page -- see
dashboard/data/analysis_batches.py's module docstring for what was
deliberately left out and why.
"""
import pandas as pd
import streamlit as st

import data
from _common import get_connections, navigate_on_row_click


@st.cache_data(show_spinner=False)
def _cached_runs(_sqlite_conn):
    return data.list_analysis_runs(_sqlite_conn)


# run_id is a bounded, discrete value drawn from the run picker below (one
# of a finite list of real analysis_runs rows), not a free-ranging slider
# -- fine to key a cache on directly, per the audit-dashboard-queries
# skill's "bounded-cardinality args are fine" rule. Cleared the same way
# every other cache in this app is (the sidebar "Refresh data" button).
@st.cache_data(show_spinner="Computing what this batch changed…")
def _cached_headline(_sqlite_conn, run_id):
    return data.get_batch_headline_delta(_sqlite_conn, run_id)


@st.cache_data(show_spinner=False)
def _cached_phase_delta(_sqlite_conn, run_id):
    return data.get_phase_accuracy_batch_delta(_sqlite_conn, run_id)


@st.cache_data(show_spinner=False)
def _cached_endgame_delta(_sqlite_conn, run_id):
    return data.get_endgame_type_batch_delta(_sqlite_conn, run_id)


@st.cache_data(show_spinner=False)
def _cached_motif_delta(_sqlite_conn, run_id):
    return data.get_motif_batch_delta(_sqlite_conn, run_id)


@st.cache_data(show_spinner=False)
def _cached_new_blunders(_sqlite_conn, run_id):
    return data.get_new_blunders_this_run(_sqlite_conn, run_id)


def _arrow(before, after, fmt="{:.1f}") -> str:
    """'45.2 → 42.1' with an em dash for a missing side -- pre-formatted
    strings only (any None/NaN in a rendered data cell shows as the
    literal text "None"; BRIEF §6n/§6r)."""
    b = "—" if before is None or pd.isna(before) else fmt.format(before)
    a = "—" if after is None or pd.isna(after) else fmt.format(after)
    return f"{b} → {a}"


def _run_label(row) -> str:
    n = row.games_analyzed or 0
    when = row.ended_at or row.started_at or "unknown time"
    return f"Run #{row.id} — {when} — {n} game{'s' if n != 1 else ''}"


def render(self_page=None, detail_page=None):
    sqlite_conn, _duck_conn = get_connections()
    st.title("Batch Impact")
    st.write(
        "What a specific Stockfish analysis batch actually changed — accuracy, "
        "blunders, and tactical patterns, before that batch vs. after it."
    )
    st.caption(
        "This tracks drift by analysis batch, not by calendar time — see "
        "Repertoire Evolution for how your opening choices changed over the years."
    )

    runs = _cached_runs(sqlite_conn)
    if runs.empty:
        st.info("No analysis runs yet — start one from Analysis Jobs, then come back here.")
        return

    labels = {row.id: _run_label(row) for row in runs.itertuples()}
    run_id = st.selectbox(
        "Analysis batch", runs["id"].tolist(), format_func=lambda i: labels[i],
        help="Runs are listed most-recent first. Each one is a single Analysis "
             "Jobs session — see that page to start a new one.",
    )

    headline = _cached_headline(sqlite_conn, run_id)
    if headline is None or headline["games_analyzed"] == 0:
        st.info("This run analyzed no games with recorded moves — nothing to compare.")
        return
    if headline["annotated_this_run"] == 0:
        # Real gap found live-verifying against the real DB (BRIEF §6u): a
        # run analyzes moves (setting eval_cp/analysis_run_id) but cpl/
        # classification aren't computed until the SEPARATE annotate.run()
        # pass. Without this check every section below would silently show
        # "0 moves this run" and a flat before==after delta -- indistinguishable
        # from "this batch genuinely changed nothing" unless said outright.
        st.subheader(f"Run #{headline['run_id']} — {headline['games_analyzed']} "
                     f"game{'s' if headline['games_analyzed'] != 1 else ''} analyzed")
        st.info("This batch hasn't been through the annotation pass yet, so there's "
                "nothing to compare — run \"Run annotation pass now\" on Analysis Jobs, "
                "then come back here.")
        return

    _render_headline(headline)
    st.divider()
    _render_phase_section(sqlite_conn, run_id)
    _render_motif_section(sqlite_conn, run_id)
    _render_endgame_section(sqlite_conn, run_id)
    _render_new_blunders_section(sqlite_conn, run_id, self_page, detail_page)


def _render_headline(headline: dict) -> None:
    n = headline["games_analyzed"]
    st.subheader(f"Run #{headline['run_id']} — {n} game{'s' if n != 1 else ''} analyzed")

    has_history = headline["before_acpl"] is not None
    col1, col2, col3 = st.columns(3)
    if has_history:
        acpl_delta = (headline["after_acpl"] or 0) - headline["before_acpl"]
        col1.metric(
            "ACPL", f"{headline['after_acpl']:.1f}" if headline["after_acpl"] else "—",
            delta=f"{acpl_delta:+.1f}" if headline["after_acpl"] else None,
            delta_color="inverse",
            help="Average centipawn loss across every analyzed game, through this run.",
        )
        br_delta = (headline["after_blunder_rate"] or 0) - headline["before_blunder_rate"]
        col2.metric(
            "Blunder rate",
            f"{headline['after_blunder_rate']:.1f}%" if headline["after_blunder_rate"] else "—",
            delta=f"{br_delta:+.1f}%" if headline["after_blunder_rate"] else None,
            delta_color="inverse",
        )
    else:
        col1.metric("ACPL (first batch)",
                    f"{headline['after_acpl']:.1f}" if headline["after_acpl"] else "—",
                    help="Average centipawn loss — lower is more accurate play.")
        col2.metric("Blunder rate",
                    f"{headline['after_blunder_rate']:.1f}%" if headline["after_blunder_rate"] else "—")
    col3.metric(
        "Blunders / Brilliancies this run",
        f"{headline['new_blunders']} / {headline['new_brilliant']}",
        help="New blunders and brilliant-move candidates found in this specific run.",
    )
    if headline["top_motif"]:
        n_m = headline["top_motif_count"]
        st.caption(
            f"Most common missed tactic this run: **{headline['top_motif']}** "
            f"({n_m} instance{'s' if n_m != 1 else ''})."
        )


def _render_phase_section(sqlite_conn, run_id) -> None:
    st.subheader("Accuracy by game phase")
    df = _cached_phase_delta(sqlite_conn, run_id)
    if df.empty:
        st.caption("No analyzed moves with phase data yet.")
        return
    display = pd.DataFrame({
        "Phase": df["phase"].str.capitalize(),
        "ACPL (before → after)": [_arrow(r.before_acpl, r.after_acpl) for r in df.itertuples()],
        "Blunder rate (before → after)": [
            _arrow(r.before_blunder_rate, r.after_blunder_rate, "{:.1f}%") for r in df.itertuples()],
        "Moves this run": df["n_moves_this_run"],
    })
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption("Lower ACPL and blunder rate are better. \"Before\" is every prior "
               "batch; \"after\" includes this one.")


def _render_motif_section(sqlite_conn, run_id) -> None:
    st.subheader("Tactical motifs missed")
    df = _cached_motif_delta(sqlite_conn, run_id)
    if df.empty:
        st.caption("No classified tactical motifs yet — see Analysis Jobs to run "
                   "the motif backfill if your games predate that feature.")
        return
    top = df.head(10)
    display = pd.DataFrame({
        "Motif": top["motif"].str.replace("_", " ").str.capitalize(),
        "Missed before": top["n_before"],
        "Missed after": top["n_after"],
        "New this run": top["n_this_run"],
    })
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption("Missed tactics (mistakes/blunders) classified by motif, across your "
               "whole history — before this batch vs. after it.")


def _render_endgame_section(sqlite_conn, run_id) -> None:
    st.subheader("Endgame accuracy")
    df = _cached_endgame_delta(sqlite_conn, run_id)
    if df.empty:
        st.caption("Not enough analyzed endgame moves yet.")
        return
    display = pd.DataFrame({
        "Endgame type": df["endgame_type"],
        "ACPL (before → after)": [_arrow(r.before_acpl, r.after_acpl) for r in df.itertuples()],
        "Blunder rate (before → after)": [
            _arrow(r.before_blunder_rate, r.after_blunder_rate, "{:.1f}%") for r in df.itertuples()],
        "Moves this run": df["n_moves_this_run"],
    })
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption("Win/draw/loss rates by endgame type aren't shown here — those depend "
               "on game results, not on this batch's engine analysis, so they don't "
               "move when a batch completes. See Game Endings for those.")


def _render_new_blunders_section(sqlite_conn, run_id, self_page, detail_page) -> None:
    df = _cached_new_blunders(sqlite_conn, run_id)
    if df.empty:
        return
    st.subheader(f"New blunders this run ({len(df)})")
    # or-"" not None: any None/NaN in a rendered data cell shows as the
    # literal text "None" (BRIEF §6n/§6r) -- most of these moves predate
    # motif classification (motif_backfill_needed), so this is the common
    # case, not an edge case.
    df = df.assign(motif=df["motif"].fillna(""))
    navigate_on_row_click(
        df, key=f"batch_impact_blunders_{run_id}",
        detail_page=detail_page, self_page=self_page, return_label="Batch Impact",
        column_config={
            "san": "Move",
            "cpl": st.column_config.NumberColumn(
                "Cost (cp)", help="Centipawns lost vs. the engine's best move."),
            "motif": "Motif",
        },
    )
