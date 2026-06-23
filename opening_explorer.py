#!/usr/bin/env python3
"""
Phase 4b (slice 2): Opening-tree explorer.

Browse your repertoire one ply at a time, via zobrist_hash transpositions
(not raw SAN-prefix matching, so two different move orders reaching the
same position are correctly merged into one tree node). No engine
analysis needed for the core counts/win-rates -- only the per-branch ACPL
enrichment is limited to currently-analyzed games.

A node is identified by (zobrist_hash, ply) together -- the same position
reached at a different move-count is treated as a different node, by
design (avoids conflating an opening transposition with an unrelated
later-game repetition).

Usage:
    python3 opening_explorer.py --color white                  # root: 1st-move branches
    python3 opening_explorer.py --color white --moves e4 e5    # branches after 1.e4 e5
"""
import argparse
from collections import Counter

import chess

from db import get_connection
from config import load_config, pick
from chess_utils import signed_zobrist


def count_games_ended_here(conn, color, target_num_plies, target_hash):
    """Games that ended with exactly target_num_plies moves can't appear in
    a ply=(target_num_plies+1) branches query (no such row exists), but
    they still legitimately "reached" this node if it's where they ended.
    target_hash=None (root, target_num_plies=0) always matches trivially --
    every game starts at the same unique position, no replay needed.
    Otherwise, candidates are filtered by exact ply count first, then each
    one's actual move sequence is replayed to confirm it truly reaches
    target_hash (same ply count alone doesn't guarantee the same position --
    a different, equally-short game could coincidentally have the same length)."""
    candidates = conn.execute(
        "SELECT id FROM games WHERE player_color=? AND num_plies=?",
        (color, target_num_plies)
    ).fetchall()
    if target_hash is None:
        return len(candidates)

    count = 0
    for (game_id,) in candidates:
        sans = conn.execute(
            "SELECT san FROM moves WHERE game_id=? ORDER BY ply", (game_id,)
        ).fetchall()
        board = chess.Board()
        try:
            for (san,) in sans:
                board.push_san(san)
        except ValueError:
            continue  # shouldn't happen for real ingested games; skip defensively
        if signed_zobrist(board) == target_hash:
            count += 1
    return count


def resolve_node(conn, color, path):
    """Returns (target_hash, target_ply, n_games_continuing, n_ended_here).
    target_hash is None for the root (path empty). n_ended_here is games
    that reached this exact node but had no further moves (abandoned/
    forfeit, or simply the game's last move) -- they can't appear in any
    branch below, since branching requires a next move that doesn't exist."""
    if not path:
        target_hash, target_ply = None, 1
    else:
        board = chess.Board()
        for san in path:
            try:
                move = board.parse_san(san)
            except ValueError:
                raise ValueError(f"'{san}' is not a legal move after {' '.join(path[:path.index(san)])}".strip())
            board.push(move)
        target_hash = signed_zobrist(board)
        target_ply = len(path) + 1

    if target_hash is None:
        n_continuing = conn.execute(
            "SELECT COUNT(*) FROM games WHERE player_color=?", (color,)
        ).fetchone()[0]
    else:
        n_continuing = conn.execute("""
            SELECT COUNT(DISTINCT m.game_id) FROM moves m JOIN games g ON g.id = m.game_id
            WHERE g.player_color=? AND m.ply=? AND m.zobrist_hash=?
        """, (color, target_ply, target_hash)).fetchone()[0]

    n_ended_here = count_games_ended_here(conn, color, target_ply - 1, target_hash)
    if target_hash is None:
        n_continuing -= n_ended_here  # avoid double-counting the "all games" total

    return target_hash, target_ply, n_continuing, n_ended_here


