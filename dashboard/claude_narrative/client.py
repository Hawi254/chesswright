"""Phase 6 Build Order step 4 (final piece) -- on-demand Claude API narrative.
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

This is the leaf module every other submodule in this package imports
FROM -- it never imports from a sibling topic module (game_narrative.py,
commentary.py, insights_and_coaching.py, ask.py) or back through
__init__.py, which is what keeps this package's import graph acyclic.
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


def converse(messages, system=None, system_suffix=None, tools=None, model=MODEL, max_tokens=1024):
    """Multi-round conversational entry point for AI Coach (a later, private
    chesswright_pro phase builds the tool loop and prompts on top of this).
    Unlike contextualize(), this is not single-shot: messages carries the
    full conversation history (content can be a plain string or a list of
    structured blocks, since tool_result/tool_use blocks are structured),
    and the RAW response object is returned -- not response.content[0].text
    -- because a tool-loop caller needs response.stop_reason and to inspect
    response.content for tool_use blocks.

    Prompt caching: system is ALWAYS wrapped in the Anthropic cache_control
    ephemeral form when given, regardless of whether tools is also given.
    This used to be gated on `tools is not None` -- the reasoning at the
    time was "a bare single-shot system string has no prefix to reuse" --
    but that reasoning doesn't hold for this function's real callers: every
    actual caller of converse() with a system prompt is inside a multi-round
    loop (ai_coach.py's and board_chat.py's run_turn()), including the
    forced-final round each of those loops makes with tools=None after
    MAX_TOOL_ROUNDS is hit. Under the old gating, that final round -- the
    single most expensive round of the turn, since it's the one carrying
    the full system string -- silently lost its cache_control breakpoint
    and paid full price with no cache read, even though the exact same
    system text was cached under cache_control in every prior round of the
    same turn (a cache_control breakpoint is what triggers the read lookup,
    not just the write; omit it and the matching prior-round prefix is
    never looked up at all). Confirmed by grepping every converse() call
    site in both chess_app and chesswright-pro: none rely on system being
    sent as an uncached plain string, so decoupling this from `tools` is
    purely a caching-correctness fix, not a behavior change for any caller.

    The LAST tool schema also gets cache_control (a single breakpoint
    caches everything before it -- the standard recipe), independently of
    the system-caching decision above.

    system_suffix (optional): a second, small system block appended AFTER
    the cached `system` block, itself left uncached -- the "shared prefix,
    varying suffix" caching pattern, for a caller whose system prompt has a
    large stable portion and a small per-turn-volatile portion (e.g.
    board_chat.py's current_fen sentence, which changes every time the
    player navigates to a different board position and would otherwise
    bust the whole cached block if it were concatenated inside `system`
    itself). Only meaningful when `system` is also given; a bare
    system_suffix with no system is silently ignored, mirroring how a bare
    `tools=[]` with no schemas is already a no-op above.

    Confirmed against this repo's pinned `anthropic==0.111.0`
    (requirements.txt): cache_control on system/tools content blocks has
    been a stable, non-beta feature of the Messages API for a long time,
    well predating this SDK version, so no beta header or fallback is
    needed here.
    """
    api_key = api_key_store.get_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "No Anthropic API key configured. Add your own key on the Settings "
            "page to enable this feature.")

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    if system is not None:
        blocks = [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
        if system_suffix is not None:
            blocks.append({"type": "text", "text": system_suffix})
        kwargs["system"] = blocks

    if tools is not None:
        tools = [dict(t) for t in tools]
        if tools:
            tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        kwargs["tools"] = tools

    return client.messages.create(**kwargs)
