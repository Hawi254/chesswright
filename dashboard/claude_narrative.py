"""
Phase 6 Build Order step 4 (final piece) -- on-demand Claude API narrative.
Generalized in the Claude-contextualization extension (2026-06) from a
single per-game caller into a shared "contextualize any bounded summary"
module: every touchpoint builds its own small, factual prompt from data
it already has, then calls the one shared `contextualize()` -- no
touchpoint reimplements its own API call.

Hybrid design, unchanged from the original per-game version and applied
to every caller added since: a free template version is the default,
always-available output (narrative.py for games; the existing table rows
for openings/opponents). Claude is explicitly on-demand only -- called
only when the user clicks a button for one specific subject (one game,
one opening, one opponent), never pre-generated or batch-run across the
dataset, and never given raw bulk data -- only the small precomputed
summary for that one subject.

API key: each user supplies their own (BRIEF.md S3) -- this project
cannot pay for every installer's Claude usage the way the original
personal project's single ANTHROPIC_API_KEY env var did. Read via
api_key_store.get_api_key(), which checks the OS-native credential
store first (keyring), a local plaintext fallback second, and the
ANTHROPIC_API_KEY env var last (kept for technical users/CI). Set via
the Settings page, never hardcoded, never logged.
"""
import anthropic

import api_key_store

MODEL = "claude-sonnet-4-6"


class MissingApiKeyError(Exception):
    pass


def api_key_available():
    return bool(api_key_store.get_api_key())


def contextualize(prompt, max_tokens=600):
    """The one shared API call point. Every caller below builds its own
    prompt from its own small bounded summary, then calls this -- adding
    a new touchpoint should never mean writing a new anthropic.Anthropic()
    call."""
    api_key = api_key_store.get_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "No Anthropic API key configured. Add your own key on the Settings "
            "page to enable this feature.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


PERSONA_AND_STYLE = """VOICE: Write as a seasoned grandmaster-commentator would -- the voice of
someone who has played and analyzed thousands of serious games and isn't
afraid to render a real verdict on what the numbers mean. Confident,
vivid, a little wry when the moment calls for it -- never a flat
statistical recital, and never condescending or talking down to the
player as a beginner. Address the player as a fellow serious competitor,
not a student.

GLOSSARY -- use these terms naturally wherever they're relevant, and
make sure a reader unfamiliar with the jargon could still follow along:
a brief in-sentence clarification the FIRST time a term appears in your
response is enough (e.g. "your ACPL -- average centipawn loss, the
standard measure of move accuracy -- was..."); don't define a term twice,
and don't add a separate glossary section of your own.
- ACPL (Average Centipawn Loss): the average amount of evaluation lost
  per move compared to the engine's best move, in hundredths of a pawn
  -- lower means more accurate play.
- CPL (Centipawn Loss): the same measure for a single move.
- Blunder / mistake / inaccuracy: increasingly mild severity tiers for a
  bad move, classified by how much the position's evaluation worsened.
- Sharpness: how much the best move beats the second-best move in a
  given position -- a high gap means only one move was actually good.
- Win probability: the engine's estimate of this player's chance to
  eventually win, derived from the centipawn evaluation at that moment.
- Score% (for head-to-head opponent records): win% + 0.5 x draw%, the
  standard tournament-scoring convention, so repeated draws against the
  same opponent aren't misread as losses.
"""


def _completeness_note(analyzed_games, total_games):
    """Shared career-wide data-completeness caveat, added to every prompt
    (Claude-API extension, 2026-06) -- only a small fraction of the
    player's full game history has been engine-analyzed at any given
    point (e.g. 185 of 32,295 as of this writing, and this number only
    grows over time as worker.py runs more batches). Win/draw/loss counts
    come from ingestion and are complete for every game regardless of
    analysis status; only CPL/ACPL/blunder-rate numbers depend on the
    engine pass, so only those need the caveat."""
    pct = 100.0 * analyzed_games / total_games if total_games else 0.0
    return (f"Career-wide data completeness: only {analyzed_games:,} of {total_games:,} games "
            f"in the player's full history ({pct:.1f}%) have been engine-analyzed so far. "
            f"Win/draw/loss counts and rates are NOT affected by this -- those are known for "
            f"every game regardless of analysis status, so do not caveat them. Centipawn-loss "
            f"(CPL/ACPL) and blunder-rate numbers ARE affected -- they reflect only this "
            f"partial sample. If you reference an ACPL/CPL/blunder-rate number, add a brief "
            f"one-sentence caveat about this; don't belabor it or repeat it more than once.")


