"""Insights-synthesis and coaching-recommendation prompts -- one of four
topic modules split out of the former dashboard/claude_narrative.py.
"""
from .client import contextualize, PERSONA_AND_STYLE, _completeness_note


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
