# Project Brief — Chesswright (working name)

Read this fully before making any changes. This is a **scoping document**
written before any code exists. Nothing in here is a status report of
work done — it's research findings, decisions, and a sequencing plan,
checkpointed with the user before building starts.

## 0. What this project is, and isn't

A distributable desktop version of the existing personal `chess-analyzer`
project (`/home/jasper/Desktop/chess_project/chess-analyzer/`), which
analyzes one lichess player's games with Stockfish and presents findings
in a Streamlit dashboard. That backend is already config-driven by
lichess username (confirmed by reading its `config.yaml` — `player.name`
is a plain string, nothing hardcoded elsewhere in the pipeline), which is
exactly the property that makes "let other people run this on
themselves" possible without a backend rewrite.

This is **not**:
- A hosted/shared service. Local install, local Stockfish, local
  database, per user. Confirmed decision, not open for relitigation
  here.
- A phase of the original project. Separate repo, separate identity,
  separate `CLAUDE.md`/`BRIEF.md`. The original project's brief should
  never need to mention this one beyond a pointer.
- A ground-up GUI rewrite. The plan reuses the existing Streamlit/Plotly
  dashboard, wrapped in a native window — see §2 for why this held up
  under research rather than being assumed.
- A v1-to-public-launch plan. The sequencing is: copy/adapt the backend
  → internal validation → a small real pilot group → only then consider
  wider public release. Mirrors the original project's own pattern of
  validating small before scaling (1-game timing dry run → 20-game batch
  → full backlog).

## 1. Stockfish licensing (GPLv3) — what was actually researched

**The question that mattered most**: does running Stockfish as a
separate OS subprocess, talking only over the UCI text protocol (exactly
what the original project already does — `worker.py` never links
Stockfish into a binary), insulate the wrapping application from GPLv3's
copyleft obligations? This was explicitly flagged as "don't assume the
architecture is favorable just because it looks that way" — so it was
actually checked, not carried over from prior belief.

**What's settled and not in dispute:**
- Stockfish itself is GPLv3. Whenever you distribute Stockfish — as a
  binary, bundled with anything — you must include the GPLv3 license
  text and either the matching source or a clear pointer to it for the
  *exact* binary you're shipping.
- If you modify Stockfish's own source (e.g. a custom NNUE net, patched
  search code) and distribute that, the modified result must also be
  GPLv3 and its source made available. Not optional, not a gray area.

**The actual precedent researched — Stockfish vs. ChessBase (settled
2022-11-07, German court):** this is worth getting right because it's
easy to over-read as "any GUI that talks to Stockfish must be GPL." It
wasn't that. ChessBase's "Fat Fritz 2" and "Houdini 6" were **modified,
undisclosed derivatives** built on Stockfish's own source/NNUE weights,
sold under a closed license with no GPL notice, no source offer. The
settlement required ChessBase to stop distributing those products for a
year, then resume only if fully GPLv3-compliant, plus an
attribution/compliance-officer requirement. This is a much stronger
violation than "my proprietary GUI shells out to an unmodified Stockfish
binary over UCI" — it's closer to "we took Stockfish's code, changed it,
and pretended it was ours."

**The genuinely unsettled part, flagged honestly rather than papered
over:** whether a separate-process/subprocess architecture counts as
GPL's "mere aggregation" (no propagation) or a "combined work" (GPL
propagates to the whole thing) doesn't have a clean, citable legal
answer from this research — it's a real, debated edge case in
GPL/FSF discussions generally, not specific case law for chess engines.
In practice, this exact architecture (closed-source-or-permissively-
licensed GUI, unmodified Stockfish run as a subprocess via UCI) is what
a large fraction of real-world chess GUIs already do (commercial and
free), which is informative as "this is the load-bearing convention the
ecosystem already relies on" but is not the same thing as a legal
guarantee.

**Decision, given the above:**
1. **Never bundle a Stockfish binary inside the installer or download it
   silently on the user's behalf at this stage.** The cleanest, lowest-
   risk position is simply never distributing Stockfish ourselves at
   all — the app auto-detects an existing install (same convenience the
   original project already has via `engine.path: null`), and if none is
   found, the first-run flow links to Stockfish's own official download
   page and walks the user through installing it themselves (one
   sentence, one link, per platform). This sidesteps the GPLv3
   distribution question for this project entirely, by construction —
   we are not the distributor.
2. **Our own code's license (planned: MIT)** stays legally separate from
   Stockfish's GPLv3 under this model, specifically because we never
   ship, modify, or statically link it. Stated explicitly rather than
   left implicit: the backend code being copied into this repo (§5) was
   originally written for the personal `chess-analyzer` project by the
   same person who owns this project, so there's no third-party
   copyright barrier to relicensing that copy as MIT here — this is a
   non-issue, not a real open question, but worth saying outright rather
   than assuming it's obvious.
3. **Explicitly deferred, not rejected**: a future "auto-download a
   vendored, unmodified Stockfish copy at first run for convenience"
   feature, sourced live from Stockfish's own official release URLs (not
   embedded in our installer), with the GPLv3 license text and a source
   pointer shown to the user at that point. This is closer to what's
   commonly done, but it's a real product decision with real legal
   surface, worth revisiting with this plan in hand — not decided here,
   and not needed for the pilot.
