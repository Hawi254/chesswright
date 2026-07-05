"""Chess.com-specific PGN header interpretation, used by ingest.py when it
detects a game came from chess.com rather than lichess (see is_chesscom_game
below). Verified against a real game fetched live from chess.com's public
PubAPI, not assumed from lichess's conventions -- see BRIEF.md's chess.com
integration spec for the research this is based on.

Chess.com's exported PGN shares UTCDate/UTCTime/ECO/Result/clock-comment
formats with lichess's (confirmed against a live sample), so those stay on
ingest.py's existing platform-neutral code path unchanged. This module
covers only the fields that are genuinely different: game id, time control,
termination, and opening name.
"""
import re

CHESSCOM_SITE_HEADER = "Chess.com"

_MOVE_TOKEN_RE = re.compile(r"\d+\.")  # searched anywhere in the slug, not anchored -- see
                                        # chesscom_opening_family()'s docstring for why


def is_chesscom_game(headers) -> bool:
    """Chess.com's Site header is always the literal string 'Chess.com',
    never a game URL (that lives in the separate Link header instead) --
    confirmed against a live game. This is a reliable, always-present
    discriminator, so no separate "which platform" flag needs to be
    threaded through ingest()."""
    return headers.get("Site", "") == CHESSCOM_SITE_HEADER


def parse_chesscom_time_control(tc_raw: str):
    """Chess.com TimeControl has three shapes, none matching lichess's
    always-has-a-'+' '300+0' convention (confirmed live: a no-increment
    game is just '180', not '180+0'):
      - '180'      -- no increment
      - '180+2'    -- base+increment, same shape as lichess once matched
      - '1/259200' -- daily/correspondence: seconds allowed per move, no
                       live clock at all
    Returns (base_seconds, increment_seconds, category). 'daily' is a new
    category, not folded into ingest.py's original bullet/blitz/rapid/
    classical set -- a correspondence game has no meaningful "estimated
    game duration" the way a live time control does.
    """
    if not tc_raw:
        return None, None, None
    if tc_raw.startswith("1/"):
        return None, None, "daily"
    if "+" in tc_raw:
        base_str, inc_str = tc_raw.split("+", 1)
    else:
        base_str, inc_str = tc_raw, "0"
    try:
        base = int(base_str)
        inc = int(inc_str)
    except ValueError:
        return None, None, None
    estimate = base + 40 * inc  # same estimate formula ingest.py uses for lichess
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


def classify_chesscom_termination(termination_raw: str, result: str):
    """Chess.com's Termination header is a prose sentence (confirmed live:
    'Hikaru won by resignation'), not lichess's coarse enum ingest.py's
    game_end_type logic was originally written against. Only that one
    exact string is confirmed live; the rest of this classifier is a
    best-effort keyword match against chess.com's documented outcome
    vocabulary and should be re-checked against a broader real sample
    before being trusted beyond an approximate bucket -- flagged here
    rather than silently assumed correct, same standard the berserk
    detector in chess_utils.py holds itself to.
    """
    s = (termination_raw or "").lower()
    is_draw = result == "1/2-1/2"
    if "checkmate" in s:
        return "checkmate"
    if "stalemate" in s:
        return "stalemate"
    if "repetition" in s:
        return "draw_repetition"
    if "50-move" in s or "50 move" in s:
        return "draw_50_move_rule"
    if "insufficient material" in s:
        return "insufficient_material"
    if "agreement" in s or "agreed" in s:
        return "draw_agreement"
    if "abandon" in s:
        return "abandoned"
    if "time" in s:
        # "timeout vs insufficient material" is a real chess.com draw
        # outcome with no matching bucket in ingest.py's original set --
        # closest existing one is insufficient_material, flagged as an
        # approximation, not a confirmed-correct mapping.
        return "insufficient_material" if is_draw else "time_forfeit"
    if "resignation" in s or "resigned" in s:
        return "resignation"
    return "unknown"


def chesscom_opening_family(eco_url: str):
    """Chess.com PGN never sets an 'Opening' name header (confirmed live:
    only ECO + ECOUrl are present), so ingest.py's normal Opening-header
    path has nothing to read for these games. ECOUrl instead encodes the
    exact per-game opening name chess.com itself assigned, e.g.:
      '.../openings/Closed-Sicilian-Defense-Grand-Prix-Attack-3...g6-4.Bc4-Bg7-5.Nf3'
      -> 'Closed Sicilian Defense Grand Prix Attack'

    Deliberately NOT resolved via a local ECO-code lookup table: ECO codes
    are many-to-many with opening family names (checked against lichess's
    own CC0 chess-openings reference dataset -- 57 of 500 real ECO codes
    map to more than one distinct family name, and the A00 catch-all code
    alone spans 20+ unrelated openings), so a code-based table would
    silently produce a wrong name for a meaningful fraction of games. The
    URL slug is exact and per-game instead of guessed from a lossy code.

    Truncates the slug at the first move-number token ('3.', '4.', ...)
    and turns the remaining dashes into spaces. Deliberately searches for
    that token ANYWHERE in the slug, not just at a '-'-delimited component
    boundary -- checked against a real live game (Hikaru, 2026-07) where
    the boundary between name and moves had no dash at all:
    '...Yugoslav-Panno-System...7.d5-Na5-8.Nbd2-c5', where the move token
    '7.' sits immediately after 'System...' with nothing to split on. An
    earlier version of this only checked whole '-'-delimited components
    and silently produced 'Yugoslav Panno System...7.d5 Na5' for that
    exact game -- caught by inspecting real ingested data, not assumed
    correct from the one game originally used to design this.
    """
    if not eco_url:
        return None
    slug = eco_url.rstrip("/").rsplit("/", 1)[-1]
    m = _MOVE_TOKEN_RE.search(slug)
    name_part = slug[:m.start()] if m else slug
    name_part = name_part.rstrip(".-")
    if not name_part:
        return None
    return name_part.replace("-", " ")
