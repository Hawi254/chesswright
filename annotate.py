#!/usr/bin/env python3
"""
Phase 3a: Annotation pass -- CPL, win probability, move classification.

Pure post-processing over already-stored Stockfish evals (eval_cp/eval_mate
written by worker.py). No engine re-run. Fully recomputable any time --
re-running this script after editing thresholds in config.yaml, or after
worker.py analyzes more plies, just overwrites cpl/classification/
win_prob_before/win_prob_after with fresh values.

Eval perspective reminder (see CLAUDE.md / worker.py docstring): eval_cp/
eval_mate at ply i are from the POV of whoever is ABOUT TO MOVE at ply i.
Ply i and ply i+1 are from opposite POVs (movers alternate), so comparing
them requires flipping one side's sign -- that flip happens in
mover_pov_after(), nowhere else.

Usage:
    python3 annotate.py                       # annotate every eligible game
    python3 annotate.py --game-id abc123       # one game (debugging)
    python3 annotate.py --mate-cap 1500         # override config.yaml for one run
"""
import argparse
import math
import sys

from migrate import migrate
from db import get_connection
from config import load_config, pick
from motif import classify_motif


def cp_equivalent(eval_cp, eval_mate, mate_cap):
    """Collapse (eval_cp, eval_mate) into a single comparable cp number."""
    if eval_mate is not None:
        return mate_cap if eval_mate > 0 else -mate_cap
    return eval_cp


def mover_pov_after(next_eval_cp, next_eval_mate):
    """Flips ply i+1's stored data (opponent's POV) into mover M's POV.
    Both cp and mate sign flip together here, in one place, so the two
    can never disagree about whose perspective they're in."""
    after_cp = None if next_eval_cp is None else -next_eval_cp
    after_mate = None if next_eval_mate is None else -next_eval_mate
    return after_cp, after_mate


def win_prob(cp, eval_mate):
    """Lichess win% formula. Mate scores saturate to 0.0/1.0 directly."""
    if eval_mate is not None:
        return 1.0 if eval_mate > 0 else 0.0
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


def classify(win_drop, is_best_move, thresholds):
    """thresholds: dict with excellent/good/inaccuracy/mistake/blunder cutoffs
    (ascending win%-drop). best_move overrides win_drop-based classification."""
    if is_best_move:
        return "best"
    if win_drop <= thresholds["excellent"]:
        return "excellent"
    if win_drop <= thresholds["good"]:
        return "good"
    if win_drop <= thresholds["inaccuracy"]:
        return "inaccuracy"
    if win_drop <= thresholds["mistake"]:
        return "mistake"
    return "blunder"


def fetch_rank1_rank2(conn, move_ids):
    """Phase 3b: returns {move_id: (rank1_row, rank2_row_or_None)} where each
    row is (eval_cp, eval_mate). Both rows for one move_id come from the same
    search call/POV -- no perspective flip needed here, unlike CPL."""
    if not move_ids:
        return {}
    placeholders = ",".join("?" * len(move_ids))
    rows = conn.execute(f"""
        SELECT move_id, pv_rank, eval_cp, eval_mate FROM move_lines
        WHERE move_id IN ({placeholders}) AND pv_rank IN (1, 2)
    """, move_ids).fetchall()
    by_move = {}
    for move_id, pv_rank, eval_cp, eval_mate in rows:
        by_move.setdefault(move_id, {})[pv_rank] = (eval_cp, eval_mate)
    return {mid: (ranks.get(1), ranks.get(2)) for mid, ranks in by_move.items()}


def sharpness_for(rank1, rank2, mate_cap):
    """NULL (None) when there's no rank=2 line (only one legal move) --
    that's "no second-best line exists", not "the second-best is tied"."""
    if rank1 is None or rank2 is None:
        return None
    rank1_cp, rank1_mate = rank1
    rank2_cp, rank2_mate = rank2
    gap = cp_equivalent(rank1_cp, rank1_mate, mate_cap) - cp_equivalent(rank2_cp, rank2_mate, mate_cap)
    return max(0, gap)


def detect_puzzle_sequence(computed_classification, start_idx, accurate_classifications):
    """Walks forward from start_idx in steps of 2 (the SAME mover's plies --
    O's own consecutive moves, skipping M's interleaved replies), counting
    how many are classified accurately in a row. Stops at the first gap
    (no fresh classification this run), non-qualifying classification, or
    running off the end of computed_classification.

    Reads ONLY from computed_classification (this run's freshly computed
    values), never from the stale pre-run `rows` snapshot -- otherwise a
    threshold retune wouldn't actually change puzzle detection on a
    re-run, silently breaking idempotency-under-retuning the same way a
    one-pass loop using not-yet-updated values would."""
    length = 0
    idx = start_idx
    while True:
        cls = computed_classification.get(idx)
        if cls is None or cls not in accurate_classifications:
            break
        length += 1
        idx += 2
    return length


