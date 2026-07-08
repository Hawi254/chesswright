"""AI Coach (Pro feature) data layer: a conversational chat assistant over a
player's own chess-analysis data. This module itself is plain core CRUD --
same posture as srs.py: no Claude API calls, no tool-set or prompt logic
(that's a later, private chesswright_pro phase). Just conversations, turns,
feedback, and the rolling profile summary that a later phase regenerates
periodically from conversation history.

All functions take sqlite_conn first, matching this package's universal
convention. Every write follows this project's documented commit +
PRAGMA wal_checkpoint(TRUNCATE) discipline (see _shared.save_narrative) --
this app also holds a long-lived DuckDB connection ATTACHed to the same
sqlite file, and a plain commit() alone leaves a row invisible to other
connections until process exit.
"""
import datetime


def _checkpoint(sqlite_conn):
    sqlite_conn.commit()
    sqlite_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def start_conversation(sqlite_conn) -> int:
    """Start a new conversation, returning its new conversation_id."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute(
        "INSERT INTO ai_coach_conversations (started_at) VALUES (?)", [now])
    _checkpoint(sqlite_conn)
    return cur.lastrowid


def add_turn(sqlite_conn, conversation_id: int, role: str, content: str) -> int:
    """Append one turn to a conversation, returning the new turn id.

    role must be 'user' or 'assistant' (enforced by the table's CHECK
    constraint too, but validated here first for a clearer error).
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute("""
        INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
    """, [conversation_id, role, content, now])
    _checkpoint(sqlite_conn)
    return cur.lastrowid


def record_feedback(sqlite_conn, turn_id: int, feedback: int) -> None:
    """Record thumbs up (+1) / thumbs down (-1) on one assistant turn.

    Raises ValueError if turn_id doesn't exist, isn't role='assistant', or
    feedback isn't +1/-1 -- feedback is only meaningful on the coach's own
    replies, never on the player's own messages.
    """
    if feedback not in (1, -1):
        raise ValueError(f"feedback must be 1 or -1, got {feedback!r}")
    row = sqlite_conn.execute(
        "SELECT role FROM ai_coach_turns WHERE id = ?", [turn_id]).fetchone()
    if row is None:
        raise ValueError(f"no ai_coach_turns row with id={turn_id}")
    if row[0] != "assistant":
        raise ValueError(
            f"turn {turn_id} has role={row[0]!r}, feedback only applies to "
            f"role='assistant' turns")
    sqlite_conn.execute(
        "UPDATE ai_coach_turns SET feedback = ? WHERE id = ?", [feedback, turn_id])
    _checkpoint(sqlite_conn)


