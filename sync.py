#!/usr/bin/env python3
"""
Phase 7: incremental sync of new games from lichess's public games-export
API, so new games flow into the database without manually re-exporting and
re-running ingest.py by hand each time.

Usage:
    python3 sync.py --db chess.db --player "your-lichess-username"

Deliberately a separate script from ingest.py (same one-concern-per-file
reasoning as data.py/narrative.py/theme.py): this owns "where do new games
come from and in what order do they get queued," ingest.py still owns
"how does a PGN become rows."
"""
import argparse
import datetime
import sys
import tempfile
import os

import requests

from config import load_config, pick
from db import get_connection
from ingest import ingest
import achievements

LICHESS_API_URL = "https://lichess.org/api/games/user/{username}"


def compute_since_ms(conn):
    """Returns the epoch-ms cursor to pass as `since` to the lichess API,
    or None if there are no games in the database yet (fetch everything).

    Deliberately the exact timestamp of the most recent known game, NOT
    that +1ms. utc_date/utc_time are stored at 1-second granularity (straight
    from the PGN header) -- lichess's own internal game timestamps have
    real sub-second precision we never see, so a derived cursor can't tell
    whether another game shares that same displayed second but finished a
    moment later. Empirically confirmed against the real API (since=<exact
    second> still returns the game at that exact second -- an inclusive
    lower bound), so using the bare last-known timestamp guarantees no
    other game sharing that second is ever silently and permanently
    skipped. Cost: the most-recently-known game gets harmlessly re-fetched
    and re-ingested on every sync run -- already proven safe (idempotent
    INSERT OR REPLACE for an unanalyzed game, clean FK-isolated skip for an
    already-analyzed one -- see PROJECT_BRIEF.md Sec 3).

    ORDER BY ... LIMIT 1 (not MAX(utc_date)/MAX(utc_time) as two separate
    aggregates) -- the date and time must come from the SAME row, or a
    composite MAX could pair one game's date with a different game's time.
    """
    row = conn.execute("""
        SELECT utc_date, utc_time FROM games
        WHERE utc_date IS NOT NULL AND utc_date != '' AND utc_time IS NOT NULL AND utc_time != ''
        ORDER BY utc_date DESC, utc_time DESC LIMIT 1
    """).fetchone()
    if row is None:
        return None
    utc_date, utc_time = row
    dt = datetime.datetime.strptime(f"{utc_date} {utc_time}", "%Y.%m.%d %H:%M:%S").replace(
        tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_new_games_pgn(player_name, since_ms, timeout_seconds, max_games=None):
    """Streams the lichess games-export API to a temp file, returns the
    file path (caller is responsible for deleting it) or None if the
    response was empty (no new games).

    Lichess's bulk export streams gradually rather than returning
    everything at once -- for a small periodic sync this finishes in
    seconds, but a first-ever sync (or one after a long gap) can be a
    genuinely large backfill that takes minutes. Prints periodic progress
    so a long run never looks like a hang (this project's standing rule
    after a past batch was killed by mistake on exactly that assumption).

    max_games (lichess API's own `max` param) bounds the download itself,
    server-side -- not a client-side truncation after a full fetch. Only
    used by the onboarding wizard's calibration step (BRIEF.md's Phase B),
    which needs a handful of real games fast, not a full history. Regular
    periodic sync.py usage never passes this -- it stays unbounded."""
    url = LICHESS_API_URL.format(username=player_name)
    params = {"pgnInJson": "false", "clocks": "true", "opening": "true"}
    if since_ms is not None:
        params["since"] = since_ms
    if max_games is not None:
        params["max"] = max_games
    resp = requests.get(url, params=params, headers={"Accept": "application/x-chess-pgn"},
                        timeout=timeout_seconds, stream=True)
    if resp.status_code == 429:
        print("Lichess API returned 429 (rate limited) -- try again later.", file=sys.stderr)
        return None
    resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".pgn", delete=False)
    n_bytes = 0
    n_games = 0
    last_reported = 0
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
            n_bytes += len(chunk)
            n_games += chunk.count(b"[Site ")
            if n_games - last_reported >= 200:
                print(f"  ...{n_games} games downloaded so far ({n_bytes / 1_000_000:.1f} MB)")
                last_reported = n_games
    except BaseException:
        tmp.close()
        os.unlink(tmp.name)
        raise
    tmp.close()

    if n_bytes == 0:
        os.unlink(tmp.name)
        return None
    print(f"Download complete: {n_games} games, {n_bytes / 1_000_000:.1f} MB.")
    return tmp.name


def bump_new_games_to_front_of_queue(conn, new_game_ids):
    """Places newly-synced games ahead of the entire remaining historical
    backlog, without disturbing the existing queue_order of anything else
    (so the configured queue_strategy's ordering of the historical backlog
    is untouched -- this is sync.py's own policy, not a new queue_strategy
    value). New games are ordered among themselves chronologically by
    utc_date/utc_time, oldest of the new batch first."""
    if not new_game_ids:
        return
    placeholders = ",".join("?" * len(new_game_ids))
    rows = conn.execute(f"""
        SELECT id FROM games WHERE id IN ({placeholders})
        ORDER BY utc_date, utc_time
    """, new_game_ids).fetchall()
    ordered_ids = [r[0] for r in rows]

    # MIN over the WHOLE table, not just analysis_status='pending' -- the
    # interleaved_by_year strategy deliberately puts each year's earliest
    # game at the very front (queue_order 0, 1, 2, ...), which is exactly
    # what worker.py processes first, so the lowest queue_order values
    # belong to already-done games, not pending ones. Using only the
    # pending minimum here produced real duplicate queue_order values
    # against those low-numbered done games on the first real sync run --
    # caught by checking for duplicates after the fact, not assumed safe.
    min_overall = conn.execute("SELECT MIN(queue_order) FROM games").fetchone()[0]
    start = (min_overall - len(ordered_ids)) if min_overall is not None else 0

    for offset, gid in enumerate(ordered_ids):
        conn.execute("UPDATE games SET queue_order = ? WHERE id = ?", (start + offset, gid))
    conn.commit()


