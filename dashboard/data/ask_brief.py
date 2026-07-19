"""Streamlit-free assembly of the Ask feature's data brief -- extracted
from dashboard/ask_view.py::_build_data_brief (now a thin
@st.cache_data-wrapped pass-through to this module) so api/main.py's
FastAPI service can build the same brief without importing streamlit.
See docs/superpowers/specs/2026-07-17-ask-page-design.md decision 5.
"""
from . import game_endings, matchups, openings, patterns, points, tactical
from ._shared import get_headline_stats
from .insights import get_career_findings

_CONVERSION_REASON_LABELS = {
    "hung_piece": "hung a piece", "blown_mate": "blew a forced mate",
    "time_pressure": "time pressure", "other": "other / gradual give-back",
}
_RESIGN_REASON_LABELS = {
    "hung_piece": "hung a piece", "faced_mate": "faced a forced mate",
    "time_pressure": "time pressure", "other": "other / gradual decline",
    "not_analyzed": "not yet analyzed",
}


def build_ask_data_brief(duck_conn, sqlite_conn):
    """Structured text block of career stats for the Claude prompt.

    Wraps each section in a try/except so a single unavailable data function
    can't crash the whole brief -- it contributes a "(unavailable)" line
    instead. Byte-identical output to the pre-extraction ask_view.py version
    (guarded by tests/unit/test_ask_brief.py's golden-text test) -- calls
    the same underlying data.get_* functions cached_queries.py wraps, just
    directly rather than through Streamlit's @st.cache_data.
    """
    stats = get_headline_stats(duck_conn, sqlite_conn)
    findings = get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))

    sections = []

    win_pct_s = f"{stats['win_pct']:.1f}%" if stats.get("win_pct") is not None else "n/a"
    acpl_s    = f"{stats['acpl']:.1f}"      if stats.get("acpl")    is not None else "n/a"
    br_s      = f"{stats['blunder_rate']:.1f}%" if stats.get("blunder_rate") is not None else "n/a"
    sections.append(
        "HEADLINE STATS:\n"
        f"  Total games: {stats.get('total_games', 0):,}\n"
        f"  Engine-analyzed games: {stats.get('analyzed_games', 0):,}\n"
        f"  Overall win rate: {win_pct_s}\n"
        f"  ACPL (avg centipawn loss, lower = more accurate): {acpl_s}\n"
        f"  Overall blunder rate: {br_s}"
    )

    if findings:
        lines = "\n".join(
            f"  - {f['title']}: {f['headline']}. {f['detail']}" for f in findings
        )
        sections.append(f"CAREER PATTERN FINDINGS:\n{lines}")
    else:
        sections.append("CAREER PATTERN FINDINGS: (not enough analyzed data yet)")

    try:
        df = openings.get_openings_table(duck_conn, sqlite_conn)
        if df is not None and not df.empty:
            lines = []
            for row in df.head(10).itertuples(index=False):
                acpl_val = f"{row.acpl:.1f}" if row.acpl is not None else "n/a"
                lines.append(
                    f"  {row.opening_family} ({row.player_color}): "
                    f"{int(row.n)} games, {row.win_pct:.1f}% win, ACPL={acpl_val}"
                )
            sections.append("TOP OPENINGS (by games played):\n" + "\n".join(lines))
        else:
            sections.append("TOP OPENINGS: (no data yet)")
    except Exception:
        sections.append("TOP OPENINGS: (unavailable)")

    try:
        df = patterns.get_phase_accuracy(sqlite_conn)
        if df is not None and not df.empty:
            lines = [
                f"  {row.phase}: ACPL={row.acpl:.1f}, blunder rate={row.blunder_rate:.1f}%"
                for row in df.itertuples(index=False)
            ]
            sections.append("ACCURACY BY GAME PHASE:\n" + "\n".join(lines))
        else:
            sections.append("ACCURACY BY GAME PHASE: (not enough data yet)")
    except Exception:
        sections.append("ACCURACY BY GAME PHASE: (unavailable)")

    try:
        df = matchups.get_nemesis_opponents(duck_conn)
        if df is not None and not df.empty:
            lines = []
            for row in df.sort_values("score_pct").head(5).itertuples(index=False):
                lines.append(
                    f"  {row.opponent_name}: {int(row.n)} games, "
                    f"{row.score_pct:.1f}% score "
                    f"(W{int(row.wins)}/D{int(row.draws)}/L{int(row.losses)})"
                )
            sections.append("TOUGHEST OPPONENTS (lowest score%):\n" + "\n".join(lines))
        else:
            sections.append("TOUGHEST OPPONENTS: (no data yet)")
    except Exception:
        sections.append("TOUGHEST OPPONENTS: (unavailable)")

    try:
        df = tactical.get_motif_breakdown(sqlite_conn)
        analyzed = stats.get("analyzed_games", 0)
        if df is not None and not df.empty and analyzed:
            lines = []
            for row in df.head(5).itertuples(index=False):
                game_pct = 100.0 * row.n_games / analyzed
                lines.append(
                    f"  {row.motif}: missed in {game_pct:.1f}% of analyzed games "
                    f"({int(row.n_games)} of {analyzed}), {row.blunder_pct:.0f}% of those "
                    f"misses were outright blunders (rest were lesser mistakes), "
                    f"avg CPL when missed={row.avg_cpl:.1f}"
                )
            sections.append("MOST COMMON MISSED TACTICS:\n" + "\n".join(lines))
        else:
            sections.append("MOST COMMON MISSED TACTICS: (no data yet)")
    except Exception:
        sections.append("MOST COMMON MISSED TACTICS: (unavailable)")

    try:
        classified = points.classify_points_ledger(points.get_points_ledger(duck_conn))
        summary = points.summarize_buckets(classified)
        total_classified = len(classified)
        if not summary.empty and total_classified:
            lines = [
                f"  {points.BUCKET_LABEL[row.bucket]}: {100.0 * row.n_games / total_classified:.1f}% "
                f"of analyzed games ({int(row.n_games)} of {total_classified}), "
                f"{row.leaked:.1f} points leaked"
                for row in summary.itertuples(index=False)
            ]
            reason_df, _, _ = points.get_failed_conversion_causes(duck_conn, classified)
            if not reason_df.empty:
                reason_lines = [
                    f"    - {_CONVERSION_REASON_LABELS.get(row.reason, row.reason)}: {row.pct:.0f}%"
                    for row in reason_df.itertuples(index=False)
                ]
                lines.append("  Failed-conversion causes:\n" + "\n".join(reason_lines))
            sections.append("POINTS LEDGER (winning/even positions thrown away):\n" + "\n".join(lines))
        else:
            sections.append("POINTS LEDGER: (no leaked points found yet)")
    except Exception:
        sections.append("POINTS LEDGER: (unavailable)")

    try:
        reason_df, _, _ = game_endings.get_resignation_loss_causes(duck_conn)
        _, scramble_df, _ = game_endings.get_time_forfeit_loss_breakdown(duck_conn)
        lines = []
        if not reason_df.empty:
            lines.append("  Resignation losses, by cause:")
            lines += [
                f"    - {_RESIGN_REASON_LABELS.get(row.reason, row.reason)}: {row.pct:.0f}%"
                for row in reason_df.itertuples(index=False)
            ]
        if not scramble_df.empty:
            lines.append("  Time-forfeit (flagged) losses, by clock context:")
            lines += [
                f"    - {row.bucket}: {row.pct:.0f}%"
                for row in scramble_df.itertuples(index=False)
            ]
        if lines:
            sections.append("LOSS CAUSES (clock vs. blunders):\n" + "\n".join(lines))
        else:
            sections.append("LOSS CAUSES: (no data yet)")
    except Exception:
        sections.append("LOSS CAUSES: (unavailable)")

    return "\n\n".join(sections)
