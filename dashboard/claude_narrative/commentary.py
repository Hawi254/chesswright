"""Opening and opponent commentary -- one of four topic modules split out
of the former dashboard/claude_narrative.py.
"""
from .client import contextualize, PERSONA_AND_STYLE, _completeness_note


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


def _build_scouting_notes_prompt(username, repertoire_df, n_games):
    lines = "\n".join(
        f"  - {r.opening} ({r.color}): {r.n_games} games, {r.score_pct:.1f}% score, "
        f"ACPL {r.avg_cpl:.1f}, {r.blunder_pct:.1f}% blunder rate"
        for r in repertoire_df.itertuples()
    ) or "  (no openings with 3+ analysed games yet)"

    return f"""You are writing a short scouting summary of a lichess opponent's
recent games, for a player preparing to face them. Address the reader as "you".

{PERSONA_AND_STYLE}

STRICT FACTUAL RULES, do not violate these:
- Only use the repertoire rows listed below. Do not invent openings, ratings, or
  any statistic not given here.
- Do not invent games, results, or comparisons to other players.

Opponent: {username} -- {n_games} game(s) analysed.

Repertoire by opening and color (openings with 3+ analysed games):
{lines}

Write 2-3 short paragraphs identifying what {username} tends to play, where their
scores are weakest, and which opening/color pairing looks most worth preparing
against based on blunder rate and score together -- not a recap of every row, a
real synthesis of what the numbers add up to."""


def generate_scouting_notes(username, repertoire_df, n_games):
    prompt = _build_scouting_notes_prompt(username, repertoire_df, n_games)
    return contextualize(prompt)
