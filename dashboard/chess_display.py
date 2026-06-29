"""Shared position display helpers used by openings_view and game_detail_view."""
import json
import math

import chess
import chess.pgn

_GLYPH_TO_NAG = {"!": 1, "?": 2, "!!": 3, "??": 4, "!?": 5, "?!": 6}


def eval_str(eval_cp, eval_mate) -> str:
    """Format a Stockfish eval as a sign-prefixed string (+1.25, -0.50, M3, -M5)."""
    if eval_mate is not None:
        return f"M{eval_mate}" if eval_mate > 0 else f"−M{abs(eval_mate)}"
    if eval_cp is not None:
        return f"+{eval_cp / 100:.2f}" if eval_cp >= 0 else f"{eval_cp / 100:.2f}"
    return "—"


def pv_str(fen: str, pv_json_str, max_moves: int = 6) -> str | None:
    """Format a stored pv_json string as a readable move sequence.

    Reconstructs move-number notation (e.g. '1. Nf3 d5 2. d4') using
    python-chess so the notation is correct for both white-to-move and
    black-to-move positions.  Returns None if pv_json_str is empty or
    unparseable, so callers can skip the line without an extra None check.
    """
    if not pv_json_str:
        return None
    try:
        pv = json.loads(pv_json_str)
    except Exception:
        return None
    board = chess.Board(fen)
    parts: list[str] = []
    for san in pv[:max_moves]:
        try:
            if board.turn == chess.WHITE:
                parts.append(f"{board.fullmove_number}. {san}")
            elif not parts:
                parts.append(f"{board.fullmove_number}… {san}")
            else:
                parts.append(san)
            board.push_san(san)
        except Exception:
            break
    return " ".join(parts) or None


def eval_bar_html(eval_cp, eval_mate, fen: str) -> str:
    """Return an HTML eval bar (white/black split proportional to win probability).

    eval_cp and eval_mate are from side-to-move's perspective (positive = current
    player better), so we flip to absolute before converting to win probability.
    """
    try:
        board = chess.Board(fen)
        white_to_move = board.turn == chess.WHITE
    except Exception:
        white_to_move = True

    if eval_mate is not None:
        white_pct = 100.0 if (eval_mate > 0) == white_to_move else 0.0
    elif eval_cp is not None:
        absolute_cp = eval_cp if white_to_move else -eval_cp
        white_pct = 100.0 / (1.0 + math.exp(-absolute_cp / 250.0))
    else:
        white_pct = 50.0

    black_pct = 100.0 - white_pct
    return (
        f'<div style="display:flex;height:12px;border-radius:3px;overflow:hidden;'
        f'margin:4px 0 2px 0;">'
        f'<div style="width:{white_pct:.1f}%;background:#d8d8d8;"></div>'
        f'<div style="width:{black_pct:.1f}%;background:#222222;"></div>'
        f'</div>'
    )


def variation_to_pgn(branch_fen: str, moves_uci: list, annotations: dict,
                     title: str | None = None) -> str:
    """Build a PGN string from a saved variation.

    annotations: {move_index: Annotation} from get_variation_annotations().
    Index 0 = branch-point comment; index n = annotation after the nth move.
    """
    game = chess.pgn.Game()
    game.headers["Event"] = title or "Chesswright variation"
    game.headers["Site"] = "Chesswright"
    game.headers["Result"] = "*"
    if branch_fen != chess.STARTING_FEN:
        try:
            game.setup(chess.Board(branch_fen))
        except Exception:
            game.headers["FEN"] = branch_fen
            game.headers["SetUp"] = "1"

    if 0 in annotations:
        ann = annotations[0]
        parts = [p for p in [ann.comment,
                              f"[Claude: {ann.ai_comment}]" if ann.ai_comment else None]
                 if p]
        if parts:
            game.comment = " ".join(parts)

    node = game
    for i, uci in enumerate(moves_uci):
        try:
            move = chess.Move.from_uci(uci)
            node = node.add_variation(move)
            ann = annotations.get(i + 1)
            if ann:
                if ann.glyph and ann.glyph in _GLYPH_TO_NAG:
                    node.nags.add(_GLYPH_TO_NAG[ann.glyph])
                parts = [p for p in [ann.comment,
                                     f"[Claude: {ann.ai_comment}]" if ann.ai_comment else None]
                         if p]
                if parts:
                    node.comment = " ".join(parts)
        except Exception:
            break

    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    return game.accept(exporter)
