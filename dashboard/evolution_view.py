"""Repertoire Evolution -- the time dimension of the Openings page.

What entered and left the repertoire, when, and whether each change paid
off. Core (free-tier) page; the position-level companion is the Pro
Opening Tree's "What Changed" tab (BRIEF 6s). All sections run off ONE
cached games-table scan (data.get_family_period_counts); the only
moves-table read is the deep-dive's per-family ACPL trend, cached on
exactly the args its scan depends on.
"""
import pandas as pd
import streamlit as st

import charts
import data
import theme
from _common import get_connections

_TC_ORDER = ["bullet", "blitz", "rapid", "classical", "correspondence"]
_ALL_TC = "All time controls"

_STATUS_TEXT = {
    "adopted": "🆕 Adopted",
    "dropped": "✂️ Dropped",
    "rising": "📈 Rising",
    "fading": "📉 Fading",
    "stable": "Stable",
}


@st.cache_data(show_spinner="Reading your games' opening history…")
def _cached_period_counts(_duck_conn):
    return data.get_family_period_counts(_duck_conn)


@st.cache_data(show_spinner="Computing the accuracy trend for this opening…")
def _cached_family_acpl(_duck_conn, family, color, time_control):
    # Keyed on family/color/time_control -- unlike the page's other
    # controls these genuinely change what the scan reads (audit rule).
    return data.get_family_acpl_by_period(_duck_conn, family, color, time_control)


def _pct_arrow(early, late) -> str:
    """'41% → 49%' with an em dash for windows where the opening wasn't
    played -- pre-formatted strings only (this Streamlit renders any null
    flavor in data cells as literal 'None'; BRIEF 6n/6r)."""
    fmt = lambda v: "—" if pd.isna(v) else f"{v:.0f}%"
    return f"{fmt(early)} → {fmt(late)}"


def render():
    _, duck_conn = get_connections()
    st.title("Repertoire Evolution")
    st.caption(
        "How your opening repertoire changed across your career — what you "
        "adopted, what you dropped, and whether each change paid off."
    )

    counts = _cached_period_counts(duck_conn)
    if counts.empty:
        st.info("No games here yet — sync your games first, then come back.")
        return

    ctrl_color, ctrl_tc, ctrl_group = st.columns(3)
    with ctrl_color:
        color = st.radio(
            "Playing as", options=["white", "black"],
            format_func=lambda c: "⬜ White" if c == "white" else "⬛ Black",
            horizontal=True, key="ev_color",
        )
    with ctrl_tc:
        present = [tc for tc in _TC_ORDER
                   if tc in set(counts["time_control_category"].dropna())]
        tc_choice = st.selectbox("Time control", [_ALL_TC] + present, key="ev_tc")
        tc = None if tc_choice == _ALL_TC else tc_choice
    with ctrl_group:
        group_choice = st.selectbox(
            "Group openings by", ["Opening family", "ECO section (A–E)"],
            key="ev_grouping",
            help="Lichess opening names put move-order variations in "
                 "catch-all buckets (e.g. “Zukertort Opening” is mostly "
                 "1.Nf3 lines). ECO sections are coarser but steadier.",
        )
        grouping = "family" if group_choice == "Opening family" else "eco"

    filtered = data.filter_counts(counts, color, tc, grouping)
    if filtered.empty:
        st.info("No games match this color and time control.")
        return
    if filtered["period"].nunique() < 2:
        st.info("All these games fall in a single quarter — play across a "
                "longer stretch to see your repertoire evolve.")
        return

    _render_share_section(filtered, color, tc_choice)
    _render_ledger_section(filtered)
    _render_deep_dive(counts, duck_conn, color, tc, tc_choice)


# ── Section 1: share over time ────────────────────────────────────────────────

def _render_share_section(filtered, color, tc_choice) -> None:
    st.subheader("Where your games went")
    shares, top = data.period_shares(filtered)
    colors = {fam: theme.CATEGORICAL_SERIES[i] for i, fam in enumerate(top)}
    colors["Other"] = theme.CATEGORICAL_OTHER
    st.plotly_chart(
        charts.stacked_bar_chart(
            shares, "label", "family", "share", colors, height=340,
            x_title="Quarter", y_title="Share of games (%)", y_suffix="%"),
        use_container_width=True)
    side = "White" if color == "white" else "Black"
    st.caption(
        f"Each bar is one quarter of your {side} games "
        f"({tc_choice.lower()}), split by what you opened with — "
        f"{int(filtered['n_games'].sum()):,} games in total. Empty slots "
        "are quarters you didn't play."
    )


# ── Section 2: adoption/abandonment ledger ────────────────────────────────────

