"""Event-type / named tournament & arena breakdown (roadmap §27b,
2026-07-11) -- one of eight topic modules split out of the former
dashboard/data/patterns.py.

Lichess's ingested `event` PGN field carries no tournament INSTANCE id --
only a per-game `Site` URL -- and recurring arenas (e.g. "Hourly
SuperBlitz Arena") share the exact same event name across every instance
ever played, with no game-gap signal that splits "this hour's arena" from
"next week's" (verified empirically against the real dev DB: no bimodal
gap distribution). So this section deliberately does NOT attempt
per-instance tournament grouping -- it only classifies each game's event
into "Casual" (every non-tournament rated game's event is always exactly
"Rated <category> game") vs. "Tournament / Arena" (everything else), and
separately breaks the latter down by the specific event NAME (which arena/
tournament, not which instance of it).
"""
import re

import pandas as pd

from connections import get_config

_CASUAL_EVENT_RE = re.compile(r"^Rated .+ game$")


def _event_perf_rows(duck_conn):
    """One row per (game, event) with that game's own mean_cpl/n_cpl_moves --
    same per-game combined-query shape as get_favorite_underdog_performance/
    get_session_rollup above (a LEFT-JOIN-free per-game GROUP BY avoids the
    move-fan-out overcount a naive SUM over the moves JOIN would produce).
    Adds a `category` column (Casual / Tournament / Arena) classified from
    `event` via _CASUAL_EVENT_RE. Shared by get_event_type_performance and
    get_event_name_breakdown so both stay classification-consistent."""
    df = duck_conn.execute("""
        SELECT g.id AS game_id, g.event, g.outcome_for_player,
               AVG(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN m.cpl END) AS mean_cpl,
               COUNT(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN 1 END)   AS n_cpl_moves
        FROM db.games g JOIN db.moves m ON m.game_id = g.id
        WHERE g.event IS NOT NULL AND g.outcome_for_player IS NOT NULL
        GROUP BY g.id, g.event, g.outcome_for_player
    """).fetchdf()
    if df.empty:
        return df
    df["category"] = df["event"].apply(
        lambda e: "Casual" if _CASUAL_EVENT_RE.match(e) else "Tournament / Arena")
    return df


def _aggregate_event_rows(df, group_col, order=None):
    """Same win_pct/draw_pct/loss_pct/acpl/n_analyzed aggregation formula
    as get_session_rollup's loop -- one row per distinct *group_col* value,
    acpl is None (not dropped/zeroed) when a group has zero analyzed
    moves."""
    out_rows = []
    groups = order if order is not None else df[group_col].unique()
    for label in groups:
        sub = df[df[group_col] == label]
        if not len(sub):
            continue
        n_games = len(sub)
        win_pct = 100.0 * (sub.outcome_for_player == "win").sum() / n_games
        draw_pct = 100.0 * (sub.outcome_for_player == "draw").sum() / n_games
        loss_pct = 100.0 * (sub.outcome_for_player == "loss").sum() / n_games
        analyzed = sub[sub.n_cpl_moves > 0]
        n_analyzed = int(analyzed.n_cpl_moves.sum())
        acpl = ((analyzed.mean_cpl * analyzed.n_cpl_moves).sum() / n_analyzed) if n_analyzed else None
        out_rows.append((label, n_games, win_pct, draw_pct, loss_pct, acpl, n_analyzed))
    return out_rows


def get_event_type_performance(duck_conn, config_path=None) -> pd.DataFrame:
    """Casual vs. Tournament/Arena win/draw/loss% and ACPL -- the 2-category
    summary half of the Event Type Breakdown (Playing Sessions tab). Every
    *casual* rated game's `event` field is always exactly "Rated <category>
    game" (blitz/bullet/rapid/classical), a clean, zero-contamination
    classifier confirmed against every distinct event value in the real dev
    DB; anything else (a named arena or tournament) falls into "Tournament /
    Arena". config_path is accepted for signature consistency with this
    module's other config-driven queries but is currently unused (the
    classification regex has no config knob).

    Games with a NULL `event` or a NULL `outcome_for_player` are excluded,
    matching every other win/draw/loss query in this package.

    Returns exactly 2 rows (Casual first, then Tournament / Arena):
    category, n_games, win_pct, draw_pct, loss_pct, acpl, n_analyzed."""
    cols = ["category", "n_games", "win_pct", "draw_pct", "loss_pct", "acpl", "n_analyzed"]
    df = _event_perf_rows(duck_conn)
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = _aggregate_event_rows(df, "category", order=["Casual", "Tournament / Arena"])
    return pd.DataFrame(rows, columns=cols)


def get_event_name_breakdown(duck_conn, min_games: int | None = None, config_path=None) -> pd.DataFrame:
    """Win/draw/loss% and ACPL for each individually-NAMED tournament/arena
    (e.g. "Hourly SuperBlitz Arena", "Weekly Rapid Arena") -- the specific-
    events half of the Event Type Breakdown. Reuses
    get_event_type_performance's same classification (via _event_perf_rows)
    then restricts to the "Tournament / Arena" category and groups by the
    raw `event` name instead of the 2-way category, so the generic "Rated
    <category> game" casual buckets (already covered by the 2-category
    summary) never appear here. min_games defaults to
    analytics.min_sample_size when not passed explicitly, gating one-off
    or rarely-played events from cluttering the table -- this is a
    per-EVENT-NAME rollup, not per-tournament-instance (see module comment
    above for why the latter isn't feasible from the data Lichess gives us).

    Returns event, n_games, win_pct, draw_pct, loss_pct, acpl, n_analyzed --
    sorted by n_games descending."""
    if min_games is None:
        min_games = get_config(config_path)["analytics"]["min_sample_size"]
    cols = ["event", "n_games", "win_pct", "draw_pct", "loss_pct", "acpl", "n_analyzed"]
    df = _event_perf_rows(duck_conn)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df[df.category == "Tournament / Arena"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = _aggregate_event_rows(df, "event")
    out = pd.DataFrame(rows, columns=cols)
    out = out[out.n_games >= min_games]
    return out.sort_values("n_games", ascending=False).reset_index(drop=True)
