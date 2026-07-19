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
from cached_queries import cached_headline_stats


@st.cache_data(show_spinner="Gathering your stats…")
def _build_data_brief(_duck_conn, _sqlite_conn):
    """Thin Streamlit-caching pass-through to the streamlit-free
    dashboard/data/ask_brief.py::build_ask_data_brief -- kept here (rather
    than deleted) so ask_view.py's existing @st.cache_data behavior
    (including cache-clear-on-refresh) is unchanged. See
    docs/superpowers/specs/2026-07-17-ask-page-design.md decision 5."""
    return data.build_ask_data_brief(_duck_conn, _sqlite_conn)


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