def _game_completeness_note(header, num_plies):
    analyzed_ply = int(header.last_analyzed_ply) if header.last_analyzed_ply else 0
    if header.analysis_status == "done" and analyzed_ply >= num_plies:
        return ""
    return (f"This specific game has only been engine-analyzed through ply {analyzed_ply} of "
            f"{num_plies} -- moves after that have no engine evaluation yet. Don't imply the "
            f"engine looked at the whole game if it didn't, and don't invent evaluations for "
            f"unanalyzed moves.")


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


def _build_opening_prompt(opening_row, baseline_win_pct, analyzed_games, total_games):
    acpl_line = ("not yet analyzed (no engine-analyzed games have reached this opening yet)"
                 if opening_row.n_analyzed == 0 else f"{opening_row.acpl:.1f}")

    return f"""You are writing a short, vivid take on one chess opening in a player's personal
repertoire. The reader is the player, addressed as "you".

{PERSONA_AND_STYLE}

STRICT FACTUAL RULES, do not violate these:
- Do not invent games, ratings, or any detail not explicitly given below.
- Do not invent statistics, percentages, or comparisons to other players or
  rating levels -- nothing like that is given here, so do not write
  anything like that. The only comparison you may make is to the player's
  own overall win rate, given below.

{_completeness_note(analyzed_games, total_games)}

Opening: {opening_row.opening_family}
Color played: {opening_row.player_color}
Games played: {opening_row.n}
Win / draw / loss %: {opening_row.win_pct:.1f}% / {opening_row.draw_pct:.1f}% / \
{100.0 - opening_row.win_pct - opening_row.draw_pct:.1f}%
Average centipawn loss (ACPL) in this opening: {acpl_line}
Player's overall win rate across all games, for comparison: {baseline_win_pct:.1f}%

Write 1-2 short paragraphs about how this opening is actually working out for
the player -- is it over- or under-performing their overall record, is the
sample size large enough to mean much, what kind of story does the number
tell. Be specific about the numbers given, don't pad with generic chess
opening commentary not grounded in these stats."""


def generate_opening_commentary(opening_row, baseline_win_pct, analyzed_games, total_games):
    prompt = _build_opening_prompt(opening_row, baseline_win_pct, analyzed_games, total_games)
    return contextualize(prompt)


def _build_opponent_prompt(opponent_row, baseline_win_pct, analyzed_games, total_games):
    return f"""You are writing a short, vivid take on one head-to-head rivalry in a chess
player's personal game history. The reader is the player, addressed as "you"; the opponent is a
separate, named person.

{PERSONA_AND_STYLE}

STRICT FACTUAL RULES, do not violate these:
- Do not invent games, ratings, or any detail not explicitly given below.
- Do not invent statistics, percentages, or comparisons to other players or
  rating levels -- nothing like that is given here, so do not write
  anything like that. The only comparison you may make is to the player's
  own overall win rate, given below.

{_completeness_note(analyzed_games, total_games)}

Opponent: {opponent_row.opponent_name}
Games played against them: {opponent_row.n}
Record (wins / draws / losses): {opponent_row.wins} / {opponent_row.draws} / {opponent_row.losses}
Score% (win + 0.5*draw, standard tournament scoring): {opponent_row.score_pct:.1f}%
Player's overall win rate across all games, for comparison: {baseline_win_pct:.1f}%

Write 1-2 short paragraphs about this specific rivalry -- nemesis, easy
target, or close to even -- grounded only in the numbers given. Note
explicitly whether the sample size (games played) is large enough to mean
much, or whether it's too small to draw a real conclusion."""


