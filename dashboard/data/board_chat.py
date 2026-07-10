"""Board Chat (Pro feature) data layer: a game-scoped, multi-turn Claude
conversation embedded in Game Detail's variation explorer -- complementary
to AI Coach, not a mode of it. This module itself is plain core CRUD --
same posture as ai_coach.py: no Claude API calls, no tool-set or prompt
logic (that's a later, private chesswright_pro phase). Just conversations,
turns (with an optional per-turn board_directives JSON blob for arrows/
highlights shown alongside that turn), and capability-gap telemetry.

All functions take sqlite_conn first, matching this package's universal
convention. Every write just calls sqlite_conn.commit() -- no explicit
WAL checkpoint needed. DuckDB (dashboard/data/_common.get_duckdb_connection)
only ever ATTACHes a private, read-only snapshot copy of the sqlite file,
never the live file, so there's no other connection that needs a write to
be checkpointed to disk for immediate visibility; a plain commit() is
already durable and immediately visible to any other real connection to
the WAL-mode file.

Also record_feedback: thumbs up/down on one assistant turn, identical
shape to ai_coach.py's own record_feedback (see migration 0037's own
comment for why this mirrors migration 0034's ai_coach_turns.feedback
column). Thumbs-down additionally drives an auto-logged capability gap
via record_capability_gap() -- wired in chesswright_pro/board_chat.py's
render(), not here (this module stays plain CRUD, no Streamlit).
"""
import datetime
import json


def start_conversation(sqlite_conn, game_id: str) -> int:
    """Start a new board-chat conversation for one game, returning its id."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute(
        "INSERT INTO board_chat_conversations (game_id, started_at) VALUES (?, ?)",
        [game_id, now])
    sqlite_conn.commit()
    return cur.lastrowid


def add_turn(sqlite_conn, conversation_id: int, role: str, content: str,
             board_directives: str | None = None) -> int:
    """Append one turn. board_directives is an already-JSON-serialized
    string (the caller -- chesswright_pro/board_chat.py's render() --
    json.dumps()s the side_effects["board_directives"] list before
    calling this), or None for a turn with no board directives (every
    user turn, and any assistant turn that didn't call show_arrow/
    highlight_squares)."""
    if role not in ("user", "assistant"):
        raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute("""
        INSERT INTO board_chat_turns
            (conversation_id, role, content, board_directives, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, [conversation_id, role, content, board_directives, now])
    sqlite_conn.commit()
    return cur.lastrowid


def record_feedback(sqlite_conn, turn_id: int, feedback: int) -> None:
    """Record thumbs up (+1) / thumbs down (-1) on one assistant turn.

    Raises ValueError if turn_id doesn't exist, isn't role='assistant', or
    feedback isn't +1/-1 -- feedback is only meaningful on Claude's own
    replies, never on the player's own messages. Exact structural mirror
    of ai_coach.record_feedback, board_chat_turns substituted for
    ai_coach_turns.
    """
    if feedback not in (1, -1):
        raise ValueError(f"feedback must be 1 or -1, got {feedback!r}")
    row = sqlite_conn.execute(
        "SELECT role FROM board_chat_turns WHERE id = ?", [turn_id]).fetchone()
    if row is None:
        raise ValueError(f"no board_chat_turns row with id={turn_id}")
    if row[0] != "assistant":
        raise ValueError(
            f"turn {turn_id} has role={row[0]!r}, feedback only applies to "
            f"role='assistant' turns")
    sqlite_conn.execute(
        "UPDATE board_chat_turns SET feedback = ? WHERE id = ?", [feedback, turn_id])
    sqlite_conn.commit()


def get_conversation_messages(sqlite_conn, conversation_id: int) -> list[dict]:
    """Anthropic messages=[{"role", "content"}] shape -- role/content only,
    board_directives excluded (identical purpose and shape to
    ai_coach.get_conversation_messages; Claude never needs to see its own
    past tool-call side effects replayed as text)."""
    rows = sqlite_conn.execute("""
        SELECT role, content FROM board_chat_turns
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, [conversation_id]).fetchall()
    return [{"role": role, "content": content} for role, content in rows]


def get_turns_for_display(sqlite_conn, conversation_id: int) -> list[dict]:
    """Full turn rows for UI rendering / conversation replay: id, role,
    content, board_directives (json.loads()'d back to a list, or None),
    created_at. NEW relative to ai_coach.py -- that module has no display-
    shape getter distinct from get_conversation_messages because its chat
    panel builds display_history incrementally in session_state rather
    than reloading a past conversation; board chat needs this because §9's
    "reopening a past conversation faithfully redisplays what was shown"
    requirement means a conversation can be loaded fresh, not just built
    up turn-by-turn in one sitting."""
    rows = sqlite_conn.execute("""
        SELECT id, role, content, board_directives, created_at
        FROM board_chat_turns
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, [conversation_id]).fetchall()
    return [
        {
            "id": r[0], "role": r[1], "content": r[2],
            "board_directives": json.loads(r[3]) if r[3] is not None else None,
            "created_at": r[4],
        }
        for r in rows
    ]


def list_conversations_for_game(sqlite_conn, game_id: str) -> list[dict]:
    """Past conversations for this game, newest first: id, started_at,
    turn_count (a COUNT(*) subquery on board_chat_turns) -- feeds a
    "past conversations" affordance in the chat panel, same list-with-load
    shape as game_detail_view.py's own _render_saved_variations (list +
    Load button), not a new UI idiom."""
    rows = sqlite_conn.execute("""
        SELECT c.id, c.started_at,
               (SELECT COUNT(*) FROM board_chat_turns t
                WHERE t.conversation_id = c.id) AS turn_count
        FROM board_chat_conversations c
        WHERE c.game_id = ?
        ORDER BY c.started_at DESC, c.id DESC
    """, [game_id]).fetchall()
    return [
        {"id": r[0], "started_at": r[1], "turn_count": r[2]}
        for r in rows
    ]


def record_capability_gap(sqlite_conn, turn_id: int, question_summary: str,
                           missing_data_description: str) -> int:
    """Identical logic to ai_coach.record_capability_gap, targeting
    board_chat_capability_gaps instead (see migration 0036's own comment
    on why this is a dedicated table, not a reuse of
    ai_coach_capability_gaps)."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute("""
        INSERT INTO board_chat_capability_gaps
            (turn_id, question_summary, missing_data_description, created_at)
        VALUES (?, ?, ?, ?)
    """, [turn_id, question_summary, missing_data_description, now])
    sqlite_conn.commit()
    return cur.lastrowid


def get_capability_gaps(sqlite_conn, limit: int = 200) -> list[dict]:
    """Identical logic to ai_coach.get_capability_gaps, targeting
    board_chat_capability_gaps."""
    rows = sqlite_conn.execute("""
        SELECT g.id, g.turn_id, g.question_summary,
               g.missing_data_description, g.created_at
        FROM board_chat_capability_gaps g
        ORDER BY g.created_at DESC LIMIT ?
    """, [limit]).fetchall()
    return [
        {"id": r[0], "turn_id": r[1], "question_summary": r[2],
         "missing_data_description": r[3], "created_at": r[4]}
        for r in rows
    ]
