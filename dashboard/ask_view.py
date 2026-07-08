"""Ask -- natural-language questions answered from the player's real game data.

Each question is independent (single-turn, no dialogue). Claude receives a
pre-assembled data brief covering headline stats, career findings, openings,
phase accuracy, nemesis opponents, and missed tactical motifs, then answers
in 2-4 sentences grounded only in what that brief contains.

Q&A history lives in session_state -- ephemeral, per-session. Persisting
arbitrary questions to the DB doesn't fit the claude_narratives keyed-subject
model (subject_type + subject_key), and individual Q&A wouldn't benefit from
that cache anyway.
"""
import streamlit as st

import claude_narrative
import data
import pro_gate
import theme
from _common import get_connections
from cached_queries import (
    cached_career_findings, cached_failed_conversion_causes, cached_headline_stats,
    cached_points_ledger, cached_resignation_loss_causes, cached_time_forfeit_loss_breakdown,
)

_CONVERSION_REASON_LABELS = {
    "hung_piece": "hung a piece", "blown_mate": "blew a forced mate",
    "time_pressure": "time pressure", "other": "other / gradual give-back",
}
_RESIGN_REASON_LABELS = {
    "hung_piece": "hung a piece", "faced_mate": "faced a forced mate",
    "time_pressure": "time pressure", "other": "other / gradual decline",
    "not_analyzed": "not yet analyzed",
}


@st.cache_data(show_spinner="Gathering your stats…")
def _build_data_brief(_duck_conn, _sqlite_conn):
    """Structured text block of career stats for the Claude prompt.

    Underscore-prefixed args tell @st.cache_data to skip hashing (connection
    objects aren't serialisable) -- same convention used on every other cached
    data function in the codebase. Regenerated when the user clicks "Refresh
    data" in the sidebar (which clears st.cache_data globally).

    Wraps each section in a try/except so a single unavailable data function
    can't crash the whole brief -- it contributes a "(unavailable)" line instead.
    """
    # Shared cached wrappers, not raw data.get_* calls -- these two are the
    # most expensive queries in the app (~0.4s / ~4.3s) and Overview/Insights
    # have usually already computed them (see cached_queries.py).
    stats = cached_headline_stats(_duck_conn, _sqlite_conn)
    findings = cached_career_findings(_duck_conn, stats.get("blunder_rate"))

    sections = []

    # Headline stats
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

    # Career findings
    if findings:
        lines = "\n".join(
            f"  - {f['title']}: {f['headline']}. {f['detail']}" for f in findings
        )
        sections.append(f"CAREER PATTERN FINDINGS:\n{lines}")
    else:
        sections.append("CAREER PATTERN FINDINGS: (not enough analyzed data yet)")

    # Openings -- top 10 by games played
    try:
        df = data.get_openings_table(_duck_conn, _sqlite_conn)
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

    # Phase accuracy
    try:
        df = data.get_phase_accuracy(_sqlite_conn)
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

    # Toughest opponents -- sorted by lowest score%
    try:
        df = data.get_nemesis_opponents(_duck_conn)
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

    # Most common missed tactical motifs -- framed as % of analyzed games
    # (a raw "missed 927x" count is meaningless without knowing the sample
    # size it's drawn from; % of games makes severity legible on its own).
    try:
        df = data.get_motif_breakdown(_sqlite_conn)
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

    # Points ledger -- winning/even positions thrown away, and why. Bucket
    # size framed as % of fully-analyzed games (the denominator this ledger
    # is actually drawn from), not just a raw game count.
    try:
        classified = cached_points_ledger(_duck_conn)
        summary = data.summarize_buckets(classified)
        total_classified = len(classified)
        if not summary.empty and total_classified:
            lines = [
                f"  {data.BUCKET_LABEL[row.bucket]}: {100.0 * row.n_games / total_classified:.1f}% "
                f"of analyzed games ({int(row.n_games)} of {total_classified}), "
                f"{row.leaked:.1f} points leaked"
                for row in summary.itertuples(index=False)
            ]
            reason_df, _, _ = cached_failed_conversion_causes(_duck_conn, classified)
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

    # Loss causes -- clock vs. blunders
    try:
        reason_df, _, _ = cached_resignation_loss_causes(_duck_conn)
        _, scramble_df, _ = cached_time_forfeit_loss_breakdown(_duck_conn)
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