def detect_best_move_streaks(rows, sharpness_by_idx, streak_cfg):
    """Best-move streaks: the player matching the engine's literal top move
    (san=best_move_san) for consecutive own turns. Only needs san/
    best_move_san (available the moment THIS ply is analyzed) and sharpness
    (same-ply, from move_lines) -- unlike cpl/classification, it does NOT
    need the next ply analyzed, so it gets computed independently of pass 1
    rather than gated behind it.

    Walks the player's own analyzed turns directly (pre-filtered to
    is_player_move=1 with a known best_move_san) -- opponent plies are
    already absent from this list, not stepped-over the way
    detect_puzzle_sequence steps by 2 through an interleaved list.

    One row per streak, anchored at its FIRST ply (mirrors
    puzzle_sequence_length's one-row-per-sequence convention) -- every
    other ply within the streak gets (0, 0, 0), the run's length/trigger/
    unforced-count is only ever recorded at the start.

    A streak only qualifies as is_best_move_streak_trigger=1 if its FIRST
    move was itself "unforced" (competitive margin -- moves.sharpness read
    inverted: small gap means several moves were genuinely close in
    quality, so finding the best one was a real choice). Later moves in
    the streak don't have to be unforced -- best_move_streak_unforced_count
    records how many of them were, for a stronger "every move was a real
    choice" signal on top of the qualifying minimum of 1."""
    own_idxs = [idx for idx, row in enumerate(rows) if row[9] and row[5] is not None]
    max_cp = streak_cfg["unforced_competitive_margin_max_cp"]

    def is_unforced(idx):
        s = sharpness_by_idx.get(idx)
        return s is not None and s < max_cp

    results = {}
    i = 0
    while i < len(own_idxs):
        idx = own_idxs[i]
        san, best_move_san = rows[idx][2], rows[idx][5]
        if san != best_move_san:
            results[idx] = (0, 0, 0)
            i += 1
            continue

        run_idxs = [idx]
        j = i + 1
        while j < len(own_idxs) and rows[own_idxs[j]][2] == rows[own_idxs[j]][5]:
            run_idxs.append(own_idxs[j])
            j += 1

        length = len(run_idxs)
        unforced_count = sum(1 for k in run_idxs if is_unforced(k))
        is_trigger = int(is_unforced(idx) and length >= streak_cfg["min_streak_length"])
        results[idx] = (length, is_trigger, unforced_count)
        for k in run_idxs[1:]:
            results[k] = (0, 0, 0)
        i = j
    return results


