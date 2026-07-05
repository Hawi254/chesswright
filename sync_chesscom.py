#!/usr/bin/env python3
"""
Incremental sync of games from chess.com's public PubAPI -- the chess.com
sibling of sync.py. See BRIEF.md's chess.com integration spec for the
research this is based on.

Usage:
    python3 sync_chesscom.py --db chess.db --player "your-chesscom-username"

Deliberately a separate script from sync.py, not a --platform flag on it:
chess.com's API shape is different enough (monthly archives, no single
"everything since X" streaming endpoint) that a shared implementation would
mostly be an if/else fork at every step. Both funnel into the same
ingest.py -- that's the actual shared core, not this fetch layer.
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
from sync import bump_new_games_to_front_of_queue

CHESSCOM_API_BASE = "https://api.chess.com/pub/player/{username}"
# Chess.com's own guidance: a descriptive User-Agent with contact info lets
# them reach out about suspicious activity instead of just blocking it.
# Points at the public repo rather than a personal email -- this is
# distributed code, not a one-off script run by its author only.
USER_AGENT = "Chesswright (+https://github.com/Hawi254/chesswright)"


def compute_since_month(conn):
    """Returns (year, month) to start fetching archives from (inclusive),
    or None if there are no chess.com games in the database yet (fetch
    every available archive).

    Chess.com's site column is always the literal string "Chess.com" for
    games from this platform (see chesscom_pgn.CHESSCOM_SITE_HEADER) --
    a reliable, already-present discriminator, so no new schema column is
    needed just to tell chess.com rows apart from lichess ones.

    Inclusive of the most-recently-known game's month, not that month+1:
    chess.com has no per-game "since" cursor the way lichess does, only
    whole monthly archives, so the cheapest correct approach is to always
    re-fetch the current-to-that-player known month in full (idempotent
    INSERT OR REPLACE, same as sync.py's own last-known-game re-fetch)
    rather than try to dedupe below month granularity.
    """
    row = conn.execute("""
        SELECT MAX(utc_date) FROM games
        WHERE site = 'Chess.com' AND utc_date IS NOT NULL AND utc_date != ''
    """).fetchone()
    if row is None or row[0] is None:
        return None
    d = datetime.datetime.strptime(row[0], "%Y.%m.%d")
    return d.year, d.month


def list_archive_months(player_name, timeout_seconds):
    """Returns a sorted list of (year, month) tuples for every monthly
    archive chess.com has for this player, oldest first."""
    url = CHESSCOM_API_BASE.format(username=player_name) + "/games/archives"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout_seconds)
    if resp.status_code == 404:
        raise ValueError(f"No chess.com account found for '{player_name}' -- check the spelling.")
    resp.raise_for_status()
    archives = resp.json().get("archives", [])
    months = []
    for archive_url in archives:
        # Each archive URL ends in .../games/{YYYY}/{MM}
        parts = archive_url.rstrip("/").split("/")
        year, month = int(parts[-2]), int(parts[-1])
        months.append((year, month))
    return sorted(months)


def fetch_month_pgn(player_name, year, month, timeout_seconds, variant_policy):
    """Fetches one monthly archive and returns its games as a single
    concatenated PGN blob (str), or None if that month had zero games (or
    zero after variant filtering).

    Filters out non-Standard games here using chess.com's own JSON "rules"
    field (values like "chess960", "bughouse", "kingofthehill") rather
    than relying on ingest.py's PGN-header-based Variant check -- it's
    unverified whether chess.com's exported PGN reliably sets a Variant
    tag the way lichess's does (flagged, not assumed, in BRIEF.md's
    integration spec), but the JSON "rules" field is always present and
    unambiguous.
    """
    url = CHESSCOM_API_BASE.format(username=player_name) + f"/games/{year:04d}/{month:02d}"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout_seconds)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    games = resp.json().get("games", [])

    pgns = []
    n_skipped_variant = 0
    for g in games:
        if g.get("rules", "chess") != "chess" and variant_policy == "skip":
            n_skipped_variant += 1
            continue
        pgn = g.get("pgn")
        if pgn:
            pgns.append(pgn)
    if n_skipped_variant:
        print(f"  {year:04d}-{month:02d}: skipped {n_skipped_variant} non-Standard-variant game(s)")
    if not pgns:
        return None
    return "\n\n".join(pgns)


def fetch_new_games_pgn(player_name, since_month, timeout_seconds, variant_policy, max_months=None):
    """Streams every in-scope monthly archive to a single temp file,
    sequentially (chess.com's own guidance: parallel requests risk 429),
    printing progress per month so a long first-time backfill never looks
    like a hang -- same standing rule sync.py's docstring states, applies
    doubly here since a chess.com backfill is one request per calendar
    month of account history, not one streaming request.

    Returns the temp file path (caller deletes it) or None if nothing was
    fetched at all."""
    months = list_archive_months(player_name, timeout_seconds)
    if since_month is not None:
        months = [m for m in months if m >= since_month]
    if max_months is not None:
        months = months[-max_months:]  # most recent N months, for onboarding calibration
    if not months:
        return None

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False, encoding="utf-8")
    n_months_with_games = 0
    try:
        for i, (year, month) in enumerate(months):
            pgn_blob = fetch_month_pgn(player_name, year, month, timeout_seconds, variant_policy)
            if pgn_blob:
                tmp.write(pgn_blob)
                tmp.write("\n\n")
                n_months_with_games += 1
            if (i + 1) % 6 == 0 or (i + 1) == len(months):
                print(f"  ...{i + 1}/{len(months)} month(s) checked so far")
    except BaseException:
        tmp.close()
        os.unlink(tmp.name)
        raise
    tmp.close()

    if n_months_with_games == 0:
        os.unlink(tmp.name)
        return None
    print(f"Download complete: {n_months_with_games} month(s) with games, out of {len(months)} checked.")
    return tmp.name


def run(db_path, player_name, queue_strategy, variant_policy, timeout_seconds, max_months=None):
    conn = get_connection(db_path)
    since_month = compute_since_month(conn)
    existing_queue_orders = dict(conn.execute("SELECT id, queue_order FROM games").fetchall())
    conn.close()

    if since_month is None:
        scope = f"the most recent {max_months} month(s)" if max_months else "full history"
        print(f"No chess.com games in the database yet -- fetching {scope}.")
    else:
        print(f"Fetching chess.com archives from {since_month[0]:04d}-{since_month[1]:02d} onward "
              f"(inclusive -- that month's already-known games will be harmlessly re-fetched).")

    try:
        pgn_path = fetch_new_games_pgn(player_name, since_month, timeout_seconds, variant_policy,
                                        max_months=max_months)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            print("Chess.com API returned 429 (rate limited) -- try again later.", file=sys.stderr)
            return
        raise
    if pgn_path is None:
        print("No new games found.")
        return

    try:
        # ingest.py's own skipped_variants counter is not surfaced here --
        # variant filtering already happened in fetch_month_pgn() against
        # chess.com's JSON "rules" field, the trustworthy signal (see its
        # docstring), so this is expected to stay empty for chess.com.
        n, _skipped_variants, skipped_no_id, skipped_not_player, skipped_errors, \
            suspicious_zero_ply_games, inserted_ids = ingest(
                pgn_path, db_path, player_name, variant_policy, queue_strategy,
                berserk_max_fraction=0.75,  # berserk doesn't exist on chess.com; value is inert here
                requeue=False)
    finally:
        os.unlink(pgn_path)

    truly_new_ids = [gid for gid in inserted_ids if gid not in existing_queue_orders]

    conn = get_connection(db_path)
    for gid in inserted_ids:
        if gid in existing_queue_orders and existing_queue_orders[gid] is not None:
            conn.execute("UPDATE games SET queue_order = ? WHERE id = ?",
                         (existing_queue_orders[gid], gid))
    bump_new_games_to_front_of_queue(conn, truly_new_ids)
    conn.commit()
    conn.close()

    print(f"Synced {n} game(s) ({len(truly_new_ids)} genuinely new, "
          f"{n - len(truly_new_ids)} already-known re-fetched at the sync boundary).")
    if truly_new_ids:
        print(f"New games queued ahead of the historical backlog: {truly_new_ids}")
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
    ap.add_argument("--player", default=None, help="chess.com username (default: config.yaml's "
                                                     "player.chesscom_username)")
    ap.add_argument("--variant-policy", choices=["skip", "include"], default=None)
    ap.add_argument("--queue-strategy",
                     choices=["interleaved_by_year", "chronological", "reverse_chronological"],
                     default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    player = pick(args.player, cfg["player"].get("chesscom_username"))
    if not player:
        sys.exit("No chess.com username given -- pass --player or set "
                 "player.chesscom_username in config.yaml.")
    variant_policy = pick(args.variant_policy, cfg["ingestion"]["variant_policy"])
    queue_strategy = pick(args.queue_strategy, cfg["ingestion"]["queue_strategy"])
    timeout_seconds = cfg["sync_chesscom"]["request_timeout_seconds"]

    run(db_path, player, queue_strategy, variant_policy, timeout_seconds)
