"""The Ask-page free-text question prompt/generate pair -- one of four
topic modules split out of the former dashboard/claude_narrative.py.
"""
import app_capabilities

from .client import contextualize, PERSONA_AND_STYLE


def _build_ask_prompt(question: str, data_brief: str) -> str:
    capabilities_block = app_capabilities.format_capabilities_block()
    return f"""You are a chess analysis assistant helping a player understand their personal game history.

{PERSONA_AND_STYLE}

STRICT RULES — do not violate these:
- Answer using ONLY the data provided in the section below. Do not invent statistics, trends, or comparisons not present in the data.
- If the question asks about something not covered (a specific game, a specific date, individual move sequences), say so explicitly and name the real page(s) below that come closest, from this list of what the app actually offers:
{capabilities_block}
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