# (button label, full question) -- chosen to be answerable from every
# section of the data brief that's reliably populated once a player has
# any analyzed games.
_PRESET_QUESTIONS = [
    ("Blunder timing", "When do I blunder most — opening, middlegame, or endgame?"),
    ("Openings to keep/drop", "Which opening should I drop, and which should I play more?"),
    ("Missed tactics", "What's the one tactical motif I keep missing that's costing me the most rating points?"),
    ("Biggest lever", "If I could fix just one habit, what would move my results the most?"),
    ("This week's practice", "What's a realistic, specific thing I should practice this week based on my last batch of games?"),
    ("Thrown-away points", "Where do I throw away winning positions, and why does it usually happen?"),
    ("Clock vs. blunders", "Do I lose more games to the clock or to blunders?"),
]


def _ask(duck_conn, sqlite_conn, question: str, history: list[dict]) -> None:
    with st.spinner("Thinking..."):
        try:
            brief = _build_data_brief(duck_conn, sqlite_conn)
            answer = claude_narrative.answer_question(question, brief)
            history.insert(0, {"question": question, "answer": answer})
        except claude_narrative.MissingApiKeyError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Claude API call failed: {e}")


def render():
    sqlite_conn, duck_conn = get_connections()
    st.title("Ask about your games")
    st.write(
        "Ask a question in plain English and get an answer grounded in your analyzed games. "
        "Claude works from the same stats that drive the rest of this app — win rates, ACPL, "
        "openings, phase accuracy, toughest opponents, and missed tactical patterns. "
        "Hit **Refresh data** in the sidebar after a new analysis batch to see the latest."
    )

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    if stats.get("analyzed_games", 0) == 0:
        st.info(theme.thin_data_message(0, 1))
        return

    if not claude_narrative.api_key_available():
        st.info("Add your own Anthropic API key on the Settings page to enable this feature.")
        return

    if pro_gate.is_pro_active():
        try:
            from chesswright_pro import ai_coach
        except ImportError:
            st.error(
                "Pro is licensed but the chesswright_pro package couldn't be "
                "imported. Try reinstalling it."
            )
            return
        ai_coach.render(duck_conn, sqlite_conn)
        return

    history: list[dict] = st.session_state.setdefault("ask_history", [])

    st.info(
        "**AI Coach** (Chesswright Pro) turns this into a real back-and-forth "
        "conversation: it remembers what you've discussed, builds a rolling "
        "profile of your goals and tendencies that persists and updates across "
        "sessions, lets you give thumbs up/down feedback on answers, and pulls "
        "live data across all these same metrics automatically instead of one "
        "fixed pre-assembled brief. Upgrade to Pro to unlock it."
    )

    st.caption("Try a preset question:")
    row_size = 4
    for i in range(0, len(_PRESET_QUESTIONS), row_size):
        row = _PRESET_QUESTIONS[i:i + row_size]
        for col, (label, preset_question) in zip(st.columns(row_size), row):
            if col.button(label, key=f"ask_preset_{label}", use_container_width=True):
                _ask(duck_conn, sqlite_conn, preset_question, history)
                st.rerun()

    question = st.text_input(
        "Your question",
        placeholder="e.g. When do I blunder most — opening, middlegame, or endgame?",
        label_visibility="collapsed",
    )
    ask_clicked = st.button("Ask", type="primary", disabled=not question.strip())

    if ask_clicked and question.strip():
        _ask(duck_conn, sqlite_conn, question.strip(), history)
        st.rerun()

    if history:
        for entry in history:
            with st.container(border=True):
                st.markdown(f"**Q: {entry['question']}**")
                st.markdown(entry["answer"])
        if len(history) > 1:
            if st.button("Clear history", key="ask_clear"):
                st.session_state["ask_history"] = []
                st.rerun()
