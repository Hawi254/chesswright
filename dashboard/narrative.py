"""
Phase 6 Build Order step 4 -- template-based narrative generator. Free,
instant, always-available default story for any game (no API call). The
on-demand Claude-API "tell me the story" richer version is a separate,
later piece -- this module is the free default every game always has.

Determinism: one random.Random(game_id) is seeded ONCE per game and used
for every phrasing choice in that game's narrative, in order -- the same
game reads identically every time it's viewed; different games get real
variety, since their seeds differ.
"""
import random

import chess
import pandas as pd

BRILLIANT_BONUS = 400      # flat impact-score bonus for is_brilliant_candidate
SHARP_FIND_BONUS = 250      # flat impact-score bonus for a 'best' move in a sharp position
SHARP_FIND_MIN_SHARPNESS = 150  # "found the only move" needs a real forcing position
MAX_CRITICAL_MOMENTS = 5
RATING_UPSET_THRESHOLD = 200  # reuses the spirit of config.yaml's rating_diff_buckets

# Every moment-type has a YOU set and an OPPONENT set -- a brilliant find,
# a blunder, and the turning point can each belong to either side, and
# crediting/blaming the wrong one isn't a style nit, it's wrong. Caught
# directly: a real Claude-API test run praised "a real sacrifice, and the
# right one" for two moves that were both the OPPONENT's, and called the
# OPPONENT'S blunder "the moment the game turned" without saying so --
# both technically-true facts (move number, san, classification) wrapped
# in attribution-free prose that reads like the player's own doing.
BLUNDER_PHRASES_YOU = [
    "On move {move_number}, your {san} let the position slip away.",
    "Your {san} on move {move_number} was the kind of move that costs games.",
    "Move {move_number}: you played {san}, and it handed away what had been built up.",
]
BLUNDER_PHRASES_OPPONENT = [
    "On move {move_number}, {opponent}'s {san} handed the position back to you.",
    "{opponent} blundered with {san} on move {move_number} -- a real gift.",
    "Move {move_number} was {opponent}'s mistake to give: {san} let everything slip.",
]
MISTAKE_PHRASES_YOU = [
    "Your {san} on move {move_number} wasn't quite right.",
    "A small slip on your part with {san} on move {move_number}.",
    "Move {move_number}: your {san} gave some ground back.",
]
MISTAKE_PHRASES_OPPONENT = [
    "{opponent}'s {san} on move {move_number} wasn't quite right either.",
    "A small slip from {opponent} with {san} on move {move_number}.",
    "Move {move_number} saw {opponent} give a little ground back with {san}.",
]
BRILLIANT_PHRASES_YOU = [
    "Then came your {san} on move {move_number} -- a real sacrifice, and the right one.",
    "Move {move_number} was your standout moment: {san}, material given up correctly.",
    "Your {san} on move {move_number} was a genuine find, not just a good move.",
]
BRILLIANT_PHRASES_OPPONENT = [
    "{opponent} found the right defense on move {move_number}: {san}, a real sacrifice.",
    "Move {move_number} belonged to {opponent} -- {san} gave up material, correctly, to escape.",
    "{opponent}'s {san} on move {move_number} was a genuine find on their part, not yours.",
]
SHARP_FIND_PHRASES_YOU = [
    "On move {move_number}, your {san} was the only move that worked -- and you found it.",
    "Your {san} on move {move_number} threaded a narrow needle in a sharp position.",
    "Move {move_number}: {san}, one right answer in a position with no margin for error, and you found it.",
]
SHARP_FIND_PHRASES_OPPONENT = [
    "On move {move_number}, {opponent}'s {san} was the only move that worked for them.",
    "{opponent}'s {san} on move {move_number} threaded a narrow needle in a sharp position.",
    "Move {move_number}: {opponent} found {san}, the one move that kept them in the game.",
]
TURNING_POINT_PHRASES_YOU = [
    "The moment the game turned was move {move_number}, when you played {san}.",
    "Everything changed on move {move_number}, when your {san} shifted the balance.",
    "If there's one move that decided this game, it was your {san} on move {move_number}.",
]
TURNING_POINT_PHRASES_OPPONENT = [
    "The moment the game turned was move {move_number}, when {opponent} played {san}.",
    "Everything changed on move {move_number}, when {opponent}'s {san} shifted the balance your way.",
    "If there's one move that decided this game, it was {opponent}'s {san} on move {move_number}.",
]

