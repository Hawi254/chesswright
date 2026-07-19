# Ask — Design

Status: approved by user (design sections), pending spec review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `ask_view.py` ("Ask") as ⛔ not
started, with an explicit note distinguishing it from every other
migration row: "Claude-backed natural-language Q&A — needs its own
API-key/streaming design, not just a data-fetch port." Per explicit user
direction, the Streamlit source (`dashboard/ask_view.py`) was read for
requirements and data-layer understanding only, **not** used as a
visual/interaction template — same posture as the Repertoire Evolution
and Points pages before it.

What the Streamlit page actually does, confirmed by reading
`dashboard/ask_view.py`:

- Free tier: single-turn Q&A. Each question is answered independently —
  Claude receives a pre-assembled "data brief" (headline stats, career
  findings, top openings, phase accuracy, nemesis opponents, missed
  motifs, points ledger, loss causes) and no prior-question context. This
  is a deliberate design choice (per the module docstring), not a gap —
  it's what keeps the free tier distinct from Pro's stateful AI Coach.
- 7 curated preset-question chips, chosen to be answerable from every
  reliably-populated section of the data brief.
- History lives in `st.session_state` — lost on refresh/navigation, never
  written to the DB (arbitrary Q&A doesn't fit the `claude_narratives`
  keyed-subject cache model, and per-question caching wouldn't help since
  each question is different).
- Pro users get the entire page replaced by `chesswright_pro.ai_coach`
  (multi-turn, persistent profile, thumbs up/down) — out of this repo's
  scope per `CLAUDE.md`'s open-core boundary. Free users instead see an
  upsell describing that feature.
- Data-brief assembly (`_build_data_brief`) goes through
  `dashboard/cached_queries.py`'s `@st.cache_data`-wrapped functions —
  Streamlit-coupled, and therefore not reusable as-is from the
  Streamlit-free FastAPI backend (`api/main.py`'s own docstring: "wrapping
  existing, Streamlit-free `dashboard/data/*.py` ... No new business
  logic"). This codebase has a documented past incident of `streamlit`
  leaking into the frozen API's import closure via a transitive import
  (`react_binary_rebuild_streamlit_import_bug_2026-07-14`), so this is a
  real constraint, not a style preference.

## Research

Web research (2026-07-17) on 2026 AI interface UX patterns, specifically
for single-turn, no-memory, grounded-in-data Q&A tools like this one:

- **Chat is the default answer and it's wrong about half the time.**
  Chat threads are cognitively demanding and poorly suited to tasks that
  don't actually require conversation. For single-turn interfaces
  specifically, patterns like Vercel AI SDK's `useCompletion` (one-off
  prompt → completion, no thread) are the better-fitting building block
  than a chat UI.
- **Card-based / "dynamic blocks" layouts** are the emerging alternative
  to chat threads for grounded data-analysis tools: each answer becomes
  an independent, scannable, dismissable card rather than a message in a
  linear scroll. This fits especially well here because the underlying
  data model is already "independent question → independent answer" —
  the UI should say what the backend does, not imply memory that isn't
  there.
- **A chat-bubble UI would actively mislead** users into expecting
  conversational memory (asking a follow-up assuming context carries
  over), which the free tier deliberately does not have. It would also
  duplicate the chat-thread pattern this codebase already uses for Board
  Chat / Pro's AI Coach, blurring rather than sharpening the free/Pro
  distinction.
- **Streaming**: standard architecture is the backend proxying the
  Claude SDK's `messages.stream()` (not `create(stream=True)`, which
  gives raw bytes instead of parsed events) as Server-Sent Events to the
  browser. Because the request needs a POST body (the question), the
  browser's native `EventSource` (GET-only) doesn't work — `fetch()` +
  manual `ReadableStream` reading is the standard workaround. Each SSE
  message needs the `data: {...}\n\n` double-newline framing exactly, or
  parsers silently drop events. Mid-stream provider errors (rate limits,
  etc.) should be converted into a terminal stream event rather than
  killing the connection raw, so the frontend can show a clean error
  instead of hanging.

