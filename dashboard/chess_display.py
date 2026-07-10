"""Shared position display helpers used by openings_view and game_detail_view."""
import datetime
import json
import math
import re

import chess
import chess.pgn

from chesscom_pgn import CHESSCOM_SITE_HEADER

_GLYPH_TO_NAG = {"!": 1, "?": 2, "!!": 3, "??": 4, "!?": 5, "?!": 6}


def lichess_game_url(game_id: str, site) -> str | None:
    """Real, clickable link back to the original game -- lichess only.
    games.site stores the PGN Site header verbatim; for lichess exports
    that's always the game's own canonical URL (confirmed by how
    ingest.py's parse_game_id already extracts game_id from this exact
    header), so reconstructing from game_id is equivalent and more
    robust than trusting the stored string's exact formatting (trailing
    slash, http vs https, etc.).

    Returns None for chess.com games: games.site there is the literal
    string "Chess.com", not a URL -- the real per-game Link header was
    only used transiently during ingest to parse game_id and was never
    persisted, so there's nothing reliable to link to yet without a
    schema change. Deliberately not guessed at -- chess.com has used more
    than one URL scheme (live vs. daily games), and a wrong guess is a
    silently broken link, worse than no link."""
    if not game_id or site == CHESSCOM_SITE_HEADER:
        return None
    return f"https://lichess.org/{game_id}"


def material_sig_str(sig: str) -> str:
    """Human-readable rendering of a chess_utils.material_signature()
    string, e.g. "Q1R1B1P6vQ1R1B1P6" -> "Q+R+B+6P vs Q+R+B+6P". Formatted
    at display time only, same pattern game_endings_view.py's
    _END_TYPE_LABELS already uses for its own chart labels -- the
    underlying cached DataFrame is never mutated.

    Kept intentionally more granular than data/_shared.py's bucketed
    classifiers (_classify_endgame_type's Queen/Rook/Minor/King & pawn,
    _classify_middlegame_trade_tier's No/Light/Moderate/Heavy trades): this
    per-signature string is for the Patterns page's detailed material-
    structure table, where the exact piece combination (opposite-colored
    bishops, queenless middlegame, etc.) is the whole point, not a broad
    category -- the bucketed classifiers back a separate, coarser grouped
    view on the same page, not a replacement for this one."""
    def side_str(side: str) -> str:
        pairs = re.findall(r"([QRBNP])(\d+)", side)
        # Preserve chess_utils's own piece order rather than regex match
        # order, which already follows it -- re.findall over "Q1R1B1P6"
        # naturally yields [('Q','1'), ('R','1'), ('B','1'), ('P','6')]
        # in that order, so no re-sort needed; ordering is documented here
        # for the reader, not because it's at risk of drifting silently.
        if not pairs:
            return "K"  # bare king -- no other piece letters present
        return "+".join(letter if count == "1" else f"{count}{letter}"
                         for letter, count in pairs)

    if "v" not in sig:
        return sig  # unexpected format -- show raw rather than mangle it
    white_side, black_side = sig.split("v", 1)
    return f"{side_str(white_side)} vs {side_str(black_side)}"


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


def _safe_val(val) -> bool:
    """True if val is a real, non-NaN value."""
    if val is None:
        return False
    try:
        return not math.isnan(float(val))
    except (TypeError, ValueError):
        return bool(val)


def _drill_context(row: dict) -> str:
    """Human-readable context string for a drill position."""
    parts = []
    if _safe_val(row.get("opening")):
        parts.append(f"Opening: {row['opening']}")
    if _safe_val(row.get("move_number")):
        parts.append(f"Move {int(row['move_number'])}")
    if _safe_val(row.get("phase")):
        parts.append(f"Phase: {row['phase']}")
    if _safe_val(row.get("motif")):
        parts.append(f"Missed tactic: {row['motif']}")
    if _safe_val(row.get("cpl")):
        parts.append(f"CPL: {int(row['cpl'])}")
    if _safe_val(row.get("wp_drop")):
        parts.append(f"Win-prob drop: {float(row['wp_drop']):.0%}")
    if _safe_val(row.get("hole_score")):
        parts.append(f"Hole score: {float(row['hole_score']):.1f}")
    if _safe_val(row.get("n_distinct_moves")):
        parts.append(f"{int(row['n_distinct_moves'])} distinct responses seen")
    return " | ".join(parts)