CLOSING_PHRASES = {
    "checkmate": [
        "It ended in checkmate.",
        "The game finished with a mate on the board.",
        "Checkmate closed it out.",
    ],
    "resignation": [
        "The opponent resigned.",
        "It ended in resignation.",
        "The game was conceded before the end.",
    ],
    "time_forfeit": [
        "The game ended on the clock.",
        "Time ran out before the position resolved.",
        "It was decided by the clock, not the board.",
    ],
    "stalemate": [
        "The game ended in stalemate.",
        "It fizzled out to a stalemate draw.",
    ],
    "draw_repetition": [
        "The position repeated and the game was drawn.",
        "It ended in a draw by repetition.",
    ],
    "draw_50_move_rule": [
        "The 50-move rule brought it to a draw.",
        "Neither side could make progress, and the 50-move rule applied.",
    ],
    "draw_agreement": [
        "The players agreed to a draw.",
        "It ended in an agreed draw.",
    ],
    "insufficient_material": [
        "There wasn't enough material left for either side to win.",
        "It ended in a draw -- insufficient material on the board.",
    ],
    "abandoned": [
        "The game was abandoned before it really began.",
    ],
    "unknown": [
        "The game ended without a clearly recorded finish.",
    ],
}

OUTCOME_WORD = {"win": "won", "loss": "lost", "draw": "drew"}


def _impact_score(row):
    score = 0.0
    if row.classification in ("mistake", "blunder") and not pd.isna(row.cpl):
        score = max(score, row.cpl)
    if not pd.isna(row.is_brilliant_candidate) and row.is_brilliant_candidate:
        score = max(score, BRILLIANT_BONUS)
    if row.classification == "best" and not pd.isna(row.sharpness) and row.sharpness >= SHARP_FIND_MIN_SHARPNESS:
        score = max(score, SHARP_FIND_BONUS)
    return score


def select_critical_moments(moves_df):
    """Returns (critical_moments, turning_point, n_other_inaccuracies).
    critical_moments is a list of move rows, ply order, capped at
    MAX_CRITICAL_MOMENTS. turning_point is the single highest-cpl
    blunder/mistake among them (None if there isn't one) -- "the moment
    it turned" means a swing in fortune, not a good find."""
    scored = []
    for row in moves_df.itertuples():
        score = _impact_score(row)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    top = scored[:MAX_CRITICAL_MOMENTS]
    top.sort(key=lambda x: x[1].ply)
    critical_moments = [row for _score, row in top]

    swings = [row for _score, row in scored if row.classification in ("mistake", "blunder")]
    turning_point = max(swings, key=lambda r: r.cpl) if swings else None

    n_other = max(0, len(scored) - len(top))
    return critical_moments, turning_point, n_other


def _choice_no_immediate_repeat(rng, phrases, used):
    """rng.choice(phrases), but excludes whichever index(es) of this exact
    phrases list were already picked earlier in the same narrative --
    caught live: a game with two blunders in the same category (both
    BLUNDER_PHRASES_YOU) drew the identical template verbatim for both,
    since plain rng.choice() has no memory across calls. `used` is a
    dict[id(phrases), set[int]] scoped to one generate_narrative() call,
    so different categories (e.g. BLUNDER_PHRASES_YOU vs _OPPONENT) don't
    interfere with each other. Once every index in a category has been
    used, that category's used-set clears -- a 4th+ moment in the same
    category can recur, just never immediately.

    Uses the SAME rng instance and makes exactly one rng call per
    invocation (rng.choice on the remaining candidates), so the sequence
    of random calls -- and therefore per-game determinism from
    random.Random(game_id) -- is unchanged; only which index within that
    call can be picked is restricted."""
    key = id(phrases)
    seen = used.setdefault(key, set())
    if len(seen) >= len(phrases):
        seen.clear()
    candidates = [p for i, p in enumerate(phrases) if i not in seen]
    choice = rng.choice(candidates)
    seen.add(phrases.index(choice))
    return choice


def _moment_sentence(row, rng, is_turning_point, opponent_name, used_phrases):
    is_you = bool(row.is_player_move)
    if is_turning_point:
        phrases = TURNING_POINT_PHRASES_YOU if is_you else TURNING_POINT_PHRASES_OPPONENT
    elif row.classification == "blunder":
        phrases = BLUNDER_PHRASES_YOU if is_you else BLUNDER_PHRASES_OPPONENT
    elif row.classification == "mistake":
        phrases = MISTAKE_PHRASES_YOU if is_you else MISTAKE_PHRASES_OPPONENT
    elif not pd.isna(row.is_brilliant_candidate) and row.is_brilliant_candidate:
        phrases = BRILLIANT_PHRASES_YOU if is_you else BRILLIANT_PHRASES_OPPONENT
    else:
        phrases = SHARP_FIND_PHRASES_YOU if is_you else SHARP_FIND_PHRASES_OPPONENT
    template = _choice_no_immediate_repeat(rng, phrases, used_phrases)
    move_number = (row.ply + 1) // 2
    return template.format(move_number=move_number, san=row.san, opponent=opponent_name)


