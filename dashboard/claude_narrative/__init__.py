"""
Phase 6 Build Order step 4 (final piece) -- on-demand Claude API narrative.
See client.py's module docstring for the full hybrid-design/API-key
reasoning; this __init__.py just re-exports every public name from the
package's five submodules (client, game_narrative, commentary,
insights_and_coaching, ask) so every existing call site
(`import claude_narrative; claude_narrative.generate_opening_commentary(...)`)
keeps working unchanged after the largest-file modularization split
(2026-07-17) that turned this from one 580-line file into a package.
"""
import anthropic  # noqa: F401 -- re-exposed so `claude_narrative.anthropic.*` still resolves
import api_key_store  # noqa: F401 -- re-exposed so `claude_narrative.api_key_store.*` still resolves

from .client import (
    MODEL, PERSONA_AND_STYLE, MissingApiKeyError, api_key_available,
    contextualize, converse,
)
from .game_narrative import (
    generate_rich_narrative, explain_engine_move, generate_game_report,
    annotate_position,
)
from .commentary import (
    generate_opening_commentary, generate_opponent_commentary, generate_scouting_notes,
)
from .insights_and_coaching import generate_insights_synthesis, generate_coaching_recommendations
from .ask import answer_question, answer_question_stream
