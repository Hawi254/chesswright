# Game Detail Slice 6 — Board Chat

Status: approved by user 2026-07-14
Branch: worktree-frontend-spike

## Context

`docs/superpowers/specs/2026-07-13-game-detail-completion-design.md`
sequenced the remaining Game Detail work into six slices. Slices 1-5
(board-interaction infra, interactive board + variation mode, saved
variations, annotations, Game Report) are all shipped. This is the
**last** slice: **Board Chat** — a Pro-gated, game-scoped, multi-turn
Claude conversation about the position currently on screen, with
arrows/highlights drawn on the board as Claude answers.

The Streamlit reference (`dashboard/game_detail_view.py`'s
`_render_board_and_chat`, `chesswright_pro/board_chat.py`'s `render()`)
is a source for business logic and requirements only, per the standing
directive — its `st.session_state`/`st.rerun(scope="fragment")`/
`st.chat_message` control flow does not carry over.

**Cross-repo scope, same shape as Game Report:** the agentic tool loop
(5 tools — `show_arrow`, `highlight_squares`, `get_position_eval`,
`check_move_sequence`, `show_plan` — plus `report_capability_gap`) lives
in the private `chesswright_pro/board_chat.py`. The plain CRUD layer
(`dashboard/data/board_chat.py`: conversations, turns, feedback,
capability gaps) is already in the public repo, already Streamlit-free,
and needs **no changes**. The DB schema (migrations 0036, 0037) already
exists — no new migration.

Unlike Annotations, the Streamlit version mounts Board Chat **once**,
grounded on whichever position is currently on screen (mainline or a
loaded variation) via a single `active_fen` — not a mainline+variation
dual mount.

## Goals

- Let the user have a multi-turn conversation with Claude about the
  exact position on screen, with all 5 tools + capability-gap logging,
  gated on Pro license + Claude API key availability.
- Preserve resume-past-conversation and thumbs up/down feedback.
- Reuse the `pro-status`/Claude-key-status gating pattern Game Report
  established.

## Key decisions (from this session's brainstorm)

1. **Blocking POST, not streaming.** `run_turn()` can take up to
   `MAX_TOOL_ROUNDS + 1` (5) sequential Claude calls per turn — slow,
   but FastAPI's sync `def` routes run in a threadpool automatically, so
   a long call doesn't block the rest of the app. Matches the precedent
   already set twice (Game Report generate, Annotation ai-comment).
   Streaming would require turning `run_turn()`'s loop into a generator
   plus new SSE client plumbing nothing else in this app has — real
   added surface area for the final slice, for a UX gain no other
   Claude-backed feature here currently offers either. Confirmed by web
   research: chess-AI-chat precedent (ChessCoach) and general 2026
   AI-chat-UX guidance both favor workflow-embedded, blocking-is-fine
   patterns over inventing new infra for one feature.
2. **Embedded panel, not a dedicated page/route.** Board Chat's entire
   value is being grounded in the *exact* position on screen right now;
   navigating to a separate route breaks that. Matches every other Game
   Detail slice's placement and avoids the page-level Pro-gating
   mechanism Slice 5 explicitly deferred.
3. **Full feature parity**, not a trimmed MVP — all 5 tools, resume,
   feedback, capability-gap logging. This is the last slice; there's no
   future pass to defer the rest to.
4. **Message history is reconstructed from the DB every turn**, not kept
   in server-side session state. Streamlit keeps the rich Anthropic-shape
   history (including past tool_use/tool_result blocks) alive in
   `st.session_state` for a live session, only falling back to
   plain-text reconstruction via `get_conversation_messages()` when
   resuming a *past* conversation after a reload. FastAPI has no
   equivalent session, so every turn uses that same reconstruction path
   uniformly: Claude sees its own past *answers* as plain text, but not
   its own past *tool calls*, within a conversation. This is already
   exactly what happens today on every resumed Streamlit conversation —
   applying it uniformly costs nothing new and keeps the backend fully
   stateless per-request, matching Slice 1's "DB is the persistence
   layer, no session-key equivalent" precedent.

## Backend: `chesswright-pro` repo change

One new function in `chesswright_pro/board_chat.py`, alongside the
existing (unchanged) `render()`:

```python
def run_chat_turn(duck_conn, sqlite_conn, game_id: str, conversation_id: int,
                   question: str, current_fen: str) -> dict:
    """Streamlit-free entry point for the FastAPI port. Persists the user
    turn, reconstructs history from the DB (see "message history"
    decision above), runs the tool loop, persists the assistant turn +
    any capability gaps, returns the trimmed display-ready result."""
    data_board_chat.add_turn(sqlite_conn, conversation_id, "user", question)
    messages = data_board_chat.get_conversation_messages(sqlite_conn, conversation_id)
    game_brief = _build_game_brief(sqlite_conn, game_id)
    stable_system, system_suffix = _build_system_prompt(game_brief, current_fen)
    answer_text, _, side_effects = run_turn(
        duck_conn, sqlite_conn, messages, stable_system, {},
        current_fen=current_fen, system_suffix=system_suffix)

    arrows, highlights = _trim_board_directives(side_effects["board_directives"])
    plan_arrows = _trim_plan_arrows(side_effects["plan_arrows"])
    directives_json = (json.dumps(side_effects["board_directives"])
                        if side_effects["board_directives"] else None)
    turn_id = data_board_chat.add_turn(
        sqlite_conn, conversation_id, "assistant", answer_text, directives_json)
    for gap in side_effects["gap_reports"]:
        data_board_chat.record_capability_gap(
            sqlite_conn, turn_id, gap["question_summary"], gap["missing_data_description"])

    return {
        "turn_id": turn_id,
        "answer_text": answer_text,
        "arrows": plan_arrows if plan_arrows else arrows,  # same "plan
        # subsumes single-move arrows" precedence render() already uses
        "highlights": highlights,
    }
```

Game brief is rebuilt fresh every turn (one cheap query) rather than
cached — FastAPI has no rerun tax to amortize against, unlike Streamlit.

`_resume_conversation()` already does everything a resume endpoint
needs and is already Streamlit-free — rename it to `resume_conversation`
(drop the leading underscore) to make it a public entry point; update
its two in-module call sites (`render()`,
`_render_resume_past_conversation()`) accordingly. No new pro-repo
function needed for resume.

## Backend: FastAPI endpoints (`api/main.py`, public repo)

```python
@app.get("/api/games/{game_id}/board-chat/conversations")
def list_board_chat_conversations(game_id: str):
    sqlite_conn, _ = get_db_connections()
    return {"conversations": data_board_chat.list_conversations_for_game(sqlite_conn, game_id)}

@app.get("/api/games/{game_id}/board-chat/conversations/{conversation_id}")
def resume_board_chat_conversation(conversation_id: int, current_fen: str):
    sqlite_conn, duck_conn = get_db_connections()
    try:
        from chesswright_pro import board_chat
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")
    return board_chat.resume_conversation(sqlite_conn, conversation_id, current_fen)

@app.post("/api/games/{game_id}/board-chat/turns")
def post_board_chat_turn(game_id: str, body: BoardChatTurnRequest):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import board_chat
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")

    sqlite_conn, duck_conn = get_db_connections()
    conversation_id = body.conversation_id
    if conversation_id is None:
        conversation_id = data_board_chat.start_conversation(sqlite_conn, game_id)
    try:
        result = board_chat.run_chat_turn(
            duck_conn, sqlite_conn, game_id, conversation_id, body.question, body.current_fen)
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    return {"conversation_id": conversation_id, **result}

@app.post("/api/board-chat/turns/{turn_id}/feedback")
def post_board_chat_feedback(turn_id: int, body: BoardChatFeedbackRequest):
    sqlite_conn, _ = get_db_connections()
    data_board_chat.record_feedback(sqlite_conn, turn_id, body.feedback)
    if body.feedback == -1 and body.question_summary:
        data_board_chat.record_capability_gap(
            sqlite_conn, turn_id, body.question_summary,
            "player marked this answer unhelpful")
    return {"ok": True}
```

`question_summary` for the thumbs-down capability gap is supplied by the
**frontend**, not re-derived server-side — the client already holds the
full display history to render the transcript, so it already knows the
preceding user question when it renders the thumbs-down button. This
avoids adding a new DB query the data layer doesn't already have, and
mirrors exactly how Streamlit's `render()` derives it from its own
client-side (`session_state`) display history rather than a fresh query.

No schema changes. `import json`, `data_board_chat` (aliased import of
`dashboard.data.board_chat`), `claude_narrative`, and `pro_gate` are all
already imported/used elsewhere in `api/main.py`.

## Frontend

**`useBoardChat(gameId)` hook** (`frontend/src/hooks/useBoardChat.ts`):
```ts
{
  displayHistory: Array<{ role: 'user'|'assistant', content: string, turnId: number|null }>
  conversationId: number | null
  sending: boolean; error: string | null
  pastConversations: Array<{ id: number, started_at: string, turn_count: number }>
  arrows: Array<{from: string, to: string, color: string}>
  highlights: Record<string, { background: string }>
  sendMessage(question: string, currentFen: string): void
  loadPastConversations(): void
  resumeConversation(conversationId: number, currentFen: string): void
  sendFeedback(turnId: number, feedback: 1 | -1): void
}
```
`sendFeedback` derives `question_summary` by walking back through the
hook's own `displayHistory` to the nearest preceding `role: 'user'`
entry — same derivation `render()` does client-side, just living in
this hook instead.

**`BoardChatPanel` component** (mirrors `AnnotationPanel`/
`GameReportPanel`'s gate structure):
- `useProStatus()` / `useClaudeKeyStatus()` called unconditionally
  (hooks-rules-safe), same precedence as `GameReportPanel`: `!proActive`
  → upsell info box (verbatim Streamlit copy, Gumroad link);
  `proActive && !claudeKeyAvailable` → "Add your Anthropic API key..."
  message; nothing else renders in either case.
- Otherwise: past-conversations list (only shown when
  `conversationId === null` and `displayHistory` is empty — "N past
  conversations" expander + Resume button per row, same list-with-Load
  idiom as `SavedVariationsPanel`), scrollable chat transcript
  (user/assistant bubbles), thumbs up/down on assistant bubbles wired to
  `sendFeedback`, text input + Send button (disabled while empty or
  `sending`; label reads "Claude is thinking…" while `sending` — the
  loading affordance for the blocking POST, no separate spinner), inline
  error text on failure (matches `AnnotationPanel`'s `aiError` pattern).

**Wiring into `GameDetailPage`:** single mount (not a mainline+variation
dual mount like `AnnotationPanel`), fed `boardFen` (the page's existing
`variation.active ? variation.currentFen : mainlineFen`, i.e. exactly
what Streamlit's `active_fen` computes) as `currentFen`.

`arrows` prop on the page's one `Chessboard` mount becomes
`[...engineArrows, ...boardChat.arrows]` — **concatenated, not
replaced**. Slice 1's design doc explicitly anticipated this: "whatever
produces arrows/highlights later... just sets normal state that flows
straight down." `highlightedSquares={boardChat.highlights}` — Board Chat
is the first real consumer of that prop since Slice 1 added it.

## Non-goals

- Streaming responses (see decision 1 above).
- A dedicated Board Chat page/route (see decision 2 above).
- Fixing the pre-existing limitation that `plan_arrows` (from
  `show_plan`) are not persisted, so resuming a past conversation cannot
  redisplay a drawn plan — carried over unchanged, already documented in
  `chesswright_pro/board_chat.py`'s own `render()` docstring.
- Any change to `chesswright_pro/board_chat.py`'s existing `render()` /
  Streamlit UI — left exactly as-is; this slice only adds a sibling
  entry point, same posture as Slice 5's `game_report.generate_report()`.

## Testing

- `chesswright-pro/tests/test_board_chat.py` additions: `run_chat_turn()`
  happy path (persists user turn, reconstructs messages from the DB,
  calls `run_turn()`, persists assistant turn + directives + gaps,
  returns the plan-overrides-arrows trimmed result), `MissingApiKeyError`
  propagation; `resume_conversation()` rename — existing tests updated
  to the new public name, behavior unchanged.
- `tests/integration/test_api_board_chat.py` (public repo, new): list
  conversations empty/populated; resume conversation 200 with
  `display_history`/`arrows`/`highlights`; `POST turns` happy path + 403
  (not licensed) + 501 (mocked `ImportError`) + 503/502; `POST feedback`
  +1/-1, confirms -1 with a `question_summary` also writes a capability
  gap row.
- `frontend/src/hooks/useBoardChat.test.ts`: send/resume/feedback state
  transitions, error states, arrows/highlights merge (plan overrides
  single-move arrows).
- `frontend/src/components/BoardChatPanel.test.tsx`: all 4 gate states,
  past-conversations list only shown pre-first-message, thumbs buttons
  call `sendFeedback` with the right `turnId`/`questionSummary`.
- `frontend/src/pages/GameDetailPage.test.tsx`: panel mounted once (not
  duplicated per variation-mode like `AnnotationPanel`), `arrows` prop
  reflects concatenation when both an engine-analysis arrow and a Board
  Chat arrow are present.

## Open items for the implementation plan to resolve

- Exact copy for the past-conversations empty/populated states and the
  "Claude is thinking…" Send-button label — port verbatim from
  Streamlit where equivalent copy exists, write fresh where it doesn't.
- HTTP status for `record_feedback`'s existing `ValueError` cases
  (unknown `turn_id`, feedback on a non-assistant turn, invalid feedback
  value) — decide at implementation time by checking how other
  `api/main.py` endpoints already map a data-layer `ValueError`/
  `IndexError` to a status code (e.g. Game Report's `IndexError` → 404)
  rather than inventing a new convention.
- Confirm the `chesswright-pro` local editable install round-trips
  `run_chat_turn()` without a reinstall step — same open item Slice 5
  flagged, still generally unresolved, check once at implementation
  time rather than per-slice.