def generate_narrative(header, moves_df):
    """header: a pandas Series from get_game_detail's first return value.
    moves_df: the second return value. Returns the full narrative as a
    single string."""
    rng = random.Random(header.game_id)

    color = header.player_color.capitalize()
    upset_phrase = ""
    if header.rating_diff <= -RATING_UPSET_THRESHOLD:
        upset_phrase = ", as a significant underdog"
    elif header.rating_diff >= RATING_UPSET_THRESHOLD:
        upset_phrase = ", as the clear favorite"

    setup = (f"On {header.utc_date}, you played {header.opponent_name} "
             f"({header.opponent_rating}) as {color} in a {header.time_control_category} "
             f"game, opening with the {header.opening_family}{upset_phrase}.")

    critical_moments, turning_point, n_other = select_critical_moments(moves_df)
    moment_sentences = []
    used_phrases: dict = {}
    for row in critical_moments:
        is_tp = turning_point is not None and row.ply == turning_point.ply
        moment_sentences.append(
            _moment_sentence(row, rng, is_tp, header.opponent_name, used_phrases))
    if n_other > 0:
        moment_sentences.append(f"There were {n_other} other notable moments along the way.")

    closing_options = CLOSING_PHRASES.get(header.game_end_type, CLOSING_PHRASES["unknown"])
    closing = rng.choice(closing_options)
    result_word = OUTCOME_WORD.get(header.outcome_for_player, "finished")
    closing = f"You {result_word}. {closing}"

    paragraphs = [setup]
    if moment_sentences:
        paragraphs.append(" ".join(moment_sentences))
    paragraphs.append(closing)
    return "\n\n".join(paragraphs)


def position_after_ply(moves_df, ply):
    """The board position right after the move at `ply` -- reuses the
    same "next ply's fen_before is this ply's after-position" pattern
    opening_explorer.py already established, falling back to replaying
    the move on the board for the last ply of the game (no next row)."""
    row = moves_df[moves_df.ply == ply].iloc[0]
    next_rows = moves_df[moves_df.ply == ply + 1]
    if len(next_rows):
        return next_rows.iloc[0].fen_before
    board = chess.Board(row.fen_before)
    board.push_san(row.san)
    return board.fen()


def generate_career_narrative(stats, rating_df, top_game_row):
    """Phase 6c.4: the Overview page's landing paragraph -- "every game
    tells a story" applied to the CAREER level, not just per-game.
    Deliberately no random phrasing variants (unlike generate_narrative
    above): there's only one career, read once per visit, not dozens of
    games where repetition would actually be noticeable.

    stats: dict from data.get_headline_stats. rating_df: DataFrame from
    data.get_rating_trajectory (columns year, avg_rating). top_game_row:
    a row from get_game_explorer_table sorted by drama_score (the single
    most dramatic game), or None if the table is empty."""
    if rating_df.empty:
        # A genuinely fresh install (no games fetched yet, or none with a
        # rating) has nothing to build a trajectory out of -- not a rare
        # edge case here the way it was for the original project's
        # already-huge dataset, since this page is reachable from the
        # sidebar at any point during BRIEF.md's Phase B onboarding
        # wizard, including before any games exist at all.
        return "No games yet -- fetch some games to get started."

    years = sorted(rating_df.year.tolist())
    span = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0]) if years else "your career"
    start_rating = rating_df.iloc[0].avg_rating
    peak_row = rating_df.loc[rating_df.avg_rating.idxmax()]
    end_rating = rating_df.iloc[-1].avg_rating

    arc = (f"Across {stats['total_games']:,} games since {span}, your rating moved from "
           f"~{start_rating:.0f} to a peak of ~{peak_row.avg_rating:.0f} in {int(peak_row.year)}")
    if abs(end_rating - peak_row.avg_rating) > 1:
        arc += f", and sits around ~{end_rating:.0f} now."
    else:
        arc += ", right where it stands today."

    # acpl is None until at least one game has been engine-analyzed AND
    # annotated -- a real gap during onboarding, since games can exist
    # well before the first analysis batch finishes, not just a
    # theoretical possibility.
    acpl_text = f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "not available yet"
    record = (f"Overall record: {stats['win_pct']:.1f}% wins across all games. "
              f"Of the {stats['analyzed_games']:,} engine-analyzed so far, average centipawn "
              f"loss is {acpl_text}.")

    teaser = ""
    if top_game_row is not None:
        teaser = (f"\n\nThe most dramatic game on record so far: vs. {top_game_row.opponent_name} "
                  f"on {top_game_row.utc_date} ({top_game_row.outcome_for_player}).")

    return f"{arc} {record}{teaser}"


def player_win_prob_series(moves_df):
    """win_prob_before/after are stored from the MOVER's own perspective at
    that ply (per CLAUDE.md's eval-perspective convention -- never
    normalized upstream, on purpose). For a single continuous "shape of
    the game" trace from the analyzed player's perspective, this is the
    one place that conversion happens: 1-p whenever the mover at that ply
    was the opponent, p unchanged when it was the player. Returns a
    DataFrame with columns ply, player_win_prob (one row per ply that has
    a value, i.e. has been annotated -- NaN rows are dropped, not zero-
    filled, so a thin-annotated game shows a short real line, not a
    misleadingly flat one)."""
    df = moves_df[["ply", "is_player_move", "win_prob_after"]].dropna(subset=["win_prob_after"]).copy()
    df["player_win_prob"] = df.win_prob_after.where(df.is_player_move == 1, 1.0 - df.win_prob_after)
    return df[["ply", "player_win_prob"]]