4. **Before any genuine public release** (post-pilot, §6), get this
   reviewed by someone with real GPL expertise — this research is solid
   enough to build and pilot on, not solid enough to bet a public launch
   on without a second opinion.

## 2. Packaging — pywebview-wrapped Streamlit, cross-platform

**Confirmed, not just assumed**: wrapping the existing Streamlit/Plotly
dashboard in a `pywebview` native window, rather than a ground-up rewrite
in a different toolkit, is a real, maintained pattern — `pywebview`
itself is cross-platform (Windows/macOS/Linux), and a small existing
library (`streamlit-desktop-app`, PyPI) does almost exactly this:
launches the Streamlit server as a subprocess, opens it in a `pywebview`
window, kills the server when the window closes. No specific gap was
found that would force a different GUI toolkit — the dashboard's actual
interactivity (Plotly charts, `st.dataframe` row-clicks, multi-page
`st.navigation`) all renders inside a webview exactly as it does in a
browser, since it *is* a browser-rendering engine under the hood.
**Recommendation: proceed with this approach**, as the user's framing
suggested, now with research behind it rather than just intuition.

**Real constraints found, not hypothetical:**
- Windows needs the .NET Framework (>4.0, near-universal already) and
  **Edge WebView2** — present by default on current Windows 10/11, but
  worth an explicit first-run check with a clear error message rather
  than a silent crash on an unusual/locked-down corporate machine.
- `streamlit-desktop-app`'s own docs cap supported Python at `3.10–3.12`
  due to PyInstaller limitations as of this research — worth pinning the
  new project's Python version deliberately rather than discovering this
  mid-build.
- PyInstaller needs explicit `--collect-all streamlit --copy-metadata
  streamlit` flags (Streamlit's package layout doesn't auto-detect
  cleanly) — a known, documented gotcha, not a surprise to debug from
  scratch.
- macOS packaging has a real split in community practice: PyInstaller
  works but some guides recommend `py2app` instead for Mac specifically.
  Worth trying PyInstaller first (one tool for all three platforms is
  simpler to maintain) and only reaching for `py2app` if a real Mac
  build surfaces a PyInstaller-specific problem.

**What's realistic to build and verify directly, given this is a Linux
dev machine, vs. what needs a pilot tester:**
- **Linux**: buildable and verifiable directly, end to end, no gap.
- **Windows and macOS**: buildable without owning the hardware, via a
  CI build matrix (e.g. GitHub Actions — free hosted runners exist for
  both, real OS images, not emulation). This produces a real executable/
  app bundle. **It does not verify that it actually runs correctly** —
  code-signing/Gatekeeper warnings on unsigned macOS apps, antivirus
  false-positives on unsigned PyInstaller `.exe`s (a known, common
  pattern, not a sign of an actual bug), and platform-specific path/
  permission quirks can only be caught by someone actually launching the
  built artifact on that OS. **This is exactly what the pilot group is
  for** — recruit pilot testers specifically covering Windows and macOS,
  not just people willing to try it on Linux.
- Plan: set up the CI build matrix early (cheap, mechanical, no design
  judgment needed) so every pilot tester always has a fresh build to
  grab, rather than building this scaffolding under pilot-feedback
  pressure later.

## 3. Bring-your-own Claude API key

The original project's rule — read `ANTHROPIC_API_KEY` from an
environment variable, never a file — was deliberate and right for a
single technical user running everything from a terminal. It's wrong
here: installers of a packaged desktop app are not assumed to know what
an environment variable is, let alone how to set one persistently on
their OS before launching a GUI app.

**Decision**: a Settings screen inside the app itself (a Streamlit page,
consistent with everything else in the UI) where the user pastes their
own Anthropic API key once. Stored via the `keyring` package, which
writes to the OS's native credential store (macOS Keychain, Windows
Credential Manager, Linux Secret Service/`libsecret`) — meaningfully more
secure than a plaintext file, and the closest available equivalent to
the original project's "never written to a file" posture, adapted for a
non-technical, non-terminal user. **Documented fallback**: on a Linux
install with no Secret Service running (happens on some minimal/headless
setups), fall back to a local plaintext file in the user's config
directory, with an explicit on-screen warning that this is less secure —
never silently degrade security without telling the user.

**Every Claude-API-powered feature (narrative generation, findings
synthesis, coaching) must work with no key configured** — show a "add
your own Anthropic API key in Settings to unlock this" message instead
of crashing or silently disabling the page. The free, template-based
narrative (the original project's Phase 6 "hybrid approach" — instant
default summary, on-demand richer Claude prose) is the right pattern to
copy here directly: most of the dashboard's value should never depend on
the user paying for API usage at all.

Reuse the original project's `claude_narrative.py` pattern (one
`contextualize()` call point, one shared persona/style block) as a
starting copy — it's already key-agnostic in design (the key itself is
read at call time, not baked into the module), so the only real change
needed is the source of the key (env var → `keyring`).

## 4. Distribution and update mechanics