def get_conversation_messages(sqlite_conn, conversation_id: int) -> list[dict]:
    """All turns for one conversation, in order, shaped as an Anthropic
    messages=[{"role": ..., "content": ...}] list -- how a later phase
    replays conversation history back to Claude."""
    rows = sqlite_conn.execute("""
        SELECT role, content FROM ai_coach_turns
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, [conversation_id]).fetchall()
    return [{"role": role, "content": content} for role, content in rows]


def get_all_turns(sqlite_conn, exclude_thumbs_down: bool = False,
                   since: str | None = None) -> list[dict]:
    """Turns across ALL conversations, ordered by created_at -- feeds a
    later phase's rolling-profile regeneration.

    exclude_thumbs_down: drop turns with feedback == -1, so regeneration
    doesn't reinforce advice the player marked wrong. Only the down-voted
    assistant row itself is dropped -- the user question that prompted it
    is deliberately kept (a caller building a transcript from this should
    treat a kept question with no following assistant turn as "answered,
    but the answer was marked unhelpful and omitted," not silently ignore
    the gap -- see chesswright_pro/ai_coach.py's maybe_regenerate_profile).
    since: only turns with created_at > this ISO timestamp (e.g. "turns
    since the profile was last generated").
    """
    sql = """
        SELECT id, conversation_id, role, content, created_at, feedback
        FROM ai_coach_turns
        WHERE 1=1
    """
    params = []
    if exclude_thumbs_down:
        sql += " AND (feedback IS NULL OR feedback != -1)"
    if since is not None:
        sql += " AND created_at > ?"
        params.append(since)
    sql += " ORDER BY created_at ASC, id ASC"
    rows = sqlite_conn.execute(sql, params).fetchall()
    return [
        {
            "id": r[0], "conversation_id": r[1], "role": r[2],
            "content": r[3], "created_at": r[4], "feedback": r[5],
        }
        for r in rows
    ]


def get_profile(sqlite_conn) -> dict | None:
    """The current profile row (singleton id=1), or None if it doesn't
    exist yet (no profile has ever been generated)."""
    row = sqlite_conn.execute("""
        SELECT summary_text, source_turns, generated_at, model
        FROM ai_coach_profile WHERE id = 1
    """).fetchone()
    if row is None:
        return None
    return {
        "summary_text": row[0], "source_turns": row[1],
        "generated_at": row[2], "model": row[3],
    }


def upsert_profile(sqlite_conn, summary_text: str, source_turns: int,
                    generated_at: str, model: str) -> None:
    """Upsert the singleton profile row (id=1)."""
    sqlite_conn.execute("""
        INSERT INTO ai_coach_profile (id, summary_text, source_turns, generated_at, model)
        VALUES (1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            summary_text = excluded.summary_text,
            source_turns = excluded.source_turns,
            generated_at = excluded.generated_at,
            model = excluded.model
    """, [summary_text, source_turns, generated_at, model])
    _checkpoint(sqlite_conn)


def record_capability_gap(sqlite_conn, turn_id: int, question_summary: str,
                           missing_data_description: str) -> int:
    """Log one structured 'I couldn't fully answer this' report. turn_id
    must already exist (the assistant's own reply row) -- see
    chesswright_pro/ai_coach.py's run_turn()/render() for why this is
    recorded AFTER the turn is persisted, not during the tool loop itself."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = sqlite_conn.execute("""
        INSERT INTO ai_coach_capability_gaps
            (turn_id, question_summary, missing_data_description, created_at)
        VALUES (?, ?, ?, ?)
    """, [turn_id, question_summary, missing_data_description, now])
    _checkpoint(sqlite_conn)
    return cur.lastrowid


def get_capability_gaps(sqlite_conn, limit: int = 200) -> list[dict]:
    """Most recent capability-gap reports, newest first -- the actual
    'gap-watch backlog' a developer or an opted-in pilot tester reads
    instead of re-auditing the tool table from scratch."""
    rows = sqlite_conn.execute("""
        SELECT g.id, g.turn_id, g.question_summary,
               g.missing_data_description, g.created_at
        FROM ai_coach_capability_gaps g
        ORDER BY g.created_at DESC LIMIT ?
    """, [limit]).fetchall()
    return [
        {"id": r[0], "turn_id": r[1], "question_summary": r[2],
         "missing_data_description": r[3], "created_at": r[4]}
        for r in rows
    ]


def count_turns_since(sqlite_conn, since: str) -> int:
    """Cheap point-style COUNT of turns created after `since` (ISO
    timestamp) -- used to decide "is the profile stale enough to
    regenerate" without pulling full turn content.

    Takes sqlite_conn, never duck_conn: this is a point/count lookup, and
    this codebase has a documented, measured rule that DuckDB's ATTACHed
    sqlite scanner doesn't push predicates down as index seeks across the
    ATTACH boundary -- every point/count lookup in this codebase already
    goes through sqlite_conn for this reason (see get_game_detail's
    docstring in data/game_explorer.py for the full EXPLAIN-confirmed
    mechanism).
    """
    row = sqlite_conn.execute(
        "SELECT COUNT(*) FROM ai_coach_turns WHERE created_at > ?", [since]
    ).fetchone()
    return row[0]