def run(db_path, player_name, queue_strategy, berserk_max_fraction, variant_policy, timeout_seconds,
        max_games=None):
    conn = get_connection(db_path)
    since_ms = compute_since_ms(conn)
    existing_queue_orders = dict(conn.execute("SELECT id, queue_order FROM games").fetchall())
    conn.close()

    if since_ms is None:
        scope = f"the most recent {max_games} games" if max_games else "full history"
        print(f"No games in the database yet -- fetching {scope}.")
    else:
        since_dt = datetime.datetime.fromtimestamp(since_ms / 1000, tz=datetime.timezone.utc)
        print(f"Fetching games since {since_dt.isoformat()} (inclusive -- the most recently "
              f"known game will be harmlessly re-fetched).")

    pgn_path = fetch_new_games_pgn(player_name, since_ms, timeout_seconds, max_games=max_games)
    if pgn_path is None:
        print("No new games found.")
        return

    try:
        n, skipped_variants, skipped_no_id, skipped_not_player, skipped_errors, \
            suspicious_zero_ply_games, inserted_ids = ingest(
                pgn_path, db_path, player_name, variant_policy, queue_strategy,
                berserk_max_fraction, requeue=False)
    finally:
        os.unlink(pgn_path)

    truly_new_ids = [gid for gid in inserted_ids if gid not in existing_queue_orders]

    # Games that already existed (re-fetched harmlessly at the sync boundary)
    # get INSERT OR REPLACE-d by ingest() above, which doesn't list queue_order
    # in its column list -- SQLite's INSERT OR REPLACE deletes the old row and
    # inserts a new one, so any unlisted column resets to its schema default
    # (NULL here), silently losing that game's place in the historical queue
    # ordering. Restore it explicitly rather than let that happen every sync.
    conn = get_connection(db_path)
    for gid in inserted_ids:
        if gid in existing_queue_orders and existing_queue_orders[gid] is not None:
            conn.execute("UPDATE games SET queue_order = ? WHERE id = ?",
                         (existing_queue_orders[gid], gid))
    bump_new_games_to_front_of_queue(conn, truly_new_ids)
    conn.commit()
    conn.close()

    try:
        achievements_conn = get_connection(db_path)
        achievements.evaluate(achievements_conn, "sync")
        achievements_conn.close()
    except Exception as e:
        print(f"WARNING: achievement evaluation failed (sync unaffected): {e}")

    print(f"Synced {n} game(s) ({len(truly_new_ids)} genuinely new, "
          f"{n - len(truly_new_ids)} already-known re-fetched at the sync boundary).")
    if truly_new_ids:
        print(f"New games queued ahead of the historical backlog: {truly_new_ids}")
    if skipped_variants:
        verb = "Included" if variant_policy == "include" else "Skipped"
        print(f"{verb} {sum(skipped_variants.values())} non-Standard-variant game(s): "
              f"{dict(skipped_variants)}")
    if skipped_no_id:
        print(f"Skipped {skipped_no_id} game(s) with no parseable game id.")
    if skipped_not_player:
        print(f"Skipped {skipped_not_player} game(s) not involving '{player_name}'.")
    if skipped_errors:
        print(f"{len(skipped_errors)} game(s) failed to (re-)ingest -- expected for "
              f"already-analyzed games re-fetched at the sync boundary (their analysis is "
              f"untouched). Game ids: {[gid for gid, _ in skipped_errors]}")
    if suspicious_zero_ply_games:
        print(f"FLAGGED {len(suspicious_zero_ply_games)} suspicious 0-ply game(s) for manual "
              f"review: {suspicious_zero_ply_games}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--player", default=None)
    ap.add_argument("--variant-policy", choices=["skip", "include"], default=None)
    ap.add_argument("--queue-strategy",
                     choices=["interleaved_by_year", "chronological", "reverse_chronological"],
                     default=None,
                     help="Only affects historical backlog re-sorting if ingest.py is also run "
                          "by hand -- sync.py always bumps its own newly-synced games to the "
                          "front of the queue regardless of this setting.")
    ap.add_argument("--berserk-max-clock-fraction", type=float, default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    player = pick(args.player, cfg["player"]["name"])
    variant_policy = pick(args.variant_policy, cfg["ingestion"]["variant_policy"])
    queue_strategy = pick(args.queue_strategy, cfg["ingestion"]["queue_strategy"])
    berserk_max_fraction = pick(args.berserk_max_clock_fraction,
                                 cfg["ingestion"]["berserk_max_clock_fraction"])
    timeout_seconds = cfg["sync"]["request_timeout_seconds"]

    run(db_path, player, queue_strategy, berserk_max_fraction, variant_policy, timeout_seconds)