def annotate_game(conn, game_id, mate_cap, thresholds, brilliant_threshold, puzzle_cfg, streak_cfg):
    """Recomputes cpl/classification/win_prob_before/win_prob_after/sharpness/
    is_brilliant_candidate/is_puzzle_trigger/puzzle_sequence_length/
    best_move_streak_length/is_best_move_streak_trigger/
    best_move_streak_unforced_count for every ply in this game with enough
    data. Idempotent -- safe to re-run after threshold tuning or partial
    re-analysis."""
    rows = conn.execute("""
        SELECT id, ply, san, eval_cp, eval_mate, best_move_san, material_delta,
               to_square, is_capture, is_player_move, fen_before
        FROM moves WHERE game_id=? ORDER BY ply
    """, (game_id,)).fetchall()

    rank_lines = fetch_rank1_rank2(conn, [r[0] for r in rows])

    # sharpness depends only on this ply's own move_lines -- compute it for
    # every analyzed ply, independent of whether the NEXT ply (needed for
    # cpl/classification/brilliant-flag below) has been analyzed yet.
    # Keyed by idx (not move_id) and read non-destructively (.get(), never
    # popped) -- best-move-streak detection below needs every analyzed
    # ply's sharpness too, not just the ones pass 1 ends up updating.
    sharpness_by_idx = {}
    for idx, row in enumerate(rows):
        move_id, _ply, _san, eval_cp, eval_mate, _best, _mat_delta, _to_sq, _is_cap, _ipm = row
        if eval_cp is None and eval_mate is None:
            continue  # not analyzed -- no move_lines exist either
        rank1, rank2 = rank_lines.get(move_id, (None, None))
        sharpness_by_idx[idx] = sharpness_for(rank1, rank2, mate_cap)
    sharpness_updates = dict(sharpness_by_idx)  # idx -> sharpness, consumed (popped) by pass 1 below

    # Pass 1: cpl/classification/win_prob/sharpness/brilliant-flag, exactly
    # as before. computed_classification[idx] caches each idx's freshly
    # computed classification for pass 2 below (puzzle detection needs to
    # look AHEAD at idx+1, idx+3, ... which pass 1 hasn't reached yet in a
    # single forward loop -- and must use THIS run's fresh values, not a
    # stale pre-run read, or a threshold retune wouldn't change detection
    # on a re-run).
    row_by_idx = {}
    computed_classification = {}
    for idx in range(len(rows) - 1):  # last ply has no "after" row -- left NULL
        (move_id, _ply, san, eval_cp, eval_mate, best_move_san, material_delta,
         to_square, _is_capture, _is_player_move) = rows[idx]
        next_material_delta = rows[idx + 1][6]
        next_eval_cp, next_eval_mate = rows[idx + 1][3], rows[idx + 1][4]
        next_to_square, next_is_capture = rows[idx + 1][7], rows[idx + 1][8]

        if eval_cp is None and eval_mate is None:
            continue  # this ply not yet analyzed
        if next_eval_cp is None and next_eval_mate is None:
            continue  # next ply not yet analyzed -- can't compare yet

        before_cp = cp_equivalent(eval_cp, eval_mate, mate_cap)
        after_m_cp, after_m_mate = mover_pov_after(next_eval_cp, next_eval_mate)
        after_m_cp_equiv = cp_equivalent(after_m_cp, after_m_mate, mate_cap)

        cpl = max(0, before_cp - after_m_cp_equiv)

        wp_before = win_prob(before_cp, eval_mate)
        wp_after = win_prob(after_m_cp, after_m_mate)
        win_drop = wp_before - wp_after

        is_best = (san == best_move_san)
        cls = classify(win_drop, is_best, thresholds)

        # Brilliant-candidate flag: a real sacrifice is invisible on THIS
        # ply's own material_delta (always >= 0) -- it shows up as the
        # OPPONENT's next-ply material_delta being large. Skip (don't
        # default to 0) when material_delta hasn't been backfilled yet,
        # same skip-on-NULL philosophy as the eval_cp/eval_mate checks above.
        #
        # Critically, the opponent's capture must land on the SAME square
        # this move just went to -- i.e. it's a recapture of the piece M
        # just placed there, not just any unrelated capture that happens to
        # occur on the very next ply. Without this check, a quiet move
        # followed by a coincidental, unrelated trade elsewhere on the board
        # was wrongly flagged (caught via manual review during verification:
        # 'h6' followed by 'Bxf6' on a totally different square).
        is_brilliant = None
        if material_delta is not None and next_material_delta is not None:
            is_brilliant = int(
                cls in ("best", "excellent")
                and bool(next_is_capture) and next_to_square == to_square
                and next_material_delta >= brilliant_threshold
                and material_delta < brilliant_threshold
            )

        sharpness = sharpness_updates.pop(idx, None)
        computed_classification[idx] = cls
        row_by_idx[idx] = [move_id, cpl, cls, wp_before, wp_after, sharpness, is_brilliant]

    # Pass 2: puzzle-candidate sequence detection -- must come AFTER pass 1
    # finishes, since it looks ahead at idx+1, idx+3, ...'s classification.
    for idx, cls in computed_classification.items():
        is_trigger = None
        seq_len = None
        if cls in puzzle_cfg["trigger_classifications"]:
            seq_len = detect_puzzle_sequence(
                computed_classification, idx + 1, puzzle_cfg["accurate_classifications"])
            is_trigger = int(seq_len >= puzzle_cfg["min_sequence_length"])
        else:
            seq_len = 0
            is_trigger = 0
        row_by_idx[idx].extend([is_trigger, seq_len])

    # Any leftover sharpness-only rows (this ply analyzed, but the next
    # ply isn't yet, so it never went through the pass-1 loop above) still
    # need their sharpness written -- the other columns stay untouched.
    sharpness_only_updates = [(sharpness, rows[idx][0]) for idx, sharpness in sharpness_updates.items()]

    updates = [(cpl, cls, wp_before, wp_after, sharpness, is_brilliant, is_trigger, seq_len, move_id)
               for move_id, cpl, cls, wp_before, wp_after, sharpness, is_brilliant, is_trigger, seq_len
               in row_by_idx.values()]

    conn.executemany("""
        UPDATE moves SET cpl=?, classification=?, win_prob_before=?, win_prob_after=?,
            sharpness=?, is_brilliant_candidate=?, is_puzzle_trigger=?, puzzle_sequence_length=?
        WHERE id=?
    """, updates)
    conn.executemany("UPDATE moves SET sharpness=? WHERE id=?", sharpness_only_updates)

    # Pass 3: best-move streaks -- independent of pass 1/2 (doesn't need
    # next-ply data), computed from sharpness_by_idx (the non-destructive
    # copy taken before pass 1 started popping sharpness_updates).
    streak_results = detect_best_move_streaks(rows, sharpness_by_idx, streak_cfg)
    streak_updates = [(length, is_trigger, unforced_count, rows[idx][0])
                       for idx, (length, is_trigger, unforced_count) in streak_results.items()]
    conn.executemany("""
        UPDATE moves SET best_move_streak_length=?, is_best_move_streak_trigger=?,
            best_move_streak_unforced_count=?
        WHERE id=?
    """, streak_updates)

    # Pass 4: tactical motif classification.
    # For each mistake/blunder where the player missed the best move and we
    # have the position (fen_before) to analyse, classify which tactical
    # idea the best move exploited. Uses python-chess only -- no engine
    # re-run. Safe to re-run idempotently (overwrites previous value).
    motif_updates = []
    for idx, cls in computed_classification.items():
        if cls not in ("mistake", "blunder"):
            continue
        move_id = rows[idx][0]
        san = rows[idx][2]
        best_move_san = rows[idx][5]
        fen_before = rows[idx][10]
        if not fen_before or not best_move_san or san == best_move_san:
            continue
        is_player_move = rows[idx][9]
        if not is_player_move:
            continue
        motif = classify_motif(fen_before, best_move_san)
        motif_updates.append((motif, move_id))
    if motif_updates:
        conn.executemany("UPDATE moves SET motif=? WHERE id=?", motif_updates)

    conn.commit()
    return len(updates)


