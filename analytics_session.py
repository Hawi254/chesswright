"""Session-context computation (session_game_number, prior_outcome,
losing_streak, session_start/session_end) -- one of four sibling modules
split out of analytics.py (largest-file modularization, 2026-07-17). A
leaf module: no dependency on this split's other three siblings.
"""
import datetime


def compute_session_context(conn, session_gap_minutes):
    """Walks ALL games (not just analyzed ones) in real chronological order
    and assigns, per game: session_game_number (1-indexed position within
    its session), prior_outcome (the immediately preceding game's outcome
    within the SAME session, None for the first game of a session), and
    losing_streak (consecutive prior losses within the same session).
    Session boundary = a gap of more than session_gap_minutes since the
    previous game's start (start-to-start, not end-to-start -- see plan
    note on why this simplification is fine for this dataset).

    Computed over all games (engine-analyzed or not) because outcome/
    timestamp are tier-2 ingest-time facts available regardless of
    analysis status -- only the ACPL/blunder-rate numbers later need a
    game to be analyzed, not the session structure itself.

    Returns (context, skipped), where context is a list of (game_id,
    session_game_number, prior_outcome, losing_streak, session_start,
    session_end) tuples -- session_start/session_end (added for the
    Playing Sessions rollup, roadmap §15 unit #4) are ISO-format strings
    (datetime.isoformat()), the same for every game in a given session.
    session_start is known as soon as a session begins (the first game's
    dt, held in session_start_by_id below); session_end is the LAST
    game's dt in that session, which isn't known until the session
    closes. Rather than rewrite the single forward pass above into a
    lookahead, a synthetic per-session integer id is assigned during the
    SAME walk (incremented each time a new session starts), and a second,
    cheap pass over the already-collected rows (no new query, no
    re-walk of the boundary logic) computes each session's max dt and
    broadcasts it back onto every row sharing that session id."""
    rows = conn.execute("""
        SELECT id, utc_date, utc_time, outcome_for_player FROM games
        WHERE utc_date IS NOT NULL AND utc_date != ''
          AND utc_time IS NOT NULL AND utc_time != ''
        ORDER BY utc_date, utc_time, id
    """).fetchall()

    gap = datetime.timedelta(minutes=session_gap_minutes)
    raw_rows = []  # (game_id, session_game_number, prior_outcome, losing_streak, session_id, dt)
    skipped = 0
    prev_dt = None
    prev_outcome = None
    session_game_number = 0
    losing_streak = 0
    session_id = -1
    session_start_by_id = {}

    for game_id, utc_date, utc_time, outcome in rows:
        try:
            dt = datetime.datetime.strptime(f"{utc_date} {utc_time}", "%Y.%m.%d %H:%M:%S")
        except ValueError:
            skipped += 1
            continue

        if prev_dt is None or (dt - prev_dt) > gap:
            session_game_number = 1
            prior_outcome = None
            losing_streak = 0
            session_id += 1
            session_start_by_id[session_id] = dt
        else:
            session_game_number += 1
            prior_outcome = prev_outcome
            losing_streak = losing_streak + 1 if prev_outcome == "loss" else 0

        raw_rows.append((game_id, session_game_number, prior_outcome, losing_streak, session_id, dt))
        prev_dt = dt
        prev_outcome = outcome

    # Second pass (over the already-collected rows, not a new DB query):
    # each session's end is simply the max dt among its rows.
    session_end_by_id = {}
    for row in raw_rows:
        sid, dt = row[4], row[5]
        if sid not in session_end_by_id or dt > session_end_by_id[sid]:
            session_end_by_id[sid] = dt

    context = [
        (game_id, sgn, prior_outcome, losing_streak,
         session_start_by_id[sid].isoformat(), session_end_by_id[sid].isoformat())
        for game_id, sgn, prior_outcome, losing_streak, sid, dt in raw_rows
    ]
    return context, skipped


def ensure_session_ctx(conn, session_gap_minutes):
    """Idempotent within a connection.

    Fast path (after migration 0023): if session_ctx_cache is current (game
    count unchanged since last build), the TEMP TABLE is created from the
    32k-row cache in <100ms instead of running compute_session_context()
    (~500ms).  Stale or absent cache falls back to a full rebuild and
    persists the result so the next start is fast.

    session_start/session_end columns (migration 0038) are carried through
    both the fast path and the rebuild path unchanged -- see
    compute_session_context's docstring for what they hold.
    """
    if conn.execute("SELECT name FROM sqlite_temp_master WHERE name='session_ctx'").fetchone():
        return

    game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    meta = conn.execute("SELECT session_game_count FROM ctx_cache_meta WHERE id=1").fetchone()
    cache_current = (meta and meta[0] == game_count and game_count > 0
                     and conn.execute("SELECT COUNT(*) FROM session_ctx_cache").fetchone()[0] > 0)

    if cache_current:
        conn.execute("""CREATE TEMP TABLE session_ctx (
            game_id TEXT PRIMARY KEY, session_game_number INTEGER,
            prior_outcome TEXT, losing_streak INTEGER,
            session_start TEXT, session_end TEXT
        )""")
        conn.execute("INSERT INTO session_ctx SELECT * FROM session_ctx_cache")
        return

    context, skipped = compute_session_context(conn, session_gap_minutes)
    if skipped:
        print(f"  ({skipped} game(s) skipped from session analysis -- unparseable timestamp)")

    conn.execute("DELETE FROM session_ctx_cache")
    conn.executemany("INSERT INTO session_ctx_cache VALUES (?,?,?,?,?,?)", context)
    conn.execute("UPDATE ctx_cache_meta SET session_game_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                 (game_count,))
    conn.commit()

    conn.execute("""CREATE TEMP TABLE session_ctx (
        game_id TEXT PRIMARY KEY, session_game_number INTEGER,
        prior_outcome TEXT, losing_streak INTEGER,
        session_start TEXT, session_end TEXT
    )""")
    conn.execute("INSERT INTO session_ctx SELECT * FROM session_ctx_cache")