Sources: [Designing AI chat interfaces](https://www.setproduct.com/blog/ai-chat-interface-ui-design), [AI UI Patterns](https://www.patterns.dev/react/ai-ui-patterns/), [From Chatbot to Dashboard: A2UI](https://chartgen.ai/resources/blog/from-chatbot-to-dashboard-a2ui), [UI Patterns That Don't Work for AI-Powered Interfaces](https://altersquare.io/ui-patterns-dont-work-ai-powered-interfaces/), [How to Stream LLM Responses Using FastAPI and SSE](https://blog.gopenai.com/how-to-stream-llm-responses-in-real-time-using-fastapi-and-sse-d2a5a30f2928), [FastAPI Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/), [Streaming Claude agent responses in production](https://www.unpromptedmind.com/streaming-claude-agent-responses-production/).

## Goals

- Answer the same question the Streamlit page answers — a grounded,
  single-turn Q&A tool over the player's real stats — with an interaction
  model that's honest about the single-turn model, not a chat-thread
  port.
- Add streaming, since immediate token-by-token feedback is a real UX
  upgrade over the current spinner-then-reveal and is achievable without
  new business logic (only a new transport for the existing
  `answer_question` call).
- Add cross-visit persistence (localStorage) — a real improvement over
  today's session-only history, at zero backend/DB cost.
- Fix the Streamlit-coupling issue in the data-brief builder as part of
  this work, since the API needs a streamlit-free version anyway.
- Free-tier scope only. Pro's actual multi-turn AI Coach conversation UI
  is out of scope — it lives in the private `chesswright-pro` repo per
  `CLAUDE.md`'s boundary rules. Until it's ported to the React frontend,
  Pro users see this same free-tier tool rather than a dead-end
  placeholder (a deliberate improvement over doing nothing for them).

## Approaches considered

1. **Answer Cards (chosen).** Pinned input (presets + free text) at the
   top; each question becomes an independent card streaming in below,
   newest first. Matches the single-turn data model honestly; matches
   2026 research on card/dynamic-block patterns for grounded analysis
   tools.
2. **Command-palette / spotlight launcher.** Minimal input, one focused
   answer at a time, history in a revisit dropdown. Rejected: hides the
   "ask several things, compare answers" use case the preset chips
   already encourage, and is a bigger visual outlier next to the rest of
   the app's page-based layout.
3. **Classic chat thread (ChatGPT-style bubbles).** Rejected: implies
   conversational memory the backend doesn't have (the exact anti-pattern
   the research flagged), and duplicates the pattern Board Chat/Pro's AI
   Coach already own elsewhere in this app, blurring the free/Pro
   distinction this page exists to preserve.

## Page structure

Top to bottom, single column:

