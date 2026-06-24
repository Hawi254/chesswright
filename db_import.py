"""Import an existing chesswright-compatible SQLite database (e.g. one
built by running the original open backend standalone, or a copy from a
previous chesswright install) -- copies it into THIS install's own
~/.chesswright/ directory rather than referencing the original file in
place. Same isolation principle this project already applies to the
original chess-analyzer project's live database (BRIEF.md S5): a path
this app doesn't own can move, get locked by another process, or be a
live database still being written to by something else -- copy once,
evolve independently, exactly like the backend modules themselves were
brought into this repo.
"""
import pathlib
import sqlite3

import migrate

# Columns this app actually reads from `games` (db.py/analytics.py/
# dashboard views) -- not the full schema, just enough to reject an
# unrelated SQLite file that happens to have its own "games" table rather
# than let migrate()'s CREATE TABLE IF NOT EXISTS silently leave an
# incompatible table in place.
REQUIRED_GAMES_COLUMNS = {"id", "white", "black", "result", "analysis_status"}


class DatabaseImportError(Exception):
    """Raised for any reason a candidate file can't be treated as a real
    chesswright-compatible database -- caught by the Settings page to show
    a clear message instead of crashing."""


def validate_source(src_path: pathlib.Path):
    """Confirms src_path is a real, openable SQLite file, and if it already
    has a `games` table, that it has the columns this app depends on."""
    if not src_path.is_file():
        raise DatabaseImportError(f"{src_path} is not a file.")
    conn = sqlite3.connect(str(src_path))
    try:
        conn.execute("PRAGMA schema_version")
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "games" in tables:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
            missing = REQUIRED_GAMES_COLUMNS - cols
            if missing:
                raise DatabaseImportError(
                    "This file has a 'games' table, but it's missing "
                    f"columns this app expects ({', '.join(sorted(missing))}) "
                    "-- it doesn't look like a chesswright-compatible "
                    "database.")
    except sqlite3.DatabaseError as e:
        raise DatabaseImportError(f"Not a valid SQLite database: {e}") from e
    finally:
        conn.close()


def suggest_player_name(db_path: pathlib.Path):
    """Returns the most frequently-appearing white/black username across
    the imported games, as a SUGGESTION only -- never auto-applied. An
    arbitrary database doesn't unambiguously indicate whose account it is
    (a hand-assembled or multi-identity file is possible, however
    unlikely), so this is pre-filled for the user to confirm, the same
    "honest, not silently assumed" posture as the onboarding wizard's
    live-calibrated time estimate."""
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("""
            SELECT name, COUNT(*) AS n FROM (
                SELECT white AS name FROM games
                UNION ALL
                SELECT black AS name FROM games
            )
            WHERE name IS NOT NULL
            GROUP BY name ORDER BY n DESC LIMIT 1
        """).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return row[0] if row else None


def import_database(src_path: pathlib.Path, dest_dir: pathlib.Path) -> pathlib.Path:
    """Copies src_path into dest_dir under a new name (never overwrites an
    existing chess.db) and runs the existing migrate() against the copy --
    migrate() is already safe to call against a partially-migrated, fully
    raw (no schema_migrations table), or already-up-to-date file, so no
    special-casing is needed here for "how old is this file's schema."
    Returns the path of the imported copy; raises DatabaseImportError and
    cleans up the copy on any failure.

    Uses sqlite3's own backup() API, not a raw byte copy -- every
    chesswright database is WAL-mode (migrations/0001_init.sql), and a
    plain shutil.copy2() of a WAL-mode file that's open or being actively
    written by another process can read a torn, structurally-inconsistent
    snapshot straight off disk. A real, reproduced incident: exactly this
    happened live -- a plain-copy import produced a file ~60MB shorter
    than two other imports of presumably the same source, unopenable
    (`sqlite3.DatabaseError: database disk image is malformed`), and
    nothing here caught it, since the only post-copy check was a
    foreign-key consistency check, which doesn't validate page-level
    structure at all. backup() takes a real, consistent SQLite-level
    snapshot (the same mechanism VACUUM INTO uses), safe against a
    concurrently-written source. The integrity_check below is a second,
    independent line of defense -- it also catches a SOURCE file that was
    already corrupted before we ever touched it, which backup() alone
    can't rule out."""
    validate_source(src_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"imported_{src_path.stem}.db"
    counter = 1
    while dest_path.exists():
        dest_path = dest_dir / f"imported_{src_path.stem}_{counter}.db"
        counter += 1

    src_conn = sqlite3.connect(str(src_path))
    try:
        dest_conn = sqlite3.connect(str(dest_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    try:
        integrity = sqlite3.connect(str(dest_path)).execute("PRAGMA integrity_check").fetchall()
        if integrity != [("ok",)]:
            raise DatabaseImportError(
                "The imported database failed an integrity check -- it may be "
                "corrupted or was still being written to when copied. Not importing it.")
        migrate.migrate(str(dest_path))
        conn = sqlite3.connect(str(dest_path))
        try:
            problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            conn.close()
        if problems:
            raise DatabaseImportError(
                f"The imported database failed a foreign-key consistency "
                f"check ({len(problems)} problem row(s)) -- not importing it.")
    except (RuntimeError, DatabaseImportError):
        dest_path.unlink(missing_ok=True)
        raise

    return dest_path
