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
import theme
from _common import get_connections
from cached_queries import cached_career_findings, cached_headline_stats


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

    # Most common missed tactical motifs
    try:
        df = data.get_motif_breakdown(_sqlite_conn)
        if df is not None and not df.empty:
            lines = []
            for row in df.head(5).itertuples(index=False):
                lines.append(
                    f"  {row.motif}: missed {int(row.n_missed)}x across "
                    f"{int(row.n_games)} games, avg CPL={row.avg_cpl:.1f}"
                )
            sections.append("MOST COMMON MISSED TACTICS:\n" + "\n".join(lines))
        else:
            sections.append("MOST COMMON MISSED TACTICS: (no data yet)")
    except Exception:
        sections.append("MOST COMMON MISSED TACTICS: (unavailable)")

    return "\n\n".join(sections)


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

    history: list[dict] = st.session_state.setdefault("ask_history", [])

    question = st.text_input(
        "Your question",
        placeholder="e.g. When do I blunder most — opening, middlegame, or endgame?",
        label_visibility="collapsed",
    )
    ask_clicked = st.button("Ask", type="primary", disabled=not question.strip())

    if ask_clicked and question.strip():
        with st.spinner("Thinking..."):
            try:
                brief = _build_data_brief(duck_conn, sqlite_conn)
                answer = claude_narrative.answer_question(question.strip(), brief)
                history.insert(0, {"question": question.strip(), "answer": answer})
            except claude_narrative.MissingApiKeyError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Claude API call failed: {e}")
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
