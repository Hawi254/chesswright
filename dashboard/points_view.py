"""Where Your Points Go -- expected-points decomposition (BRIEF §6o).

The stored win-probability curve (win_prob_before on every analyzed
move) is turned into a per-game points ledger by data/points.py: every
half point the player dropped relative to what their positions promised
is attributed to exactly one of three leak buckets -- failed
conversions, missed swindles, failed holds. This page is the ledger's
front end: where the points went, when, and in which games.

Neither lichess's insights nor chess.com's review exposes a
conversion-vs-defense-vs-swindle profile -- both stop at per-move
accuracy. This is computed purely from columns that have existed since
Phase 2; the only thing new is reading them game-shaped instead of
move-shaped.
"""
import streamlit as st

import charts
import chess_display
import data
import theme
from _common import get_connections, persist_filter, restore_filter_default
from cached_queries import (
    cached_failed_conversion_causes, cached_headline_stats, cached_points_ledger,
)

# One-line definition per bucket, shown under the bucket totals and
# restated in the methodology expander -- the numbers are only honest if
# the reader can see exactly what counted.
_BUCKET_CAPTION = {
    "failed_conversion":
        f"Reached a winning position ({data.WINNING_WP:.0%}+ win probability) "
        f"but didn't win.",
    "missed_swindle":
        f"Was lost ({data.LOST_WP:.0%} or worse), got handed a real chance "
        f"(back to {data.SWINDLE_CHANCE_WP:.0%}+), lost anyway.",
    "failed_hold":
        f"Still even ({data.EVEN_WP:.0%}+) at move {data.HOLD_EVEN_MIN_MOVE} "
        f"or later, never winning, but lost.",
}


_CONVERSION_REASON_LABELS = {
    "hung_piece":     "Hung a piece",
    "blown_mate":     "Blew a forced mate",
    "time_pressure":  "Time pressure",
    "other":          "Other / gradual give-back",
}


def _headline(summary, classified):
    """One concrete sentence naming the biggest leak -- the whole point
    of the page, so it leads. Returns None when there are no leaks."""
    if summary.empty:
        return None
    top = summary.iloc[0]
    total = summary.leaked.sum()
    if top.bucket == "failed_conversion":
        detail = ""
        phases = data.conversion_breakdown(classified, "conv_phase")
        bands = data.conversion_breakdown(classified, "adv_band")
        if len(phases) and len(bands):
            top_phase = phases.loc[phases.leaked.idxmax()]
            top_band = bands.loc[bands.leaked.idxmax()]
            detail = (f" The costliest slice: positions that first became winning "
                      f"in the **{top_phase.conv_phase}** ({top_phase.leaked:.0f} pts), "
                      f"most often at **{top_band.adv_band}**.")
        return (f"Your biggest leak is **failed conversions**: {int(top.n_games)} games "
                f"where you reached a winning position and gave back "
                f"**{top.leaked:.0f} of your {total:.0f} leaked points**.{detail}")
    if top.bucket == "missed_swindle":
        return (f"Your biggest leak is **missed swindles**: in {int(top.n_games)} lost "
                f"games your opponent handed the game back to even or better and it "
                f"slipped away again -- **{top.leaked:.0f} of your {total:.0f} leaked "
                f"points**.")
    return (f"Your biggest leak is **failed holds**: {int(top.n_games)} games that were "
            f"still level in the middlegame but drifted into losses -- "
            f"**{top.leaked:.0f} of your {total:.0f} leaked points**.")


