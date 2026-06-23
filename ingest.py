#!/usr/bin/env python3
"""
Phase 1 ingestion: PGN -> SQLite (structural data only, no engine analysis yet).

Usage:
    python3 ingest.py --pgn sample.pgn --db chess.db --player "your-lichess-username"
"""
import argparse
import sqlite3
import sys
import datetime
from collections import defaultdict, Counter

import chess
import chess.pgn

from migrate import migrate
from config import load_config, pick
from db import get_connection
from chess_utils import (material_signature, signed_zobrist, material_delta_for_move,
                          parse_clock_seconds, detect_berserk)

COMMIT_EVERY_N_GAMES = 500  # bounds how much re-parsing a crash/interrupt can cost on a big file


def parse_game_id(site_url: str):
    if not site_url:
        return None
    return site_url.rstrip("/").split("/")[-1]


def parse_time_control(tc_raw: str):
    """'300+0' -> (300, 0, 'blitz')"""
    if not tc_raw or "+" not in tc_raw:
        return None, None, None
    base_str, inc_str = tc_raw.split("+", 1)
    try:
        base = int(base_str)
        inc = int(inc_str)
    except ValueError:
        return None, None, None
    estimate = base + 40 * inc  # standard lichess estimated game duration
    if estimate < 30:
        cat = "ultrabullet"
    elif estimate < 180:
        cat = "bullet"
    elif estimate < 480:
        cat = "blitz"
    elif estimate < 1500:
        cat = "rapid"
    else:
        cat = "classical"
    return base, inc, cat


def normalize_opening_family(opening_raw: str):
    if not opening_raw:
        return None
    return opening_raw.split(":")[0].strip()


