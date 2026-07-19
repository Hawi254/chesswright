"""Rich per-game narrative, structured game report, engine-move
explanation, and variation-position annotation -- one of four topic
modules split out of the former dashboard/claude_narrative.py.
"""
from .client import contextualize, PERSONA_AND_STYLE, _completeness_note, _game_completeness_note


def _build_prompt(header, moves_df, template_narrative, critical_moments, turning_point,
                   analyzed_games, total_games):
    # Explicit "(YOUR move)" / "(OPPONENT's move)" tag per moment -- a real
    # test run without this tag praised the opponent's two brilliant
    # sacrifices as if the player had made them, and called the
    # opponent's blunder "the moment the game turned" without saying so.
    # Whose move it was is exactly as important a fact as the san/cpl, and
    # the model won't reliably infer it from classification/cpl alone.
    moment_lines = []
    for row in critical_moments:
        tag = "TURNING POINT" if turning_point is not None and row.ply == turning_point.ply else row.classification
        who = "YOUR move" if row.is_player_move else f"{header.opponent_name}'s move (the opponent)"
        moment_lines.append(
            f"  move {(row.ply + 1) // 2} ({who}): {row.san} -- {tag}, cpl={row.cpl}")

    return f"""You are writing a short, vivid story about one chess game, presented to the
player as the story of their own game. The reader is the player, addressed
as "you" -- the opponent is a separate person, named below.

{PERSONA_AND_STYLE}

STRICT FACTUAL RULES, do not violate these:
- Do not invent moves, ratings, outcomes, or any detail not explicitly given below.
- Do not invent statistics, percentages, or any comparison to other players
  or rating levels (e.g. "98% of players wouldn't find this") -- nothing
  like that is given here, so do not write anything like that.
- Each critical moment below is explicitly tagged as YOUR move or the
  OPPONENT's move. Credit/blame the correct side -- if a moment is
  tagged as the opponent's, the story must say so (e.g. "{header.opponent_name}
  played..."), never imply you made that move.

{_game_completeness_note(header, int(moves_df.ply.max()))}
{_completeness_note(analyzed_games, total_games)}

Date: {header.utc_date}
Opponent: {header.opponent_name} (rated {header.opponent_rating})
Player rating: {header.player_rating}, rating differential: {header.rating_diff}
Color played: {header.player_color}
Time control: {header.time_control_category}
Opening: {header.opening_family}
Result: {header.outcome_for_player}
How the game ended: {header.game_end_type}

Critical moments:
{chr(10).join(moment_lines) if moment_lines else "  (no standout moments flagged)"}

A plain template-based summary already exists for reference (don't just
repeat it verbatim -- write something more vivid, but stay factually
consistent with it, including which side each moment belongs to):
{template_narrative}

Write 2-3 short paragraphs telling this game's story. Be specific about
the critical moments above, and explicit about whose move each one was."""


def generate_rich_narrative(header, moves_df, template_narrative, critical_moments, turning_point,
                             analyzed_games, total_games):
    prompt = _build_prompt(header, moves_df, template_narrative, critical_moments, turning_point,
                            analyzed_games, total_games)
    return contextualize(prompt)


def explain_engine_move(fen: str, eval_cp: int | None, eval_mate: int | None,
                        best_san: str) -> str:
    """2-3 sentences explaining WHY the engine's top move is the right choice.

    Distinct from annotate_position(): that writes a position label for
    the user's own variation notes; this explains an engine suggestion in
    the context of game review -- the question being answered is always
    'why is X the best move here?', not 'what is this position about?'
    """
    if eval_mate is not None:
        side = "current side" if eval_mate > 0 else "opponent"
        eval_str = f"forced mate in {abs(eval_mate)} for the {side}"
    elif eval_cp is not None:
        eval_str = f"{eval_cp / 100:+.2f} (positive = current player is better)"
    else:
        eval_str = "not available"

    prompt = f"""You are explaining a chess move to a serious club-level player reviewing their game.

Position (FEN): {fen}
Engine evaluation (side-to-move perspective): {eval_str}
Engine's recommended move: {best_san}

In exactly 2-3 sentences, explain the chess IDEA behind {best_san}: what specific threat it creates, what structural element it improves, or what weakness it exploits. Name the concrete squares, pieces, or pawn features involved. Do NOT describe the physical move — explain WHY it works. Do NOT use filler phrases like "this is a great move."

Explanation:"""
    return contextualize(prompt, max_tokens=180)


_GAME_REPORT_VOICE = """VOICE: Write as an experienced chess coach annotating a student's game — analytical,
precise, and direct. Every sentence must carry specific chess information. Use concrete
concepts: piece activity, pawn structure, weak squares, open files, outpost squares,
king safety, tactical patterns. Name specific squares, pieces, and pawn features rather
than abstract descriptions. Avoid sports-commentary flourishes ("what a blunder!"),
suspense-building ("little did they know…"), and filler phrases ("this was a key moment",
"interestingly", "notably"). Do not praise moves as "excellent" or "brilliant" — describe
what they accomplish. Address the player as "you".

TERMS — introduce with a brief in-sentence definition the first time each appears, then
use freely:
- ACPL (Average Centipawn Loss): average engine-evaluation cost per move — lower is more accurate
- CPL (Centipawn Loss): the evaluation cost of one specific move
- Blunder / mistake / inaccuracy: severity tiers; a blunder typically drops at least a pawn of value
- Outpost: a square the opponent's pawns can no longer attack, ideal for a piece to lodge permanently
- Open file: a file with no pawns of either colour, valuable for rooks
- Backward pawn: a pawn that has advanced beyond its neighbours and cannot be protected by other pawns"""