def _render_ledger_section(filtered) -> None:
    st.subheader("Adopted, dropped, rising, fading")
    ledger = data.classify_evolution(filtered)
    if ledger.empty:
        st.caption(
            "No opening here clears the ledger's floors yet "
            f"(at least {data.MIN_FAMILY_GAMES} games and "
            f"{data.MINOR_SHARE_PCT:.0f}% of a comparison window)."
        )
        return

    def status_text(row):
        base = _STATUS_TEXT[row["status"]]
        if row["status"] == "adopted":
            return f"{base} ({row['adopted_label']})"
        if row["status"] == "dropped":
            return f"{base} ({row['dropped_label']})"
        return base

    display = pd.DataFrame({
        "Opening": ledger["family"],
        "Status": [status_text(r) for _, r in ledger.iterrows()],
        "Share of games": [_pct_arrow(r["share_early"], r["share_late"])
                           for _, r in ledger.iterrows()],
        "Win rate": [_pct_arrow(r["win_early"], r["win_late"])
                     for _, r in ledger.iterrows()],
        "Games": [f"{n:,}" for n in ledger["n_games_total"]],
    })
    st.dataframe(
        display, hide_index=True, width="stretch",
        column_config={
            "Status": st.column_config.TextColumn(
                help="Adopted/Dropped dates are the first/last quarter the "
                     f"opening reached {data.MAJOR_SHARE_PCT:.0f}% of your games."),
            "Share of games": st.column_config.TextColumn(
                help="Its share of your games in your first year of history "
                     "→ your most recent year."),
            "Win rate": st.column_config.TextColumn(
                help="Your score with it in those same two windows. “—” "
                     "means you didn't play it in that window."),
        },
    )
    st.caption(
        "Windows compare your first ≈year of games against your latest. "
        "Win rates also move with your overall strength — a fading opening "
        "with a rising win rate usually says more about you than about it."
    )


# ── Section 3: one family up close ────────────────────────────────────────────

@st.fragment
def _render_deep_dive(counts, duck_conn, color, tc, tc_choice) -> None:
    """Always keyed to real opening families (not ECO sections), whatever
    the page-level grouping toggle says -- an accuracy trend for "D —
    Closed & semi-closed" would be mush."""
    st.subheader("One opening, up close")
    by_family = data.filter_counts(counts, color, tc, "family")
    fam_totals = (by_family.groupby("family")["n_games"].sum()
                           .sort_values(ascending=False))
    eligible = list(fam_totals[fam_totals >= data.MIN_FAMILY_GAMES].index)
    if not eligible:
        st.caption("No opening has enough games for a trend yet.")
        return

    family = st.selectbox(
        "Opening", eligible, key=f"ev_family_{color}_{tc_choice}",
        help="Openings with at least "
             f"{data.MIN_FAMILY_GAMES} games as this color, most played first.",
    )

    win_col, acpl_col = st.columns(2)
    with win_col:
        wt = data.family_win_trend(by_family, family)
        if len(wt) < 2:
            st.caption("Not enough games per quarter for a win-rate trend.")
        else:
            st.plotly_chart(
                charts.line_chart(wt, "label", "win_pct", theme.POSITIVE,
                                  height=300, x_title="Quarter",
                                  y_title="Win rate (%)"),
                use_container_width=True)
            st.caption("Quarters with fewer than 5 games are left out.")
    with acpl_col:
        acpl = _cached_family_acpl(duck_conn, family, color, tc)
        if len(acpl) < 2:
            st.caption(
                "Not enough analyzed moves for an accuracy trend — this "
                "shows only quarters with 30+ analyzed moves in this opening."
            )
        else:
            acpl = acpl.assign(
                hover_coverage=acpl.apply(
                    lambda r: f"{int(r.n_games)} of {int(r.n_total_games)} games ({r.coverage_pct:.1f}%)",
                    axis=1))
            st.plotly_chart(
                charts.line_chart(acpl, "label", "acpl", theme.ACCENT_GOLD,
                                  height=300, x_title="Quarter",
                                  y_title="Avg centipawn loss",
                                  hover_extra=("hover_coverage", "Analyzed")),
                use_container_width=True)
            st.caption(
                "Lower is more accurate. Only quarters with 30+ analyzed "
                "moves count; the gaps are where analysis is thin."
            )
            min_row = acpl.loc[acpl.coverage_pct.idxmin()]
            max_row = acpl.loc[acpl.coverage_pct.idxmax()]
            if max_row.coverage_pct >= 2 * max(min_row.coverage_pct, 0.1):
                st.caption(
                    f"⚠️ These quarters aren't equally analyzed -- from "
                    f"{min_row.coverage_pct:.1f}% in {min_row.label} to "
                    f"{max_row.coverage_pct:.1f}% in {max_row.label}. Analysis "
                    "prioritizes recently-synced games, so a shift here can "
                    "mean \"this quarter finally got analyzed\" rather than "
                    "a real accuracy change. Hover a point for its own coverage."
                )