def fetch_branches(conn, color, target_ply, target_hash):
    """Returns {san: [game_id, ...]} for every move played at target_ply
    among games of this color reaching target_hash (or, at the root,
    among ALL games of this color)."""
    if target_hash is None:
        rows = conn.execute("""
            SELECT m.san, m.game_id FROM moves m JOIN games g ON g.id = m.game_id
            WHERE g.player_color=? AND m.ply=1
        """, (color,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT m.san, m.game_id FROM moves m JOIN games g ON g.id = m.game_id
            WHERE g.player_color=? AND m.ply=? AND m.zobrist_hash=?
        """, (color, target_ply, target_hash)).fetchall()
    branches = {}
    for san, game_id in rows:
        branches.setdefault(san, []).append(game_id)
    return branches


def branch_stats(conn, game_ids, target_ply, is_players_move):
    """Returns (win, draw, loss, acpl, blunder_rate, n_analyzed, common_opening).
    acpl/blunder_rate/n_analyzed are None when this ply isn't the player's
    own move -- engine quality stats aren't applicable to the opponent's choice."""
    placeholders = ",".join("?" * len(game_ids))
    outcome_rows = conn.execute(
        f"SELECT outcome_for_player, opening_family FROM games WHERE id IN ({placeholders})",
        game_ids
    ).fetchall()
    outcomes = Counter(o for o, _ in outcome_rows)
    openings = Counter(o for _, o in outcome_rows if o)
    common_opening = openings.most_common(1)[0][0] if openings else None

    acpl = blunder_rate = n_analyzed = None
    if is_players_move:
        row = conn.execute(f"""
            SELECT COUNT(*), AVG(cpl),
                   100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*)
            FROM moves WHERE game_id IN ({placeholders}) AND ply=?
              AND is_player_move=1 AND cpl IS NOT NULL
        """, game_ids + [target_ply]).fetchone()
        n_analyzed, acpl, blunder_rate = row
        n_analyzed = n_analyzed or 0
        if n_analyzed == 0:
            acpl = blunder_rate = None

    return outcomes.get("win", 0), outcomes.get("draw", 0), outcomes.get("loss", 0), \
        acpl, blunder_rate, n_analyzed, common_opening


def run(db_path, cfg, color, path):
    conn = get_connection(db_path)
    min_sample_size = cfg["analytics"]["min_sample_size"]

    try:
        target_hash, target_ply, n_games, n_ended_here = resolve_node(conn, color, path)
    except ValueError as e:
        print(f"Invalid move sequence: {e}")
        conn.close()
        return

    label = " ".join(path) if path else "(start)"
    mover = "White" if target_ply % 2 == 1 else "Black"
    is_players_move = (mover == "White") == (color == "white")
    whose_move = "your move" if is_players_move else "opponent's reply"

    print(f"=== Position after: {label}  [color={color}] ===")
    print(f"  {n_games} game(s) continue past this position. Next: {whose_move} ({mover} to move).")
    if n_ended_here:
        print(f"  (+ {n_ended_here} game(s) that reached this exact position but had no "
              f"further moves -- abandoned/forfeit/game-ended-here, not shown in any branch below)")
    print()

    branches = fetch_branches(conn, color, target_ply, target_hash)
    if not branches:
        print("  No games go further from here.")
        conn.close()
        return

    rows = []
    for san, game_ids in branches.items():
        win, draw, loss, acpl, blunder_rate, n_analyzed, opening = branch_stats(
            conn, game_ids, target_ply, is_players_move)
        rows.append((san, len(game_ids), win, draw, loss, acpl, blunder_rate, n_analyzed, opening))
    rows.sort(key=lambda r: -r[1])

    for san, n, win, draw, loss, acpl, blunder_rate, n_analyzed, opening in rows:
        flag = " (small sample)" if n < min_sample_size else ""
        pct = lambda x: f"{100.0*x/n:4.0f}%"
        line = f"  {san:<8} {n:>4} games  W{pct(win)}/D{pct(draw)}/L{pct(loss)}"
        if acpl is not None:
            line += f"  ACPL={acpl:5.1f} blunder={blunder_rate:4.1f}% ({n_analyzed} analyzed)"
        if opening:
            line += f"  [{opening}]"
        print(line + flag)

    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--color", required=True, choices=["white", "black"])
    ap.add_argument("--moves", nargs="*", default=[], help="SAN move sequence from the start, e.g. e4 e5 Nf3")
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])

    run(db_path, cfg, args.color, args.moves)
