#!/usr/bin/env python3
"""
Lichess cloud-eval lookup for on-demand position analysis.

Lichess's /api/cloud-eval endpoint serves deep, crowd-sourced Stockfish
evaluations for positions many players have already looked up on
lichess.org -- strongly biased toward popular/opening positions, which
makes it a poor fit for the batch worker (which must evaluate every
position in a user's actual games, most of which are off-book by the
middlegame) but a good fit for live_engine.py's on-demand position
lookups, which are disproportionately used on repeated/opening positions.

Only ever sends a bare FEN -- no username, PGN, or game result -- and is
purely a nice-to-have UI enrichment: any failure (miss, rate limit,
timeout, network error) returns None so callers fall through to the
local engine, the same fail-quiet convention sync.py's fetch_new_games_pgn
already uses for lichess 429s.

Perspective gotcha (confirmed against Lichess's published OpenAPI spec):
cp/mate in the response are documented as "from White's point of view" --
the OPPOSITE of this codebase's own convention, where every eval field
(moves.eval_cp, position_cache.eval_cp, LiveResult.eval_cp) is from the
side-to-move's perspective (see worker.score_to_fields()'s
score.pov(mover_color)). _to_mover_pov() below is the one place that
flip happens, mirroring annotate.py's mover_pov_after() philosophy of
keeping perspective flips centralized in a single function.
"""
import json

import chess
import requests

from live_engine import LiveResult

CLOUD_EVAL_URL = "https://lichess.org/api/cloud-eval"
# Same politeness convention as sync_chesscom.py's USER_AGENT -- points at
# the public repo rather than a personal email, since this is distributed
# code run by many different users, not a one-off personal script.
USER_AGENT = "Chesswright (+https://github.com/Hawi254/chesswright)"


def _to_mover_pov(cp, mate, side_to_move_is_black: bool):
    """Flips White-POV cp/mate into side-to-move POV. Both flip together,
    in this one place, so the two can never disagree about whose
    perspective they're in -- same reasoning as annotate.py's
    mover_pov_after()."""
    if not side_to_move_is_black:
        return cp, mate
    return (None if cp is None else -cp), (None if mate is None else -mate)


def fetch_cloud_eval(fen: str, timeout: float = 3.0) -> LiveResult | None:
    """Look up a position in Lichess's cloud-eval database. Returns None on
    a miss (404), rate limit (429), timeout, or any other request failure --
    never raises, since this is an optional enrichment on top of the
    always-available local-engine fallback."""
    try:
        resp = requests.get(
            CLOUD_EVAL_URL, params={"fen": fen},
            headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None  # 404 (no cloud eval for this position) or 429 (rate limited)

    try:
        data = resp.json()
        pv = data["pvs"][0]
    except (ValueError, KeyError, IndexError):
        return None

    try:
        board = chess.Board(fen)
    except ValueError:
        return None

    cp, mate = _to_mover_pov(pv.get("cp"), pv.get("mate"), board.turn == chess.BLACK)

    pv_board = board.copy()
    pv_san = []
    best_move_san = None
    for uci in pv.get("moves", "").split():
        try:
            mv = chess.Move.from_uci(uci)
            san = pv_board.san(mv)
        except (ValueError, chess.IllegalMoveError):
            break
        if best_move_san is None:
            best_move_san = san
        pv_san.append(san)
        pv_board.push(mv)

    if best_move_san is None:
        return None  # no legal moves parsed out of the PV -- nothing usable

    return LiveResult(
        eval_cp=cp,
        eval_mate=mate,
        best_move_san=best_move_san,
        pv_json=json.dumps(pv_san),
        depth=data.get("depth", 0),
        engine_version="Lichess cloud",
    )