1. Title + one-line explainer (ported from the Streamlit copy: what the
   brief covers, that it's grounded only in analyzed games).
2. Gate chain (in order): no analyzed games → existing thin-data message;
   no Claude key configured → inline message pointing at Settings.
3. **Input zone**, pinned: row of 7 preset chips (ported verbatim from
   `_PRESET_QUESTIONS`), then a free-text input + submit button. Both
   paths call the same `useAskStream.ask(question)`.
4. **First-time single-turn caption**, shown only before the first card
   exists: *"Each question is answered fresh from your stats — it won't
   remember earlier questions."* Defuses the "why didn't it use what I
   just asked" trust problem without permanent chrome once the user has
   the idea.
5. **Card stack**, newest first, directly under the input zone (no
   scrolling needed to see a new answer arrive).
6. "Clear history" action, shown once at least one card exists.

Pro users reach the same page/tool (see Goals) — no separate branch.

## Components

- **`AskPage.tsx`** (`frontend/src/pages/AskPage.tsx`) — page shell,
  owns the gate chain, renders input zone + card stack via
  `useAskStream`.
- **`AnswerCard.tsx`** — one per question. Question as a small heading,
  answer body rendered via `ReactMarkdown` (matching `NarrativePanel.tsx`'s
  existing convention for Claude-generated text), relative timestamp.
  Three visual states: `streaming` (live text as deltas arrive, brief
  "thinking…" before the first token), `settled`, `error` (message +
  Retry, see Error handling).
- **`useAskStream.ts`** hook — owns `cards: AskCard[]`; `ask(question)`
  appends a placeholder card, opens the SSE stream, patches that card's
  text on each delta; `retry(cardId)`; `clearHistory()`. Persists
  `cards` to `localStorage` under `chesswright.ask.history` (capped at
  the most recent 20) on every settle; hydrates on mount. Uses an
  `AbortController` per in-flight request, aborted on unmount.
- Preset chips reuse whatever button/chip primitive the codebase already
  has for this shape (survey existing components at implementation time
  rather than inventing a new one).

## Data flow / API

Backend, two changes:

1. **Extract `dashboard/data/ask_brief.py::build_ask_data_brief(duck_conn,
   sqlite_conn)`** — the streamlit-free brief-assembly logic currently
   inlined in `ask_view.py::_build_data_brief`, calling the same
   underlying `data.get_*` functions `cached_queries.py` already wraps
   (`get_openings_table`, `get_phase_accuracy`, `get_nemesis_opponents`,
   `get_motif_breakdown`, `summarize_buckets`, etc.) plus the equivalent
   uncached headline-stats/career-findings/points-ledger calls.
   `ask_view.py`'s `@st.cache_data`-wrapped `_build_data_brief` becomes a
   thin pass-through to this function, so Streamlit behavior (including
   cache-clear-on-refresh) is unchanged.
2. **New streaming endpoint `POST /api/ask/stream`** in `api/main.py`:
   - Request: `{"question": "<text>"}`.
   - Checks `claude_narrative.api_key_available()` up front; returns a
     normal JSON 4xx if missing (no half-open stream).
   - Builds the brief through a new `_ask_brief_cache = _TTLCache(60)`
     entry, matching every other cache already in `api/main.py`.
   - New `claude_narrative.answer_question_stream(question, data_brief)`
     using the Anthropic SDK's `messages.stream()` context manager,
     yielding text deltas.
   - Streams `data: {"delta": "<text>"}\n\n` per chunk, then a final
     `data: {"done": true, "answer": "<full text>"}\n\n` (the full text
     doubles as a safety net against client-side accumulation drift and
     gives the frontend a clean string to persist).
   - A mid-stream Claude error emits a terminal
     `data: {"error": "<message>"}\n\n` event instead of dropping the
     connection.
3. No new DB writes, no new tables — history persistence is
   client-side-only (localStorage), consistent with the existing
   decision not to fit arbitrary Q&A into the `claude_narratives` cache
   model.

Frontend: `useAskStream` calls `fetch('/api/ask/stream', {method:
'POST', ...})` and reads the response body via
`response.body.getReader()`, parsing `data: ...\n\n` frames manually
(not the native `EventSource`, since it can't POST a body).

## Error handling

- No analyzed games / no Claude key: static gates before the tool
  renders, no wasted request (unchanged from today's pattern elsewhere
  in the app).
- Card-level failure (network drop, mid-stream `error` event, non-2xx
  response): that card alone flips to `error` state with its message and
  a Retry action. Other cards and the input zone are unaffected. An
  `error`-state card is **not** persisted to localStorage, so a stale
  failure doesn't survive a reload.
- Navigating away mid-stream: the hook's `AbortController` aborts on
  unmount, preventing a dangling connection or a post-unmount state
  update.

## Testing

Backend (pytest):
- Golden-text test asserting `build_ask_data_brief()` produces output
  identical to today's `_build_data_brief` for a fixed fixture DB — guards
  the extraction refactor.
- `ask_view.py`'s existing behavior unaffected (thin wrapper now).
- `/api/ask/stream`: happy path (SSE chunks assemble to the expected
  answer), missing-key 4xx, mid-stream error event.

Frontend (Vitest, matching every other page/component in this
codebase):
- `AskPage.test.tsx`: the three gates, preset-chip submission.
- `AnswerCard.test.tsx`: streaming / settled / error visual states.
- `useAskStream.test.ts`: mocked `fetch` + `ReadableStream` for delta
  accumulation, localStorage persistence/hydration (capped at 20),
  abort-on-unmount.

Live verification (`verify` skill, real dev `chess.db`): submit a preset
question and watch it stream, reload and confirm history survived,
force a failure (e.g. temporarily invalid key) and confirm the per-card
error path.

## Decisions

1. Answer Cards over command-palette or chat-thread (research-driven,
   see Approaches considered).
2. Streaming via `fetch` + manual SSE parsing, not native `EventSource`
   (POST body requirement).
3. localStorage persistence, capped at 20 cards, no new DB table.
4. Pro users see the same free-tier tool as an interim fallback, not a
   placeholder, until AI Coach itself is ported to the React frontend.
5. Data-brief assembly extracted to a new streamlit-free module as part
   of this work, not deferred — the API needs it either way.
