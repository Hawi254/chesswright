"""Board Chat (Pro feature) data layer: a game-scoped, multi-turn Claude
conversation embedded in Game Detail's variation explorer -- complementary
to AI Coach, not a mode of it. This module itself is plain core CRUD --
same posture as ai_coach.py: no Claude API calls, no tool-set or prompt
logic (that's a later, private chesswright_pro phase). Just conversations,
turns (with an optional per-turn board_directives JSON blob for arrows/
highlights shown alongside that turn), and capability-gap telemetry.

All functions take sqlite_conn first, matching this package's universal
convention. Every write follows this project's documented commit +
PRAGMA wal_checkpoint(TRUNCATE) discipline -- this app also holds a
long-lived DuckDB connection ATTACHed to the same sqlite file, and a plain
commit() alone leaves a row invisible to other connections until process
exit. The _checkpoint helper is duplicated here rather than imported from
data.ai_coach -- it's private (leading underscore) there, and importing a
private symbol across sibling modules for 3 lines is worse than the
duplication itself.

No record_feedback/thumbs-up-down function here: deliberately out of
scope for this feature (see docs/scoping/ai-coach-board-interaction-
2026-07-08.md §3).
"""
import datetime
import json


def _checkpoint(sqlite_conn):
    sqlite_conn.commit()
    sqlite_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def start_conversation(sqlite_conn, game_id: str) -> int:
    """Start a new board-chat conversation for one game, returning its id."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute(
        "INSERT INTO board_chat_conversations (game_id, started_at) VALUES (?, ?)",
        [game_id, now])
    _checkpoint(sqlite_conn)
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
    _checkpoint(sqlite_conn)
    return cur.lastrowid


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
    _checkpoint(sqlite_conn)
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
