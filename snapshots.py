"""Historical snapshot store for headline metrics (docs/superpowers/
specs/2026-07-14-insights-page-redesign-phase2-snapshot-store-design.md).
Sqlite-only by design -- see that spec's Context section for why this
deliberately does not reuse dashboard/data/_shared.py's
get_headline_stats(), which needs a duck_conn this module's only caller
(sync.py) has never opened and shouldn't have to.

Duplicates dashboard/confidence.py's default_thresholds()/confidence_tier()
and dashboard/data/_shared.py's estimate_rating_from_acpl() rather than
importing them: confidence.py and _shared.py both live under dashboard/,
which is only ever on sys.path for processes that explicitly add it
(tests/conftest.py, api/db.py, desktop_app.py, react_desktop_app.py).
sync.py -- this module's only caller -- has no sys.path.insert calls at
all, so `from confidence import ...` would raise ModuleNotFoundError the
first time a real sync ran this code path. Same reasoning _shared.py
itself already uses for its own local duplication of insights.py's
MIN_BUCKET_MOVES: no root-level module imports from dashboard/ anywhere
in this codebase today.
"""
import datetime
import math

import analytics

MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING = 20

_TREND_WINDOW_DAYS = 90

_MEDIUM_MULTIPLIER = 3
_HIGH_MULTIPLIER = 8


def _default_thresholds(low):
    """Identical scheme to dashboard/confidence.py's default_thresholds
    -- see that module's docstring. Duplicated, not imported; see this
    module's docstring."""
    return {
        "low": low,
        "medium": low * _MEDIUM_MULTIPLIER,
        "high": low * _HIGH_MULTIPLIER,
    }


def _confidence_tier(n, thresholds):
    """Identical logic to dashboard/confidence.py's confidence_tier --
    see that module's docstring. Duplicated, not imported; see this
    module's docstring."""
    ordered = sorted(thresholds.items(), key=lambda kv: kv[1])
    tier = "insufficient"
    for name, cutoff in ordered:
        if n >= cutoff:
            tier = name
    return tier


def _estimate_rating_from_acpl(acpl: float) -> int:
    """Identical formula to dashboard/data/_shared.py's
    estimate_rating_from_acpl -- see that function's docstring for the
    citation. Duplicated, not imported; see this module's docstring."""
    return round(3100 * math.exp(-0.01 * acpl))


def record_snapshot(conn):
    """Computes today's headline stats via plain sqlite3 queries (no
    duck_conn -- see module docstring) and upserts one row into
    metric_snapshots keyed on today's date. Called from sync.py right
    after achievements.evaluate(), wrapped in the same try/except
    isolation so a snapshot failure can never fail a sync."""
    today = datetime.date.today().isoformat()
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    analyzed_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE analysis_status='done'").fetchone()[0]
    n_moves, _, acpl, blunder_rate = analytics.acpl_and_blunder_rate(conn)
    win_row = conn.execute("""
        SELECT 100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*)
        FROM games WHERE outcome_for_player IS NOT NULL
    """).fetchone()
    win_pct = win_row[0]

    rating_confidence = None
    implied_rating = None
    if acpl is not None:
        rating_confidence = _confidence_tier(
            n_moves, _default_thresholds(MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING))
        if rating_confidence != "insufficient":
            implied_rating = _estimate_rating_from_acpl(acpl)
        else:
            rating_confidence = None

    conn.execute("""
        INSERT INTO metric_snapshots
            (snapshot_date, total_games, analyzed_games, acpl, blunder_rate,
             win_pct, n_analyzed_moves, implied_rating, rating_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_date) DO UPDATE SET
            total_games=excluded.total_games, analyzed_games=excluded.analyzed_games,
            acpl=excluded.acpl, blunder_rate=excluded.blunder_rate,
            win_pct=excluded.win_pct, n_analyzed_moves=excluded.n_analyzed_moves,
            implied_rating=excluded.implied_rating,
            rating_confidence=excluded.rating_confidence
    """, (today, total_games, analyzed_games, acpl, blunder_rate, win_pct,
          n_moves, implied_rating, rating_confidence))
    conn.commit()


def get_headline_trend(conn, current_stats: dict) -> dict:
    """current_stats is the live get_headline_stats() dict this call's
    caller already fetched (api/main.py already computes it for the
    /api/overview/headline-stats endpoint) -- passed in rather than
    recomputed here so this module still never needs a duck_conn (see
    this module's own docstring) and there is exactly one code path that
    calls get_headline_stats().

    Finds the metric_snapshots row closest to (but not after) 90 days
    ago. Every *_delta is None when no such row exists, or when the
    corresponding current_stats field is itself None (nothing to diff
    against)."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=_TREND_WINDOW_DAYS)).isoformat()
    row = conn.execute("""
        SELECT snapshot_date, acpl, blunder_rate, win_pct, implied_rating
        FROM metric_snapshots
        WHERE snapshot_date <= ?
        ORDER BY snapshot_date DESC LIMIT 1
    """, (cutoff,)).fetchone()

    if row is None:
        return {
            "compared_to_date": None,
            "acpl_delta": None, "blunder_rate_delta": None,
            "win_pct_delta": None, "implied_rating_delta": None,
        }

    compared_to_date, past_acpl, past_blunder, past_win, past_rating = row

    def _delta(current, past):
        return None if current is None or past is None else current - past

    return {
        "compared_to_date": compared_to_date,
        "acpl_delta": _delta(current_stats["acpl"], past_acpl),
        "blunder_rate_delta": _delta(current_stats["blunder_rate"], past_blunder),
        "win_pct_delta": _delta(current_stats["win_pct"], past_win),
        "implied_rating_delta": _delta(current_stats["implied_rating"], past_rating),
    }