def _build_game_report_prompt(header, num_plies: int,
                               phase_stats: str, notable_moments: str) -> str:
    return f"""You are writing a structured game report for a chess player reviewing one of their games.
This is an analytical coaching document, not a narrative story: section headings, specific phase
breakdowns, each notable moment annotated with concrete chess reasoning, and actionable takeaways.

{_GAME_REPORT_VOICE}

STRICT FACTUAL RULES — do not violate these:
- Do not invent moves, evaluations, square names, or any detail not given below.
- Do not invent comparisons to other players or rating levels. Never write "X% of players" or similar.
- Each moment in the list is tagged YOUR move or OPPONENT's move — credit the correct side every time.
- If a motif is listed (fork, pin, skewer, discovered attack, back-rank mate, hanging piece), name it.
  If no motif is listed for a move, do not invent one.
- The phase accuracy stats are for context — synthesise what they mean, do not recite them as a list.

{_game_completeness_note(header, num_plies)}

GAME FACTS:
Date: {header.utc_date}
Opponent: {header.opponent_name} (rated {header.opponent_rating})
Player rating: {header.player_rating}
Color played: {header.player_color}
Time control: {header.time_control_category}
Opening: {header.opening_family}
Result: {header.outcome_for_player}
How it ended: {header.game_end_type}

YOUR ACCURACY BY PHASE (your moves only, engine-analyzed — use to characterise each phase):
{phase_stats}

NOTABLE MOMENTS (player mistakes/blunders/highlights + opponent blunders, ordered by ply):
{notable_moments}

Write the report using EXACTLY these section headings in bold markdown. Omit Endgame entirely
if the game ended before a genuine endgame (resignation, mate, or time forfeit in the middlegame).

**Opening:** 1-2 sentences. Characterise how the {header.opening_family} was handled — whether the position
was steered into familiar or unfamiliar territory, and what structural feature (pawn centre, piece
placement, king safety) shaped the early middlegame. Do not recite accuracy numbers.

**Middlegame:** 2-3 sentences. Identify the key structural or tactical theme that ran through this
phase (e.g. a weak square, an open file, a queenside pawn majority, uncastled kings). Explain how the
notable moments connect to that theme and what ultimately decided the game's direction.

**Endgame:** 1-2 sentences, only if a genuine endgame was reached. Name the material imbalance (e.g.
rook vs. bishop, king-and-pawn), identify the key winning or drawing resource, and assess whether
technique was sound or where it broke down.

**Key moments:**
One bullet per entry in the notable moments list above — do not skip any. Format each as:
"- **[Move number]. [SAN]** ([whose move]): [2 sentences — (1) what the position required at that
moment: the specific threat, weak square, piece, or tactical pattern at stake; (2) what the played
move did or failed to do, and for mistakes/blunders what the engine's preference addressed instead.
For listed tactical motifs, name and briefly explain the pattern.]"

**Verdict:**
2-3 numbered takeaways, each naming a specific chess concept or position type from this game.
Not "work on tactics" but e.g. "In positions with an open g-file against your king, calculate
forcing lines before committing to a pawn advance." Omit a third point rather than pad.
1. [Most important lesson, tied to a specific moment or pattern from this game]
2. [Second distinct lesson]
3. [Third only if genuinely distinct]"""


def generate_game_report(header, num_plies: int,
                          phase_stats: str, notable_moments: str) -> str:
    """Structured per-game report: phase analysis, annotated key moments, verdict.

    A Pro feature -- more structured and longer than generate_rich_narrative()
    (which is the free on-demand narrative). Both can coexist for the same game.
    """
    prompt = _build_game_report_prompt(header, num_plies, phase_stats, notable_moments)
    return contextualize(prompt, max_tokens=1600)


def annotate_position(fen: str, eval_cp: int | None = None,
                      engine_best_san: str | None = None,
                      user_comment: str | None = None) -> str:
    """Write 1-3 sentences of concrete chess commentary for a single position.

    eval_cp is from the side-to-move's perspective (positive = current player
    is better), matching the convention used throughout the rest of the app.
    Called from the variation annotation panel -- always on-demand, one click
    per position, never batch-run.
    """
    eval_str = f"{eval_cp / 100:+.2f}" if eval_cp is not None else "unknown"
    lines = [f"Position (FEN): {fen}"]
    if eval_cp is not None:
        lines.append(f"Engine evaluation (centipawns, side-to-move perspective): {eval_str}")
    if engine_best_san:
        lines.append(f"Engine's top move from here: {engine_best_san}")
    if user_comment:
        lines.append(f"Player's own note: \"{user_comment}\"")

    prompt = f"""Write exactly 1-3 sentences annotating this chess position. Be specific and concrete — name the strategic theme, tactical motif, or pawn-structure implication. Do not repeat the player's note verbatim; you may extend or contextualise it. No filler phrases.

{chr(10).join(lines)}

Annotation:"""
    return contextualize(prompt, max_tokens=150)