def fetch_games_to_annotate(conn, game_id=None):
    if game_id:
        return conn.execute("SELECT id FROM games WHERE id=?", (game_id,)).fetchall()
    # any game with at least one analyzed ply is worth a pass --
    # annotate_game's internal NULL-skip handles partially-analyzed games
    return conn.execute("SELECT id FROM games WHERE last_analyzed_ply > 0").fetchall()


def count_games_awaiting_annotation(conn) -> int:
    """For the Analysis Jobs dashboard view's "K games awaiting
    annotation" notification -- NOT the same query as
    fetch_games_to_annotate() above. That one is deliberately broad (any
    previously-analyzed game, since annotate_game() is a cheap, idempotent
    full recompute, safe to re-run against everything every time) -- a
    notification needs to be narrow instead, or it would permanently read
    "K games awaiting annotation" for every game ever analyzed, since
    annotate.py has no separate "already annotated" marker column at all
    (confirmed by reading annotate_game(): it always recomputes cpl/
    classification/etc. for every eligible ply, every run).

    The real, narrow signal: a move with its own eval already written
    (worker.py's job) but no cpl yet (annotate.py's job) -- excluding each
    game's structurally LAST analyzed ply, which never gets a cpl by
    design (there's no "next ply" to diff against, see annotate_game()'s
    `range(len(rows) - 1)`), so it would otherwise read as a permanent
    false positive on every game ever analyzed."""
    row = conn.execute("""
        SELECT COUNT(DISTINCT m.game_id)
        FROM moves m
        JOIN games g ON g.id = m.game_id
        WHERE (m.eval_cp IS NOT NULL OR m.eval_mate IS NOT NULL)
          AND m.cpl IS NULL
          AND m.ply < g.num_plies
    """).fetchone()
    return row[0]


def run(db_path, mate_cap, thresholds, brilliant_threshold, puzzle_cfg, streak_cfg, game_id):
    migrate(db_path)
    conn = get_connection(db_path)
    games = fetch_games_to_annotate(conn, game_id)
    print(f"Annotating {len(games)} game(s)...")

    total_moves = 0
    failed = []
    for (gid,) in games:
        try:
            n = annotate_game(conn, gid, mate_cap, thresholds, brilliant_threshold, puzzle_cfg, streak_cfg)
            total_moves += n
        except Exception as e:
            # one bad game must never crash the batch -- same isolation
            # pattern as ingest.py's process_one_game
            failed.append((gid, repr(e)))
            print(f"  WARNING: failed to annotate game {gid}: {e}", file=sys.stderr)
            continue

    print(f"Done: {total_moves} move(s) annotated across {len(games) - len(failed)} game(s).")
    if failed:
        print(f"Skipped {len(failed)} game(s) due to errors -- see warnings above.", file=sys.stderr)
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--game-id", default=None, help="Annotate a single game (debugging)")
    ap.add_argument("--mate-cap", type=int, default=None)
    ap.add_argument("--brilliant-threshold", type=int, default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    mate_cap = pick(args.mate_cap, cfg["annotation"]["mate_score_cap_cp"])
    thresholds = cfg["annotation"]["thresholds"]
    brilliant_threshold = pick(args.brilliant_threshold, cfg["annotation"]["brilliant_material_threshold_cp"])
    puzzle_cfg = cfg["annotation"]["puzzle"]
    streak_cfg = cfg["annotation"]["best_move_streak"]

    run(db_path, mate_cap, thresholds, brilliant_threshold, puzzle_cfg, streak_cfg, args.game_id)