def generate_opponent_commentary(opponent_row, baseline_win_pct, analyzed_games, total_games):
    prompt = _build_opponent_prompt(opponent_row, baseline_win_pct, analyzed_games, total_games)
    return contextualize(prompt)


def _build_insights_prompt(findings, win_pct, analyzed_games, total_games):
    finding_lines = "\n".join(
        f"  - {f['title']}: {f['headline']}. {f['detail']}" for f in findings)

    return f"""You are writing a short "what stands out" summary of a chess player's
analyzed game history, presented to the player as their own results. The reader is the
player, addressed as "you".

{PERSONA_AND_STYLE}

STRICT FACTUAL RULES, do not violate these:
- Only use the findings explicitly listed below. Do not invent games, moves, ratings, or
  any statistic not given here.
- Do not invent comparisons to other players or rating levels -- nothing like that is
  given here, so do not write anything like that.

{_completeness_note(analyzed_games, total_games)}

Player's overall win rate across all games: {win_pct:.1f}%

Findings (each independently computed from however much data is currently analyzed --
some may be missing if there isn't enough data yet for that one):
{finding_lines}

Write 2-3 short paragraphs picking out what genuinely stands out across these findings --
not a recap of every line, a real synthesis of what they add up to. If two findings point
the same direction, say so. If one is based on a small sample, note that briefly rather
than overstating it."""


def generate_insights_synthesis(findings, win_pct, analyzed_games, total_games):
    prompt = _build_insights_prompt(findings, win_pct, analyzed_games, total_games)
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


def _build_coaching_prompt(findings, win_pct, analyzed_games, total_games):
    finding_lines = "\n".join(
        f"  {i + 1}. {f['title']}: {f['headline']}. {f['detail']}"
        for i, f in enumerate(findings))

    return f"""You are a chess coach giving specific, actionable improvement advice.

{PERSONA_AND_STYLE}

STRICT RULES — do not violate these:
- Base ALL recommendations only on the findings explicitly listed below. Do not invent statistics or findings.
- Each recommendation must be concrete and specific — not vague advice like "study tactics" but a named pattern, position type, or drill format.
- 2-3 numbered recommendations only, each 2-3 sentences. No bullet sub-points.
- Address the player as "you" throughout.

{_completeness_note(analyzed_games, total_games)}

Player's overall win rate: {win_pct:.1f}%

Findings (from their analyzed game history):
{finding_lines}

What should this player actually DO to address their biggest weaknesses? Give 2-3 concrete, specific practice recommendations, each grounded in one of the findings above."""


def generate_coaching_recommendations(findings, win_pct, analyzed_games, total_games):
    prompt = _build_coaching_prompt(findings, win_pct, analyzed_games, total_games)
    return contextualize(prompt, max_tokens=450)


def _build_ask_prompt(question: str, data_brief: str) -> str:
    return f"""You are a chess analysis assistant helping a player understand their personal game history.

{PERSONA_AND_STYLE}

STRICT RULES — do not violate these:
- Answer using ONLY the data provided in the section below. Do not invent statistics, trends, or comparisons not present in the data.
- If the question asks about something not covered (a specific game, a specific date, individual move sequences), say so explicitly and name the relevant app page (Game Detail for individual games, Tactical Highlights for specific moves, Patterns & Tendencies for time/phase breakdowns).
- Cite actual numbers from the data. Be specific.
- 2-4 sentences. No headers. Bullet points only if comparing 3+ items makes the answer genuinely clearer as a list.
- Address the player as "you".

--- DATA ---
{data_brief}
--- END DATA ---

Question: {question}

Answer:"""


def answer_question(question: str, data_brief: str) -> str:
    """Answer a free-text career question grounded in a pre-assembled data brief."""
    return contextualize(_build_ask_prompt(question, data_brief), max_tokens=300)


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