def drills_to_pgn_study(drill_groups: dict) -> str:
    """Convert drill positions to a multi-chapter PGN string for Lichess Study import.

    drill_groups: {chapter_name: DataFrame} -- each DataFrame needs at minimum
    fen_before and best_move_san columns. Optional: opening, move_number, phase,
    motif, cpl, wp_drop, hole_score.

    Returns a single PGN string where each drill is one game. Lichess Study
    interprets multi-game PGN as separate chapters on import.
    """
    today = datetime.date.today().strftime("%Y.%m.%d")
    games = []
    for source, df in drill_groups.items():
        for i, row in enumerate(df.itertuples(index=False), 1):
            row_dict = row._asdict()
            fen = row_dict.get("fen_before")
            best_move = row_dict.get("best_move_san") or row_dict.get("most_played_san")
            if not fen or not best_move or not _safe_val(fen) or not _safe_val(best_move):
                continue

            game = chess.pgn.Game()
            game.headers["Event"] = f"{source} — Drill {i}"
            game.headers["Site"] = "Chesswright"
            game.headers["Date"] = today
            game.headers["Result"] = "*"
            try:
                game.setup(chess.Board(fen))
            except Exception:
                game.headers["FEN"] = fen
                game.headers["SetUp"] = "1"

            context = _drill_context(row_dict)
            if context:
                game.comment = context

            try:
                board = chess.Board(fen)
                move = board.parse_san(str(best_move))
                node = game.add_variation(move)
                node.comment = "Engine best move"
            except Exception:
                pass

            exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
            games.append(game.accept(exporter))

    return "\n\n".join(games)


def game_to_annotated_pgn(header, moves_df, narrative_text: str | None = None,
                          player_name: str = "You") -> str:
    """Full-game annotated PGN with move classifications and optional Claude narrative.

    header: namedtuple from data.get_game_detail()
    moves_df: DataFrame with ply, san, classification, cpl columns
    narrative_text: embedded as the PGN game comment when present
    player_name: used as the White or Black player tag -- the caller's
        username on WHICHEVER platform header.site says this game is from
        (lichess or chess.com), not always the lichess one; see
        game_detail_view.py's call site, which picks the right config field
        based on header.site before calling this.
    """
    game = chess.pgn.Game()

    color = (getattr(header, "player_color", "") or "").lower()
    outcome = (getattr(header, "outcome_for_player", "") or "").lower()

    if color == "white":
        white_name, black_name = player_name, (header.opponent_name or "Opponent")
        white_elo = getattr(header, "player_rating", None)
        black_elo = getattr(header, "opponent_rating", None)
        result = {"win": "1-0", "loss": "0-1"}.get(outcome, "1/2-1/2")
    else:
        white_name, black_name = (header.opponent_name or "Opponent"), player_name
        white_elo = getattr(header, "opponent_rating", None)
        black_elo = getattr(header, "player_rating", None)
        result = {"win": "0-1", "loss": "1-0"}.get(outcome, "1/2-1/2")

    try:
        date_str = str(header.utc_date).replace("-", ".")
    except Exception:
        date_str = "????.??.??"

    # header.site is the raw games.site column: literally "Chess.com" for
    # chess.com-origin games (see chesscom_pgn.CHESSCOM_SITE_HEADER),
    # otherwise a lichess.org game URL. Was unconditionally hardcoded to
    # "Lichess (via Chesswright)" before chess.com was a real second
    # source -- silently mislabeled the export's origin for those games.
    source = "Chess.com" if getattr(header, "site", "") == "Chess.com" else "Lichess"
    game.headers["Event"] = f"vs {header.opponent_name or 'Opponent'}"
    game.headers["Site"] = f"{source} (via Chesswright)"
    game.headers["Date"] = date_str
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    for tag, elo in (("WhiteElo", white_elo), ("BlackElo", black_elo)):
        if elo is not None:
            try:
                game.headers[tag] = str(int(elo))
            except (TypeError, ValueError):
                pass
    game.headers["Result"] = result
    opening = getattr(header, "opening_family", None)
    if opening:
        game.headers["Opening"] = str(opening)

    if narrative_text:
        game.comment = narrative_text

    node = game
    board = chess.Board()
    for row in moves_df.sort_values("ply").itertuples(index=False):
        try:
            move = board.parse_san(str(row.san))
        except Exception:
            break
        node = node.add_variation(move)
        parts = []
        classification = getattr(row, "classification", None)
        if classification and str(classification) not in ("", "None", "nan"):
            parts.append(str(classification))
        cpl = getattr(row, "cpl", None)
        if cpl is not None:
            try:
                cpl_f = float(cpl)
                if not math.isnan(cpl_f):
                    parts.append(f"CPL {int(cpl_f)}")
            except (TypeError, ValueError):
                pass
        if parts:
            node.comment = ", ".join(parts)
        board.push(move)

    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    return game.accept(exporter)


def drills_to_anki_csv(drill_groups: dict) -> str:
    """Convert drill positions to an Anki-importable tab-separated string.

    One card per position: FEN \\t Side to move \\t Engine best move \\t Source \\t Context.
    No header row -- Anki expects data-only with tab separator.
    """
    rows = []
    for source, df in drill_groups.items():
        for row in df.itertuples(index=False):
            row_dict = row._asdict()
            fen = row_dict.get("fen_before")
            best_move = row_dict.get("best_move_san") or row_dict.get("most_played_san")
            if not fen or not best_move or not _safe_val(fen) or not _safe_val(best_move):
                continue
            try:
                board = chess.Board(fen)
                side = "White" if board.turn == chess.WHITE else "Black"
            except Exception:
                side = "?"
            context = _drill_context(row_dict)
            rows.append("\t".join([fen, side, str(best_move), source, context]))
    return "\n".join(rows)