def render(self_page=None, detail_page=None):
    _sqlite_conn, duck_conn = get_connections()
    st.title("Where Your Points Go")
    st.write("Every analyzed game stores a move-by-move win-probability curve. "
             "Read game-shaped, it becomes a ledger: what your positions promised "
             "at their best, what you actually scored, and which kind of collapse "
             "ate the difference.")

    classified = cached_points_ledger(duck_conn)
    if classified.empty:
        stats = cached_headline_stats(duck_conn, _sqlite_conn)
        st.info(theme.thin_data_message(stats["analyzed_games"], 1))
        return

    tc_options = ["All time controls"] + sorted(
        classified.time_control_category.dropna().unique())
    restore_filter_default("points_tc", tc_options[0])
    tc = st.selectbox("Time control", tc_options, key="points_tc")
    persist_filter("points_tc")
    view = classified if tc == "All time controls" else \
        classified[classified.time_control_category == tc]
    if view.empty:
        st.info("No analyzed games in this time control yet.")
        return

    summary = data.summarize_buckets(view)
    actual = view.points.sum()
    leaked = view.leaked.sum()
    n = len(view)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Games in ledger", f"{n:,}",
                help="Fully analyzed games with win-probability data.")
    col2.metric("Actual score", f"{100 * actual / n:.1f}%",
                help="Points actually scored (win = 1, draw = ½) as a share of "
                     "the games in the ledger.")
    col3.metric("Points leaked", f"{leaked:.1f}",
                help="Half-points and wins given back across all three leak types "
                     "below — the gap between your actual score and your ceiling.")
    col4.metric("Ceiling score", f"{100 * (actual + leaked) / n:.1f}%",
                help="Score if every leak had been recovered. Nobody converts "
                     "everything -- treat this as the direction, not a target.")

    headline = _headline(summary, view)
    if headline:
        with st.container(border=True):
            st.write(headline)

    if summary.empty:
        st.success("No leaked points found in this slice -- every winning position "
                   "was converted and no even game drifted away.")
        return

    with st.container(border=True):
        st.subheader("The three leaks")
        cols = st.columns(3)
        by_bucket = summary.set_index("bucket")
        for col, bucket in zip(cols, ["failed_conversion", "missed_swindle", "failed_hold"]):
            with col:
                if bucket in by_bucket.index:
                    row = by_bucket.loc[bucket]
                    st.metric(data.BUCKET_LABEL[bucket], f"{row.leaked:.1f} pts")
                    st.caption(f"{int(row.n_games)} games. {_BUCKET_CAPTION[bucket]}")
                else:
                    st.metric(data.BUCKET_LABEL[bucket], "0 pts")
                    st.caption(f"0 games. {_BUCKET_CAPTION[bucket]}")

    monthly = data.monthly_points(view)
    if len(monthly) >= 2:
        with st.container(border=True):
            st.subheader("Actual vs. ceiling, by month")
            st.caption("Monthly score against the score with that month's leaks "
                       "recovered. The gap is what this page decomposes; months "
                       "with fewer than 3 analyzed games are excluded.")
            st.plotly_chart(charts.multi_line_chart(
                monthly, "month",
                [("actual_pct", "Actual score %", theme.POSITIVE),
                 ("potential_pct", "Ceiling %", theme.ACCENT_GOLD)],
                y_title="Score %", x_title="Month"), theme=None)

    conv_leak = view[view.bucket == "failed_conversion"]
    if len(conv_leak):
        with st.container(border=True):
            st.subheader("Failed conversions, up close")
            st.caption("Where the conversion leaks concentrate: how big the advantage "
                       "was at its peak, in which phase the position first became "
                       "winning, and how much clock you had when it did.")
            band_col, phase_col, clock_col = st.columns(3)
            with band_col:
                st.caption("By peak advantage")
                st.plotly_chart(charts.bar_chart(
                    data.conversion_breakdown(view, "adv_band"),
                    "adv_band", "leaked", theme.NEGATIVE, height=280,
                    x_title="Advantage at its peak", y_title="Points leaked"), theme=None)
            with phase_col:
                st.caption("By phase it became winning")
                st.plotly_chart(charts.bar_chart(
                    data.conversion_breakdown(view, "conv_phase"),
                    "conv_phase", "leaked", theme.NEGATIVE, height=280,
                    x_title="Phase it became winning", y_title="Points leaked"), theme=None)
            with clock_col:
                st.caption("By clock remaining at that moment")
                st.plotly_chart(charts.bar_chart(
                    data.conversion_breakdown(view, "conv_clock"),
                    "conv_clock", "leaked", theme.NEGATIVE, height=280,
                    x_title="Clock remaining", y_title="Points leaked"), theme=None)

    if len(conv_leak):
        reason_df, piece_df, mate_df = cached_failed_conversion_causes(duck_conn, view)
        with st.container(border=True):
            st.subheader("Why conversions failed")
            st.caption("Of your failed conversions: what happened, at the move level, "
                       "after the position first became winning. Both the hanging-piece "
                       "check (same detection Tactical Highlights' hallucination section "
                       "uses) and the blown-forced-mate check (same as Tactical "
                       "Highlights' blown-mates list) need engine analysis -- but since "
                       "this ledger only ever contains fully analyzed games to begin "
                       "with, every failed conversion already has as much engine coverage "
                       "as it will ever get, unlike the resignation-cause breakdown on "
                       "Game Endings. This is an all-time picture, not a calendar trend: "
                       "the ledger itself only covers analyzed games, and analysis "
                       "coverage is heavily skewed toward recently-synced games, so a "
                       "by-year cut of these causes would read as \"this started "
                       "happening recently\" when it's really \"this is when the engine "
                       "got there.\"")
            if reason_df.empty:
                st.info(theme.thin_data_message(0, 1))
            else:
                reason_plot = reason_df.copy()
                reason_plot["reason"] = reason_plot["reason"].map(
                    lambda x: _CONVERSION_REASON_LABELS.get(x, x))
                st.plotly_chart(
                    charts.bar_chart(reason_plot, "reason", "pct", theme.ACCENT_GOLD,
                                      x_title="Cause", y_title="% of failed conversions"),
                    theme=None)

                col1, col2 = st.columns(2)
                with col1:
                    st.write("**Which piece hung**")
                    if piece_df.empty:
                        st.info(theme.thin_data_message(0, 1))
                    else:
                        piece_plot = piece_df.copy()
                        piece_plot["piece_name"] = piece_plot["hung_piece"].map(
                            lambda p: str(data.PIECE_NAME.get(p, p)).title())
                        order = {p: i for i, p in enumerate(data.PIECE_ORDER)}
                        piece_plot = piece_plot.sort_values(
                            by="hung_piece", key=lambda s: s.map(order))
                        st.plotly_chart(
                            charts.bar_chart(piece_plot, "piece_name", "pct", theme.NEGATIVE,
                                              x_title="Piece hung",
                                              y_title="% of hung-piece failed conversions"),
                            theme=None)
                with col2:
                    st.write("**How deep the blown mate was**")
                    if mate_df.empty:
                        st.info(theme.thin_data_message(0, 1))
                    else:
                        st.plotly_chart(
                            charts.bar_chart(mate_df, "bucket", "pct", theme.NEGATIVE,
                                              x_title="Forced mate distance",
                                              y_title="% of blown-mate failed conversions"),
                            theme=None)

    with st.container(border=True):
        st.subheader("Costliest games")
        st.caption("The individual games that leaked the most points. Tick a row's "
                   "checkbox to open that game's full story.")
        worst = view[view.bucket != "none"].nlargest(15, "leaked").reset_index(drop=True)
        # Conversion leaks are measured from the peak; swindle leaks from
        # the post-collapse chance -- show whichever the leak was scored
        # against so the % column always explains the points column.
        worst["best_chance"] = worst.peak_wp.where(
            worst.bucket != "missed_swindle", worst.post_lost_peak_wp)
        worst["bucket_label"] = worst.bucket.map(data.BUCKET_LABEL)
        # or-"" not None: LinkColumn renders every null flavor as literal
        # "None"; only empty string gives an empty cell (see game_explorer_view).
        worst["url"] = worst.apply(
            lambda r: chess_display.lichess_game_url(r.game_id, r.site) or "", axis=1)
        selection = st.dataframe(
            worst, width='stretch', on_select="rerun", hide_index=True,
            selection_mode="single-row", key="points_worst_table",
            column_order=["url", "utc_date", "opponent_name", "outcome_for_player",
                          "bucket_label", "best_chance", "leaked"],
            column_config={
                "url": st.column_config.LinkColumn("Game", display_text="View ↗",
                                                    width="small"),
                "utc_date": "Date",
                "opponent_name": "Opponent",
                "outcome_for_player": "Result",
                "bucket_label": "Leak",
                "best_chance": st.column_config.NumberColumn(
                    "Best chance", format="percent",
                    help="Your win probability at its most promising moment -- "
                         "what the leak is measured against."),
                "leaked": st.column_config.NumberColumn("Points leaked", format="%.2f"),
            })
        selected_rows = selection.selection.rows if selection and selection.selection else []
        if selected_rows and detail_page is not None:
            st.session_state["selected_game_id"] = worst.iloc[selected_rows[0]].game_id
            st.session_state["return_page"] = self_page
            st.session_state["return_page_label"] = "Where Your Points Go"
            st.switch_page(detail_page)

    with st.expander("How the ledger is scored"):
        st.markdown(
            f"- Only fully analyzed games count, so every curve is complete.\n"
            f"- **Failed conversion**: your win probability reached "
            f"{data.WINNING_WP:.0%}+ and the game wasn't won. Leak = peak "
            f"probability minus points scored.\n"
            f"- **Missed swindle**: you were down to {data.LOST_WP:.0%} or worse, "
            f"the opponent let you back to {data.SWINDLE_CHANCE_WP:.0%}+, and you "
            f"still lost. Leak = the chance you were given.\n"
            f"- **Failed hold**: at move {data.HOLD_EVEN_MIN_MOVE}+ you still had "
            f"{data.EVEN_WP:.0%}+ but never reached winning, and lost. Leak = the "
            f"half point an even game is worth.\n"
            f"- Each game lands in at most one bucket (conversion first, then "
            f"swindle, then hold), so leaked points add up instead of double-"
            f"counting.\n"
            f"- Win probabilities use the same formula as move classification "
            f"(lichess's win% curve); the 90%+ conversion band is the Matchups "
            f"page's \"collapse\" definition, weighted by points instead of "
            f"counted.")