def safe_int(value):
    """Lichess PGN headers sometimes use '?' or '' for unknown/missing numeric
    fields (observed in the wild: BlackElo='?' for some bot/unrated-category
    opponents). Treat anything unparseable as missing rather than crashing
    a 30k-game ingestion over one bad header."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or value == "?":
        return None
    try:
        return int(value.replace("+", ""))
    except ValueError:
        return None


def piece_letter(piece_type):
    return {
        chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B",
        chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K",
    }.get(piece_type, "?")


def compute_queue_order(conn, strategy: str):
    """Assigns games.queue_order according to the configured strategy:
    - interleaved_by_year: round-robin across years (early sample = representative cross-section)
    - chronological: oldest first
    - reverse_chronological: newest first (prioritize "how am I playing now")
    """
    if strategy == "chronological":
        rows = conn.execute("SELECT id FROM games ORDER BY utc_date, utc_time").fetchall()
        ordered_ids = [r[0] for r in rows]
    elif strategy == "reverse_chronological":
        rows = conn.execute("SELECT id FROM games ORDER BY utc_date DESC, utc_time DESC").fetchall()
        ordered_ids = [r[0] for r in rows]
    elif strategy == "interleaved_by_year":
        by_year = defaultdict(list)
        cur = conn.execute("SELECT id, year, utc_date, utc_time FROM games ORDER BY utc_date, utc_time")
        for gid, yr, *_ in cur.fetchall():
            by_year[yr].append(gid)
        ordered_ids = []
        queues = {yr: list(ids) for yr, ids in by_year.items()}
        while any(queues.values()):
            for yr in sorted(queues.keys(), key=lambda y: (y is None, y)):
                if queues[yr]:
                    ordered_ids.append(queues[yr].pop(0))
    else:
        raise ValueError(f"Unknown queue_strategy: {strategy!r}")

    for order, gid in enumerate(ordered_ids):
        conn.execute("UPDATE games SET queue_order = ? WHERE id = ?", (order, gid))
    conn.commit()


def process_one_game(game, game_id, white, black, player_name, variant_policy, conn,
                      berserk_max_fraction):
    """Parses and stores a single already-identified game. Returns
    'inserted', or 'skipped_variant' if it was a non-Standard variant
    skipped per policy. Raises on any unexpected/unforeseen data issue --
    the caller decides whether to isolate that failure to this one game."""
    h = game.headers

    variant = h.get("Variant", "Standard")
    if variant != "Standard":
        if variant_policy == "skip":
            # python-chess / Stockfish assume standard rules; analyzing a
            # Chess960/Atomic/Crazyhouse game as if it were standard would
            # silently produce garbage evals rather than an obvious error.
            return "skipped_variant", variant
        # else variant_policy == "include": fall through and ingest it.
        # NOTE: worker.py will still hand it to standard Stockfish unless
        # you configure a variant-aware engine separately -- "include"
        # is for visibility/storage, not a claim that analysis will be correct.

    player_color = "white" if white == player_name else "black"
    opponent_name = black if player_color == "white" else white
    white_elo = safe_int(h.get("WhiteElo"))
    black_elo = safe_int(h.get("BlackElo"))
    player_rating = white_elo if player_color == "white" else black_elo
    opponent_rating = black_elo if player_color == "white" else white_elo
    rating_diff = (player_rating - opponent_rating) if (
        player_rating is not None and opponent_rating is not None) else None

    white_rating_diff = safe_int(h.get("WhiteRatingDiff"))
    black_rating_diff = safe_int(h.get("BlackRatingDiff"))
    player_rating_change = white_rating_diff if player_color == "white" else black_rating_diff

    result = h.get("Result", "")
    if result == "1/2-1/2":
        outcome_for_player = "draw"
    elif (result == "1-0" and player_color == "white") or (result == "0-1" and player_color == "black"):
        outcome_for_player = "win"
    elif result in ("1-0", "0-1"):
        outcome_for_player = "loss"
    else:
        outcome_for_player = None

    utc_date = h.get("UTCDate", "")
    utc_time = h.get("UTCTime", "")
    year = month = day_of_week = hour_utc = None
    if utc_date:
        try:
            d = datetime.datetime.strptime(utc_date, "%Y.%m.%d")
            year, month, day_of_week = d.year, d.month, d.weekday()
        except ValueError:
            pass
    if utc_time:
        try:
            hour_utc = int(utc_time.split(":")[0])
        except ValueError:
            pass

    base_seconds, increment_seconds, tc_category = parse_time_control(h.get("TimeControl", ""))
    opening_family = normalize_opening_family(h.get("Opening", ""))

    # Berserk (lichess arena tournaments): halves a color's starting
    # clock, cancels their increment for the rest of that game. No PGN
    # tag for this -- derived from each color's first %clk reading vs
    # base_seconds (chess_utils.detect_berserk), validated against real
    # data (see migrations/0014). Must run BEFORE the move-walking loop:
    # ply 1's time_spent calculation needs the correct starting-clock
    # baseline already known, not discovered partway through.
    white_berserk, black_berserk = detect_berserk(game, base_seconds, berserk_max_fraction)
    berserk_by_color = {"w": white_berserk, "b": black_berserk}

    # --- walk the moves ---
    board = game.board()
    last_clock = {
        "w": (base_seconds // 2 if white_berserk else base_seconds) if base_seconds is not None else None,
        "b": (base_seconds // 2 if black_berserk else base_seconds) if base_seconds is not None else None,
    }
    move_rows = []
    ply = 0
    for node in game.mainline():
        move = node.move
        ply += 1
        move_number = (ply + 1) // 2
        color = "w" if board.turn == chess.WHITE else "b"

        piece = board.piece_at(move.from_square)
        is_capture = board.is_capture(move)
        is_castle = board.is_castling(move)
        is_promotion = move.promotion is not None
        is_check = board.gives_check(move)
        san = board.san(move)

        # Position-identity fields: derivable purely from board state, no
        # engine needed -- computed here (not worker.py) so they're
        # available for ALL games immediately, not gated behind however
        # much of the multi-week engine queue has completed so far.
        fen_before = board.fen()
        zobrist_hash = signed_zobrist(board)
        material_sig = material_signature(board)
        is_player_move = int(color == player_color[0])
        material_delta = material_delta_for_move(board, move)

        clock_seconds = parse_clock_seconds(node.comment)
        time_spent = None
        if clock_seconds is not None and last_clock[color] is not None:
            inc = 0 if berserk_by_color[color] else (increment_seconds or 0)
            time_spent = last_clock[color] - clock_seconds + inc
        if clock_seconds is not None:
            last_clock[color] = clock_seconds

        move_rows.append((
            game_id, ply, move_number, color, san, move.uci(),
            chess.square_name(move.from_square), chess.square_name(move.to_square),
            piece_letter(piece.piece_type) if piece else None,
            int(is_capture), int(is_check), int(is_castle), int(is_promotion),
            clock_seconds, time_spent,
            fen_before, zobrist_hash, material_sig, is_player_move, material_delta,
        ))
        board.push(move)

    num_plies = ply

    # game_end_type: derived from the final position, no engine needed.
    # Termination only gives coarse buckets (Normal/Time forfeit/Abandoned);
    # this fills in what actually happened within "Normal".
    termination = h.get("Termination", "")
    if termination == "Time forfeit":
        game_end_type = "time_forfeit"
    elif termination == "Abandoned":
        game_end_type = "abandoned"
    elif num_plies == 0:
        game_end_type = "unknown"
    elif board.is_checkmate():
        game_end_type = "checkmate"
    elif board.is_stalemate():
        game_end_type = "stalemate"
    elif board.is_insufficient_material():
        game_end_type = "insufficient_material"
    elif result == "1/2-1/2" and board.can_claim_fifty_moves():
        game_end_type = "draw_50_move_rule"
    elif result == "1/2-1/2" and board.is_repetition(3):
        game_end_type = "draw_repetition"
    elif result == "1/2-1/2":
        game_end_type = "draw_agreement"
    elif result in ("1-0", "0-1"):
        game_end_type = "resignation"
    else:
        game_end_type = "unknown"

    # A 0-ply game is legitimate when it's a genuine pre-move abort
    # (Termination="Abandoned") -- lichess produces these for real. It's
    # only suspicious when Termination claims something else (e.g. "Normal"
    # with a decisive result) yet no moves were parsed, since that's exactly
    # the silent-corruption failure mode found during testing: python-chess
    # can parse broken movetext leniently into an empty game with no error.
    # Flagged for manual review rather than skipped outright, since rejecting
    # a real 0-ply abort would lose legitimate data.
    suspicious_zero_ply = num_plies == 0 and termination != "Abandoned"
    if suspicious_zero_ply:
        print(f"  WARNING: game {game_id} has 0 plies but Termination={termination!r} "
              f"(not 'Abandoned') -- possibly corrupted movetext parsed as empty. "
              f"Inserted as-is; review manually.", file=sys.stderr)

    conn.execute("""
        INSERT OR REPLACE INTO games (
            id, event, site, pgn_raw, white, black, result,
            white_elo, black_elo, white_rating_diff, black_rating_diff,
            variant, time_control_raw, eco, opening_raw, termination,
            utc_date, utc_time, year, month, day_of_week, hour_utc,
            base_seconds, increment_seconds, time_control_category,
            opening_family, player_color, player_rating, opponent_rating,
            opponent_name, rating_diff, player_rating_change, outcome_for_player,
            num_plies, game_end_type, white_berserk, black_berserk
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        game_id, h.get("Event"), h.get("Site"), str(game),
        white, black, result, white_elo, black_elo,
        white_rating_diff, black_rating_diff,
        h.get("Variant"), h.get("TimeControl"), h.get("ECO"), h.get("Opening"), h.get("Termination"),
        utc_date, utc_time, year, month, day_of_week, hour_utc,
        base_seconds, increment_seconds, tc_category,
        opening_family, player_color, player_rating, opponent_rating,
        opponent_name, rating_diff, player_rating_change, outcome_for_player,
        num_plies, game_end_type,
        None if white_berserk is None else int(white_berserk),
        None if black_berserk is None else int(black_berserk),
    ))

    conn.execute("DELETE FROM moves WHERE game_id = ?", (game_id,))
    conn.executemany("""
        INSERT INTO moves (
            game_id, ply, move_number, color, san, uci, from_square, to_square,
            piece, is_capture, is_check, is_castle, is_promotion,
            clock_seconds, time_spent_seconds,
            fen_before, zobrist_hash, material_sig, is_player_move, material_delta
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, move_rows)

    return "inserted", (year, suspicious_zero_ply)


def ingest(pgn_path: str, db_path: str, player_name: str, variant_policy: str = "skip",
           queue_strategy: str = "interleaved_by_year", berserk_max_fraction: float = 0.75,
           requeue: bool = True):
    migrate(db_path)  # ensures all migrations are applied before we touch the db
    conn = get_connection(db_path)

    games_inserted = []  # (game_id, year) for queue_order computation afterward
    skipped_variants = Counter()
    skipped_no_id = 0
    skipped_not_player = 0
    skipped_errors = []  # (game_id_or_unknown, exception) -- isolated, doesn't kill the run
    suspicious_zero_ply_games = []  # 0-ply but Termination isn't "Abandoned" -- inserted, flagged for review

    with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
        games_seen = 0
        # Explicit outer transaction: without it, RELEASE-ing the per-game
        # SAVEPOINT below would itself be the statement that opened the
        # transaction (since SAVEPOINT outside an active transaction starts
        # one implicitly) -- and RELEASE-ing the outermost savepoint commits
        # that transaction to disk immediately. Confirmed by test: that
        # silently committed after every single game, defeating
        # COMMIT_EVERY_N_GAMES batching entirely. Wrapping in our own BEGIN
        # makes the per-game SAVEPOINT a true nested sub-transaction that
        # only the periodic conn.commit() below actually flushes.
        conn.execute("BEGIN")
        while True:
            game = chess.pgn.read_game(pgn_file)
            if game is None:
                break

            h = game.headers
            game_id = parse_game_id(h.get("Site", ""))
            if not game_id:
                skipped_no_id += 1
                continue  # skip malformed entries rather than crash a 30k-game run

            white, black = h.get("White", ""), h.get("Black", "")
            if player_name not in (white, black):
                skipped_not_player += 1
                continue  # defensive: only keep games the target player is actually in

            # SAVEPOINT scopes rollback to just this one game's writes -- a
            # plain conn.rollback() would also discard every other game
            # processed since the last periodic commit, not just the failing
            # one. Confirmed by test: without this, a failure between
            # process_one_game's games INSERT and its moves INSERT left a
            # half-written "ghost" games row (with no moves) that got
            # silently committed at the next periodic commit.
            conn.execute("SAVEPOINT game_save")
            try:
                status, info = process_one_game(game, game_id, white, black,
                                                 player_name, variant_policy, conn,
                                                 berserk_max_fraction)
            except Exception as e:
                # One unforeseen bad header/move shouldn't cost you the whole
                # file -- log it, skip that one game, keep going. (This is
                # exactly the class of bug that crashed the original run.)
                conn.execute("ROLLBACK TO game_save")
                conn.execute("RELEASE game_save")
                skipped_errors.append((game_id, repr(e)))
                print(f"  WARNING: skipped game {game_id} due to error: {e}", file=sys.stderr)
                continue
            conn.execute("RELEASE game_save")

            if status == "skipped_variant":
                skipped_variants[info] += 1
                continue

            year, suspicious_zero_ply = info
            if suspicious_zero_ply:
                suspicious_zero_ply_games.append(game_id)
            games_inserted.append((game_id, year))

            games_seen += 1
            if games_seen % COMMIT_EVERY_N_GAMES == 0:
                conn.commit()  # bounds how much re-parsing a later crash/interrupt can cost
                conn.execute("BEGIN")  # re-open for the next batch of games
                print(f"  ...{games_seen} games processed so far")

    conn.commit()

    # --- compute queue_order per the configured strategy ---
    # requeue=False is for callers (sync.py) that want their own queue
    # placement for just the newly-inserted games, rather than a full
    # table-wide re-sort by the configured strategy -- e.g. bumping new
    # games ahead of the historical backlog instead of re-interleaving
    # them by year alongside it.
    if requeue:
        compute_queue_order(conn, queue_strategy)
    conn.close()
    return (len(games_inserted), skipped_variants, skipped_no_id, skipped_not_player,
            skipped_errors, suspicious_zero_ply_games, [gid for gid, _year in games_inserted])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--player", default=None)
    ap.add_argument("--variant-policy", choices=["skip", "include"], default=None)
    ap.add_argument("--queue-strategy",
                     choices=["interleaved_by_year", "chronological", "reverse_chronological"],
                     default=None)
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

    n, skipped_variants, skipped_no_id, skipped_not_player, skipped_errors, suspicious_zero_ply_games, _inserted_ids = ingest(
        args.pgn, db_path, player, variant_policy, queue_strategy, berserk_max_fraction)
    print(f"Ingested {n} games into {db_path}")
    if skipped_variants:
        verb = "Included" if variant_policy == "include" else "Skipped"
        print(f"{verb} {sum(skipped_variants.values())} non-Standard-variant game(s): "
              f"{dict(skipped_variants)}")
    if skipped_no_id:
        print(f"Skipped {skipped_no_id} game(s) with no parseable game id.")
    if skipped_not_player:
        print(f"Skipped {skipped_not_player} game(s) not involving '{player}'.")
    if skipped_errors:
        print(f"Skipped {len(skipped_errors)} game(s) due to unexpected errors -- "
              f"see warnings above for details. Game ids: "
              f"{[gid for gid, _ in skipped_errors][:20]}{'...' if len(skipped_errors) > 20 else ''}")
    if suspicious_zero_ply_games:
        print(f"Inserted but FLAGGED {len(suspicious_zero_ply_games)} suspicious 0-ply game(s) "
              f"(Termination wasn't 'Abandoned') -- review manually. Game ids: "
              f"{suspicious_zero_ply_games[:20]}{'...' if len(suspicious_zero_ply_games) > 20 else ''}")