**Where people get it**: a public GitHub repository, with built
installers/executables attached to GitHub Releases (the CI build matrix
from §2 produces these automatically per tagged release). This is the
standard, zero-infrastructure-cost distribution point for an open-source
desktop tool, and matches the GPLv3-adjacent posture of §1 (a public repo
naturally satisfies "make source available," even though our own code
doesn't have to be GPL).

**Updates — staged deliberately, not solved all at once:**
- **Pilot phase (now through §6's checkpoint)**: no auto-update
  infrastructure. A lightweight on-launch version check (compare local
  version against the latest GitHub Release tag via GitHub's public API,
  no auth needed for a public repo) that shows "a newer version is
  available — get it here" with a link. Manual re-download, same as
  installing the first time. This is intentionally low-tech: a handful
  of pilot testers can be told directly when something's fixed; building
  real auto-update infrastructure for them isn't worth the cost yet.
- **Deferred to post-pilot, before genuine public release**: real
  signed auto-updates (`tufup` was the most credible option found in
  research — actively maintained, built on the `python-tuf` security
  framework, explicitly created as the replacement for the now-archived
  `PyUpdater`). This requires code-signing infrastructure (at minimum a
  macOS Apple Developer ID for notarization, ideally a Windows
  code-signing cert) that costs real money and isn't justified for a
  handful of pilot installs — but is worth planning for once the
  pilot validates there's a real audience to keep updated.

## 5. Shared-core architecture — copy now, converge later

**The question, stated honestly**: should this new project import the
original project's backend modules (`ingest.py`, `worker.py`,
`annotate.py`, `analytics.py`, `db.py`, `config.py`, `chess_utils.py`,
the `dashboard/` package) as a live shared dependency, or copy them once
and let the two projects diverge independently, converging into a real
shared package later only if it turns out to still make sense?

**Weighed both ways:**
- *For importing now*: avoids duplicating ~10 files' worth of logic;
  any bug fix in one place benefits both projects; less code to read
  when onboarding to either project later.
- *For copying now*: the original project is **explicitly mid a
  multi-week, real, currently-running Stockfish analysis pass** against
  a real personal database (32,295 games, ~31,339 pending as of the most
  recent status in that project's brief) — the user's instruction here
  is that this work must not touch or modify that running pipeline at
  all. A live import (shared `sys.path`, a installed-in-editable-mode
  shared package, even just "the same venv") creates exactly the kind of
  accidental-coupling risk that instruction is trying to prevent — a
  dependency version bump, a renamed function, a shared virtualenv
  conflict, any of which could quietly affect the original project
  without anyone intending it to. Separately, this new project's actual
  needs are already known to diverge soon, not hypothetically: API-key
  storage via `keyring` instead of an env var (§3), no assumption of a
  single long-running multi-week batch job, packaging-aware path
  handling (a config file living next to a frozen executable looks
  different from one living next to a `.py` script), and a first-run
  onboarding flow that doesn't exist in the original project at all
  (§6). A shared package extracted *before* it's clear which of these
  differences are real vs. incidental risks coordinating two projects
  around an abstraction that doesn't fit either of them well yet.

**Decision: copy now, converge later.** Take the backend modules as a
one-time copy into this new repo (no de-hardcoding needed first — the
backend is already config-driven by username, confirmed in §0). Evolve
independently. Revisit extracting a genuinely shared
`chess-analyzer-core` package only after the pilot (§6) has produced
real evidence of what's actually identical between the two projects
versus what needed to diverge — that evidence doesn't exist yet, and
guessing at it now is the premature-abstraction risk, not the
duplication itself.

## 6. Sequencing — phases, not a single launch

This mirrors the original project's own validation discipline (1-game
dry run → 20-game batch → full backlog) applied to *this* project's
actual risk: unknown packaging behavior and unknown real-world onboarding
experience, not unknown engine timing.

**Phase A — Copy and adapt the backend.** Copy the backend modules
(§5) into this repo. Confirm the existing `config.yaml`/`config.py`
pattern needs no changes to support an arbitrary lichess username (it
shouldn't — verify, don't assume). Swap the `ANTHROPIC_API_KEY` env-var
read for a `keyring`-backed Settings page (§3). No packaging yet, no
GUI wrapper yet — runnable via `streamlit run` exactly like the original,
just against an arbitrary username's data. Checkpoint: confirm a real
test username's games can be ingested and analyzed end to end before
moving on.

**Phase A — done (2026-06-23).** Backend + dashboard copied (Findings
page dropped, see S6a). API key handling rebuilt around
`dashboard/api_key_store.py` (keyring → plaintext fallback → env var,
S3). Verified end to end with `--player "SebastianCB"` against
`sample.pgn` (a real opponent in that file, not the original author) —
`ingest.py` correctly computed `player_color='white'`,
`opponent_name='L3-37'`, confirming the config-by-username design holds
with zero leftover hardcoding (grepped for it directly, found none in
actual logic, only in two now-fixed usage-example docstrings). Ran the
real `worker.py` against real Stockfish (auto-detected at
`/usr/games/stockfish`, no install step needed on this dev machine) and
`annotate.py` end to end, then the dashboard's `AppTest` suite against
that tiny (1-game) database.

**Two real bugs found this way, not hypothetical** — both are exactly
the class of bug Phase B's small-starter-batch onboarding design would
otherwise walk every pilot tester straight into, since the original
project's own dataset (tens of thousands of games) never exercised the
small-N path this project's first-run experience is built around:
1. `dashboard/data/openings.py`'s `get_most_repeated_positions()` built
   a SQL `IN (...)` clause from a list that's empty whenever no position
   has been reached `min_games` times yet — guaranteed on a fresh
   install, not a rare case. Fixed: short-circuit to an empty result
   before building the invalid query.
2. `dashboard/matchups_view.py`'s giant-killing panel divided by
   `n_underdog_games`/`n_favorite_games` with no zero-guard — both are
   routinely zero before enough games are analyzed. Fixed: render `--`
   instead of crashing, same pattern `tactical_highlights_view.py`
   already used elsewhere in the same file (confirmed by auditing every
   other inline percentage calculation in `dashboard/` for the same
   pattern — found nothing else missing a guard).

Also fixed in passing: `dashboard/test_app.py`'s determinism test had a
hardcoded original-project `game_id` that doesn't exist in a fresh
database — changed to fetch any real game_id from whatever database is
actually configured. Two remaining `AppTest` failures
(`test_game_explorer_badge_filter_reduces_row_count`,
`test_opening_and_opponent_commentary_buttons_render_correctly`) are
assumptions baked into the *test* about having enough sample data (e.g.
"at least one comeback-badged game exists") — true of the original
project's real dataset, not true of a throwaway 1-game fixture, and not
application bugs. Left as-is rather than force-fitted; worth a real
look once Phase B produces a more realistic (20-50 game) test fixture
instead of this 1-game smoke test.

**Phase B — First-run onboarding experience.** Build the "what to
expect" flow explicitly asked for: before any analysis starts, run a
short live calibration (a handful of real moves on the user's own
hardware, the same kind of timing dry run the original project did
manually) and show a concrete, honest estimate — "at this depth, your
first 20 games will take approximately N minutes" — rather than a vague
warning. Let the user pick a small starter batch (e.g. 20-50 games, not
their whole account) for the first run, with a live progress indicator,
and make sure the dashboard already shows something useful on that
partial data (the existing per-game resumable design already supports
this — confirm, don't rebuild). This phase is explicitly about the
*experience* of a real, accepted slow pipeline, not about making it
faster.

**Phase B — done (2026-06-23).** Built `dashboard/onboarding_view.py`, a
linear wizard (username → Stockfish detection → bounded real-game fetch
→ live calibration → batch-size plan with an honest estimate → run →
done), wired as `app.py`'s forced default landing page on a genuinely
fresh install. Supporting backend additions: `worker.calibrate()`
(measures real avg seconds/move over a small bounded number of real
plies, one continuous engine process, same methodology the production
`run()` loop already uses — not a fresh assumption invented for this),
a bounded `max_games` fetch option added to `sync.py` (lichess's own
`max` API param, so calibration doesn't have to download a power user's
entire history just to measure ten moves), and `config.set_player_name()`
(a targeted text substitution, not a full YAML re-serialize, so the
file's own explanatory comments survive being edited by the wizard).

**Verified live, not just reviewed** — ran the actual wizard end to end
via `AppTest` against a real public lichess account
(`DrNykterstein`/Magnus Carlsen — a real, bounded, read-only fetch of
their 100 most recent games, the same load any real user's onboarding
would put on lichess's API), with the real local Stockfish install,
real network calls, and a real 3-game analysis + annotation batch. Every
step completed with no exceptions on the second pass, after finding and
fixing three real bugs the first pass surfaced — this is exactly the
kind of thing a code-only review would not have caught:

1. **The onboarding default flag was recomputed every rerun, not frozen
   for the session.** `NEEDS_ONBOARDING` was being derived live from
   "zero games / username still CHANGE_ME" — both of which the wizard's
   own *fetch* step flips to false immediately, well before calibration
   or the batch run happen. That risked bouncing the user off the
   wizard and onto a half-built Overview page mid-flow. Fixed: decided
   once per session (cached in `st.session_state`), so only the
   wizard's own explicit "Go to dashboard" button (a real
   `st.switch_page` call) can actually leave Setup once it's started.
2. **A fresh, unmigrated database file has no tables at all** — every
   existing page's queries (`SELECT ... FROM games`) assumed at least
   empty tables exist, true of the original project (always migrated
   well before first dashboard launch) but not true of a from-scratch
   install. Fixed: `app.py` now runs `migrate()` unconditionally before
   anything else touches the database.
3. **`narrative.generate_career_narrative()` and `overview_view.py`'s
   headline metrics crashed on zero analyzed games** (`acpl`/`win_pct`
   are legitimately `None` from a 0-row SQL aggregate, not just
   theoretically possible) — reachable because Overview stays in the
   sidebar throughout onboarding, not hidden during setup. Fixed with
   explicit `None`-aware fallback text/`"--"`, same pattern already
   used elsewhere in the codebase.

A fourth bug from the same "small real dataset" class as Phase A's
findings surfaced on the subsequent full dashboard regression pass (not
the wizard itself): `tactical_highlights_view.py` crashed accessing
`hangs.resigned_quickly` when zero hanging-piece blunders exist yet —
`get_hallucination_blunders()` only adds that column when there's at
least one row. Fixed with the same `if n_total else` guard already used
two lines above it in the same function. `dashboard/test_app.py`'s suite
now passes 6/7 against the real onboarded 3-game database (the last
failure is the same test-fixture-sample-size issue noted in Phase A, not
a new one).

**Two follow-up items checked after the initial pass, per explicit
request rather than left unstated:**

- **Invalid/misspelled username — checked live, not assumed.** A real
  404 from lichess (confirmed against the actual API with a nonexistent
  username) was already being caught by `_render_fetch`'s broad
  `except Exception`, so the wizard never crashed on this — but the
  message shown was `str(e)` verbatim, which includes the raw request
  URL with query params (`...?pgnInJson=false&clocks=true&max=5`), not
  something a non-technical installer should have to parse. Fixed:
  `requests.exceptions.HTTPError` is now caught specifically, with a
  plain "no lichess account found for '...' — check the spelling"
  message for a 404, and a separate plain message for connectivity
  failures (`RequestException`) vs. other HTTP errors. Re-verified live
  against the real API after the fix.

- **Mid-wizard failure / abandonment during the "running" step — a real,
  deliberately UNFIXED gap, flagged rather than silently left absent.**
  `_render_running` launches `worker.py` as a detached `subprocess.Popen`
  and polls the database in a blocking loop for the rest of that script
  execution. If the user closes the browser tab, loses their connection,
  or otherwise abandons the page mid-batch: **the data itself stays
  safe** — the subprocess is not tied to the browser session's lifetime,
  and `worker.py`'s own per-move-commit resumability (already proven
  throughout this project) means a killed or orphaned process loses at
  most its in-flight move, never silent corruption. What's NOT handled:
  there's no surfaced indication to the user that a batch may still be
  running in the background if they come back later — `onboard_step`
  lives in Streamlit's `session_state`, which doesn't survive a real
  page reload, so returning to the app after an abandoned "running" step
  re-evaluates `_already_onboarded()` fresh; if any games are already
  `done` by then, they'll land on the normal "status" shortcut rather
  than anything that says "a batch may already be running, don't start
  a second one." Two real consequences worth naming, not glossing over:
  (a) a confused user might click "Fetch more games and analyze another
  batch" and launch a SECOND `worker.py` subprocess concurrently with an
  still-running first one — both would safely claim different games off
  the same `queue_order`-ordered queue (no double-processing of one
  game, confirmed by reading `fetch_next_game()`'s query), so this is
  wasteful (two engine processes competing for CPU) rather than
  corrupting, but it's not a good experience; (b) there's currently no
  "is a batch already running" check anywhere in the UI. **Deferred
  rather than fixed now**: a real fix (e.g. a PID/lockfile check, or
  surfacing running `analysis_runs` rows with no `ended_at`) is a small
  but genuine feature, not a one-line guard, and didn't seem proportional
  to add speculatively without first knowing whether real pilot testers
  (Phase D) actually hit this in practice. Worth revisiting before Phase
  D if it comes up, or as a fast follow-up regardless before any wider
  release.

**Phase C — Packaging.** `pywebview` wrapper + PyInstaller build for
Linux (build and verify directly) + CI build matrix for Windows/macOS
(build via CI, §2 — verification waits for Phase D). GitHub repo +
Releases set up (§4) at this point, even before any public
announcement, so the CI pipeline has somewhere real to publish to.

**Phase C — Linux build done (2026-06-23).** `desktop_app.py` (new file)
is the packaged entry point — never touches the existing dev workflow
(`streamlit run dashboard/app.py`, still how Phases A/B were built and
tested). `chesswright.spec` is the PyInstaller build config.

**User-data architecture, decided before writing the launcher, not
discovered by accident**: a packaged build's own install directory
can't be trusted to hold a growing personal database (read-only on
Windows, or for `--onefile`, a temp dir wiped between runs). Extended
the per-user `~/.chesswright/` convention `api_key_store.py` already
established (§3) rather than inventing a second one — `config.py` got a
`CHESSWRIGHT_CONFIG_PATH` env var override (unset in dev mode, so
Phases A/B's tested behavior is unchanged) and a `set_database_path()`
helper (same comment-preserving text-substitution approach as
`set_player_name()`, carefully scoped to the `database:` section only —
config.yaml has a second, unrelated `path:` key under `engine:`, and a
naive regex would have silently rewritten whichever one happened to
appear first in the file).

**A real, in-scope bug found and fixed while wiring this up, not
packaging-specific**: `onboarding_view.py`'s batch-run step originally
launched `worker.py` via `subprocess.Popen([sys.executable, "worker.py",
...])` — fine from a source checkout, but `sys.executable` IS the
bundled exe itself once frozen, with no separate `worker.py` script to
run that way. Fixed by adding an `on_game_done` callback to
`worker.run()` and calling it directly in-process (matching how
`calibrate()`/`annotate.run()` were already called), driving the
progress bar without a subprocess at all. Also fixed in the same pass:
`worker.run()`'s missing-engine case called `sys.exit(1)`, which is a
`BaseException` that an in-process caller's `except Exception` would
NOT catch — would have silently killed the whole dashboard server.
Changed to `raise RuntimeError(...)`. **Re-verified the entire wizard
live end to end again after this refactor** (same `AppTest`-against-a-
real-lichess-account method as Phase B), specifically because this
touched the most consequential step, not just packaging glue.

**Three more real bugs found getting the actual PyInstaller build to
run** — each one only surfaced by actually launching the built
executable, never by reading the build log alone, which is exactly why
"build succeeds" and "build works" were kept as separate checkpoints
throughout:
1. `ModuleNotFoundError`/`PackageNotFoundError` for streamlit itself —
   it calls `importlib.metadata` on its own package at import time;
   PyInstaller doesn't bundle a package's METADATA by default, only its
   `.py` source.
2. Once fixed, the server started and bound its port, but every request
   to `/` returned a bare 404 — streamlit's actual frontend (the built
   HTML/JS/CSS under `streamlit/static/`) was missing from the bundle
   entirely. `copy_metadata()` alone doesn't pull this in;
   `collect_all()` does (data files + binaries + submodules together).
3. Once THAT was fixed, the dashboard itself crashed immediately with
   `ModuleNotFoundError: No module named 'chess'` — the direct
   consequence of `dashboard/app.py` and the backend modules being
   loaded dynamically (by file path, via `sys.path`, at runtime — see
   `chesswright.spec`'s own comments) rather than statically `import`ed
   by `desktop_app.py`. PyInstaller's Analysis phase only follows real
   import statements reachable from the entry script, so it never even
   looked at what `dashboard/*.py` or the backend modules need. Fixed by
   explicitly `collect_all()`-ing every third-party package any of them
   import: `chess`, `yaml`, `duckdb`, `pandas`, `matplotlib`,
   `anthropic`, `requests`, `plotly`, `keyring` (already needed
   `streamlit` for the two bugs above). This is the direct cost of the
   dynamic-loading architecture, not a one-off oversight — anything new
   added to `dashboard/` or the backend that imports a not-yet-listed
   third-party package will need adding here too.

**A fourth, separate bug in the launcher's own server-startup
mechanics**, found before even reaching PyInstaller (i.e. real, not a
packaging artifact): `streamlit.web.bootstrap.run()` cannot run on a
background thread — it registers a SIGTERM handler internally, and
Python only permits `signal.signal()` from the main thread of the main
interpreter, full stop, regardless of framework. Tried running
bootstrap in a thread with pywebview on the main thread first (clean
in theory, confirmed broken live); fixed by re-invoking the SAME
executable as a subprocess with an internal `--server-mode` flag — a
standard PyInstaller pattern for "one exe, multiple entry-point
behaviors," not a one-off hack. A related, separate bug in that
subprocess's flag handling: `bootstrap.load_config_options()`'s keys
need UNDERSCORES (`server_port`), not the dotted config-option names
they represent (`server.port`) — confirmed by reading its real source
(`name.replace("_", ".")`), since the dotted version silently fell back
to streamlit's default port 8501 with no error at all.

**Verification method**: an isolated Xvfb virtual display (`:99`), not
the real desktop session — worth flagging explicitly because the first
attempt at this accidentally launched against the user's actual live
`DISPLAY=:0` desktop session before being caught and killed. Every
later test ran with `DISPLAY=:99` + `GDK_BACKEND=x11` (also needed:
`WAYLAND_DISPLAY` being set in the environment made GTK silently try
Wayland first and hang with no window and no error, even with `DISPLAY`
set correctly) + real screenshots (`mss`, since neither `xwd` nor GDK's
own pixbuf-from-window APIs cooperated easily) confirming actual
rendered content, not just "a window object exists." The final
standalone bundle (`dist/chesswright/`, ~880MB, not yet size-optimized)
was launched with zero dependency on the dev venv and showed the real
onboarding wizard correctly.

**A real privacy incident, caught before any damage, not after.**
`sample.pgn` was copied from the original `chess-analyzer` project
during Phase A (§6a never flagged it because the original project's own
`CLAUDE.md` describes it as just "20 known-good games used for smoke-
testing" — true, but it's also real personal data: the original
author's actual lichess username and rating, plus the real usernames of
every opponent in those 20 games). It sat in this repo, untouched, all
the way through Phases A–C. The first attempt to create the public
GitHub repo and push (this section) was **blocked automatically**,
flagging exactly this — real PGN data and a real username headed to a
public destination. Nothing had been pushed yet; the repo was never
even created on GitHub's side. Fixed: `sample.pgn` removed from the
repo and deleted from disk entirely (not just gitignored after the
fact), with an explicit `.gitignore` entry and comment so it can't
silently come back. **Lesson for any future fixture data in this
project**: a file being useful for testing doesn't make it safe to
publish — anything copied from the original personal project needs
this same question asked explicitly (real player data? real opponent
data?) before it ends up in a commit, not caught incidentally by a
safeguard at push time. Test fixtures going forward should be either
freshly fetched from a real public account at test-time (the approach
already used throughout Phases A–C's own live verification, e.g.
`DrNykterstein`) or genuinely synthetic — never a copy of the private
project's real data.

**CI build matrix confirmed working on real Windows and macOS runners
(2026-06-24)**, not just locally on Linux — exactly the verification §2
called "realistic to build without owning the hardware." Triggered
manually (`gh workflow run`) right after the repo went live, rather than
waiting for the first tag push, specifically to find out now whether the
spec file needed Windows/macOS-specific fixes the same way the Linux
build needed three rounds of real fixes (§ above) — it didn't. All three
jobs (`ubuntu-latest`, `windows-latest`, `macos-latest`) succeeded
cleanly on the first attempt: real, correctly-sized artifacts
(Linux 250MB, Windows 142MB, macOS 174MB zipped — all consistent with a
genuine PyInstaller bundle, not an empty or truncated one), and every
warning in all three logs is well-known, benign PyInstaller noise
(pandas/matplotlib pulling in their own test submodules via
`collect_all`, matplotlib's font-cache scan failing to parse one macOS
system font file, generic Windows-library ctypes probes that don't
apply on macOS/Linux and vice versa) — none of it a real error.

**Still genuinely unverified, and this run does not change that**: per
§2's own distinction, a successful CI build proves the artifact exists
and is non-trivial, not that it actually *runs* correctly on that OS —
code-signing/Gatekeeper warnings, antivirus false-positives on an
unsigned `.exe`, and real GTK/WebKit-equivalent backend issues on
Windows/macOS (the kind the Linux build needed real live testing to
catch, not just a successful build) are exactly what Phase D's pilot
testers are still needed for. One concrete, named follow-up the warnings
above point at: `collect_all()` for `pandas`/`matplotlib` is pulling in
their internal test suites, inflating every platform's bundle size for
no real benefit — worth excluding (`*.tests`) as a deliberate
size-optimization pass, not urgent enough to block on now.

**First tagged release, v0.1.0, published 2026-06-24** —
`https://github.com/Hawi254/chesswright/releases/tag/v0.1.0`. This is
the actual download link the README points pilot testers at. A real
bug surfaced on the first attempt, not a packaging one this time: the
tag's first CI run built all three platforms again without issue, but
the `release` job's final step (creating the GitHub Release itself)
failed with a 403 — `"Resource not accessible by integration"`. Root
cause, confirmed by reading the actual error rather than guessing: the
default `GITHUB_TOKEN` GitHub Actions provides is read-only unless a
job explicitly requests write access via a `permissions:` block, and
`build.yml` never had one. Fixed by adding `permissions: contents:
write` to the `release` job specifically (not the whole workflow — no
other job needs it). Since the failed attempt never actually created
anything on GitHub's side (confirmed via `gh release list` before
touching anything further), moving the not-yet-published `v0.1.0` tag
to the fixed commit and re-pushing was safe — no public release history
was rewritten, because none existed yet. The re-run succeeded cleanly;
the release now has all three platform zips attached at their full,
correct sizes (Linux 248MB, macOS 173MB, Windows 142MB).

Also published alongside this release: a real end-user `README.md`
(install steps per platform, the Stockfish-install prerequisite,
expected SmartScreen/Gatekeeper friction on these unsigned builds and
how to get past it, the first-run wizard walkthrough, troubleshooting)
and an MIT `LICENSE` with an explicit note that Stockfish itself stays
under its own GPLv3 and is never bundled — both didn't exist before
this point, and Phase D's "published docs only, no hand-holding" design
depends entirely on them actually existing and being accurate.

**v0.1.1, published 2026-06-24 — a real bug found by actually running
v0.1.0, not by re-reading the CI logs.** `./chesswright` on Linux failed
with `bash: ./chesswright: Permission denied`. Root cause, confirmed by
reading the actual error rather than guessing (same discipline as every
other fix in this log): `actions/upload-artifact` does not preserve
POSIX permission bits — a well-documented GitHub Actions limitation,
not something this workflow did uniquely wrong. The `build` job's
PyInstaller step sets the executable bit on the `chesswright` binary as
part of a normal build; that bit was already gone by the time the
`release` job downloaded the artifact and re-zipped it, so every Linux
and macOS user who downloaded v0.1.0 would have hit this identically —
not an edge case.

Fixed two ways, not one: (1) `chmod +x` re-applied to both the Linux and
macOS binaries immediately before re-zipping in the `release` job: (2) a
new verification step added in the SAME job that unzips the actual
about-to-be-published Linux artifact and checks the bit directly,
failing the build loudly if it's ever missing again — added specifically
so a regression here gets caught by CI, not by the next pilot tester.
Confirmed working by reading that step's own log output on the real
v0.1.1 run, not assumed from the fix alone: `OK: chesswright-linux/
chesswright is executable inside the published zip.`

**Versioning decision, since this was the first time a real bug needed
fixing after a release had genuinely gone out (v0.1.0 was already
published and possibly already downloaded by the time this was
caught)**: cut `v0.1.1` rather than deleting/moving the `v0.1.0` tag the
way the earlier (never-actually-published) release-permissions bug was
handled. Once something is real and public, fix forward with a new
version — rewriting a tag that's already been pointed at is the
destructive operation this project's own working norms (§ CLAUDE.md)
say to avoid without explicit cause. `README.md` needed no change: it
already links to the general `/releases` page (GitHub shows the latest
release first) and references the version-agnostic zip filenames
(`chesswright-linux.zip`, etc.) rather than a pinned version number —
written that way from the start, which turned out to matter the first
time a second release actually happened.
`https://github.com/Hawi254/chesswright/releases/tag/v0.1.1` is the
real, current, fixed release.

**Phase D — Small pilot group (the explicit checkpoint before wider
release).**

**Recruiting and group size (was an accidental gap, not an intentional
deferral — fixed here rather than left in §8):** target **5-6 people**,
recruited directly and personally (people already known to the user, not
a public call-for-testers post — this is a private pilot, not a soft
launch). Composition matters more than headcount: **at least 2 on
Windows, at least 2 on macOS** (covering the two platforms that can only
be verified by a real human, per §2 — one person per platform isn't
enough to tell "this works" from "this one machine happened to work"),
the rest on Linux or doubling up. Ideally people who already have a
real, decent-sized lichess game history themselves — a pilot tester with
3 games can't meaningfully test the onboarding-for-a-real-account
experience Phase B is built around. Install instructions are the
published docs only, no live hand-holding, no Claude-assisted
troubleshooting in the moment — that absence is the actual test of
whether Phase B and Phase C work unsupervised.

**Go/no-go signals, rewritten to actually be falsifiable** (the original
four were directionally right but had no numbers, so a real outcome like
"5 of 6 testers cleanly succeed, 1 hits something" had no defined
verdict — fixed below instead of left ambiguous):

- **Install/first-run success: at least 5 of 6 (≥80%) get through
  install → first analysis run with no *blocking* bug**, where blocking
  is defined narrowly: prevents installing, launching, or completing the
  first analysis batch entirely, with no workaround simpler than editing
  a config file. Cosmetic issues, confusing wording, a slow step that
  works but isn't pleasant — none of these count against this number;
  they go on a fix-it list for Phase E, they don't block it.
- **Explicit exception process for the one tester who doesn't clean up
  the math**: if a failure is traced to a *specific, diagnosed* root
  cause that's reasonably judged not to generalize (the worked example
  that prompted this rewrite: a locked-down corporate Windows machine
  blocking an unsigned `.exe` via group policy) — it does NOT
  automatically block release, but only if **both** of the following are
  true and written down, not silently waived: (1) the root cause is
  actually identified, not guessed at or assumed; (2) it's recorded
  explicitly in this brief (or a Phase D notes file) as an accepted,
  known limitation before Phase E proceeds — the same "flag it, don't
  silently change it" discipline this project already uses for the
  Stockfish depth lock. A failure with an unknown or undiagnosed cause
  always counts against the 80% bar — "probably fine" is not a
  diagnosis.
- **At least one real, successful run confirmed on each of Windows and
  macOS** (not just Linux) — unchanged from the original wording, this
  one was already concrete.
- **No open GPL-compliance question left unresolved from §1.**
- **Timing-estimate accuracy: Phase B's live-calibrated estimate must
  land within 2x of each pilot tester's actual measured time** (e.g. an
  estimate of "20 minutes" failing badly at "code, but every real tester
  took over 40" — fix the estimate, don't ship it as-is). 2x, not a
  tighter bound, because cross-machine hardware variance is real and
  expected; the bar is "not systematically misleading," not "precise."

**Phase E — Wider public release.** Only after Phase D's signals are
genuinely met, not assumed. At this point: revisit §1's GPL question
with real legal input if monetization or wider scale is on the table,
revisit §4's update mechanics for real signed auto-updates, and revisit
§5's shared-core question with actual evidence in hand. None of this is
scoped in detail yet — deliberately, since it depends on what the pilot
actually surfaces.

## 6a. Phase A note — the Findings page was dropped, not adapted

Found while actually copying the dashboard package (not anticipated when
this brief was first drafted): `dashboard/findings_view.py` depends on
two things that don't generalize to an arbitrary user — a hand-curated
`FINDINGS.md` (the original author's own prose write-up of their
results) and the entire `analysis/` directory (run as a subprocess for
the "current numbers" refresh), neither of which §5 scoped for copying,
deliberately, since both are specific to the original project's own
multi-month research process, not reusable as-is for someone installing
this fresh.

**Decision: drop the page for v1, don't fake-adapt it.** Removed from
`app.py`'s navigation, removed the corresponding `test_app.py` test, and
deleted the file outright rather than leave a broken, unreferenced page
sitting in the repo. The two Claude-API features that page offered
(cross-finding synthesis, "what to work on" coaching) were specific to
having a curated findings log to synthesize — for a fresh install with
no such log, there's nothing yet to synthesize. **Not lost, deferred**:
once a new user has run enough analysis to accumulate real findings,
some equivalent ("here's what stands out in your data so far," computed
live rather than from a hand-curated file) could be a genuine v2
feature — but that's a different design than copying this page as-is,
and isn't needed for Phase A/B/D's pilot goals.

## 7. Naming

Working name used throughout this document: **Chesswright** (a "wright"
— someone who builds/works a craft — applied to chess games; avoids any
trademark overlap with Lichess, Chess.com, or Stockfish itself, and reads
distinctly from the original project's "every game tells a story"
personal branding, which is intentionally not carried over since this is
a separate identity). Two alternates considered: **Ply & Pattern**
(literal, slightly less ownable as a single word/domain), **Moveprint**
(clean, but closer to existing "fingerprint"-style product names
elsewhere). Not finalized — trivial to change before any code exists;
confirm or override at the same checkpoint as the rest of this plan.

## 8. Open items deliberately left unscoped

Flagged here rather than guessed at, so they aren't silently forgotten:
- Exact repo host/visibility (public GitHub assumed, not confirmed).
- The specific 5-6 people for Phase D's pilot are not named — the
  *process* (personal recruiting, platform mix, real-game-history
  requirement) is decided in §6 Phase D, but who they actually are isn't
  pinned down yet, since that's a real-world logistics step that comes
  closer to Phase D, not now.
- Whether the original project's `sync.py` (lichess incremental fetch)
  needs any changes for a non-`L3-37` username, or already just works —
  needs an actual test with a second real account in Phase A, not an
  assumption either way.
- Whether multiple lichess accounts/profiles on one local install is a
  real need (e.g. one person analyzing two of their own accounts) — not
  raised by the user, not assumed needed; revisit only if it comes up.
- Telemetry/crash-reporting: none planned at all stages above. If pilot
  feedback collection turns out to need more than "ask testers
  directly," that's a privacy-sensitive decision worth its own
  checkpoint, not a default to slip in.
