# Test Suite Reorg + Speedup — Design

Status: design approved by user, pending spec review
Branch: worktree-frontend-spike

## Context

The `api/main.py` router split ([[2026-07-17-api-main-router-split-design]])
is complete: `api/routers/` now has one file per page/feature, and
`tests/integration/` has one `test_api_*.py` file per router — except
`test_api_patterns.py`, which stayed a single 1,151-line, 50-test file
covering all 8 sub-resources of the `patterns` router (clock-time,
turning-points, pieces, positions, game-context, comparisons, sessions,
summary), because the router itself groups them under one prefix.

Separately, the full backend suite (`tests/` + `dashboard/`) now
collects **1,065 tests** and takes **~20 minutes** — too slow for
iterative work. Investigation (timing individual files, reading
`tests/conftest.py` and `migrate.py`) found the cause is not test count:
`migrated_db_path` / `migrated_db` / `populated_db` in `tests/conftest.py`
are function-scoped and call `migrate()` fresh for every single test —
42 migration files, each a separate `executescript()` + `commit()`
against a real temp-file SQLite DB with default `synchronous=FULL`
(fsync per commit). Confirmed by direct measurement: `tests/unit`
(384 tests, no DB fixture) runs in 20.6s, while `test_api_patterns.py`
alone (50 tests, DB fixture on every test) did not finish in 2 minutes.

`tests/integration/test_data_layer.py` (2,523 lines, 123 tests, 22
classes) was also found during this investigation — unrelated to the
router split, but the single largest file in the suite, and it hits the
same fixture cost. Its classes already map 1:1 onto
`dashboard/data/*.py` modules (confirmed via its own inline imports:
`from data.overview import ...`, `from data.matchups import ...`, etc.),
mirroring exactly the router ↔ test_api_* relationship this design is
already fixing.

## Goal

1. Split the two oversized test files so each file covers one
   router/module, matching the convention the router split already
   established.
2. Fix the per-test migration cost so both the full suite and any
   single file run fast.
3. Make it easy to run just the tests for the module you're touching,
   without adding tooling that duplicates what pytest already does.

## Research performed

Before finalizing, searched for current best practices and checked
specific claims empirically against this repo (not just taken from
search results):

- **Session-scoped template + per-test copy** for expensive DB fixtures
  is a documented pattern (pytest-django docs, SQLite testing guides,
  FastAPI/Alembic testing writeups) — not novel to this repo.
- **Mirroring test file names to the source modules they cover** is
  pytest's own stated good practice
  (docs.pytest.org "Good Integration Practices"), and matches what the
  router split already did for `test_api_*.py`.
- **`sqlite3.Connection.backup()` into `:memory:`** was considered as a
  faster alternative to file-copy for the fixtures that yield a
  connection (`migrated_db`, `populated_db`). Checked against this
  repo's own `test_data_layer.py` helpers (`_duck_from_conn`,
  `_disk_from_conn`, which reconstruct a temp file via `.iterdump()`
  regardless of whether the source connection is file- or
  memory-backed) and confirmed it would be safe. **Declined**: the
  marginal win (a few ms/test) is small once the real 2.4s/test
  migration cost is gone, and it would mean maintaining two different
  fixture mechanisms instead of one. File-copy for everything.
- **`pytest -k <name>` already does substring matching against the file's
  module name**, not just class/function names — verified empirically:
  `pytest -k patterns --collect-only` against the *current* (unsplit)
  suite matched 58/1065 tests (all of `test_api_patterns.py` plus the
  `TestPatternsData` class inside `test_data_layer.py`). This means a
  custom test-selection script would duplicate a pytest built-in.
  Dropped from the design.
- **`pytest-xdist`** (parallel workers) was researched as a further
  speedup. Confirmed via its own docs that a session-scoped fixture runs
  once *per worker*, not once total, requiring a `filelock`-based
  once-only pattern (first worker builds the template, others wait on a
  lock and reuse it). Real added dependency and coordination complexity.
  **Deferred, not part of this design** — the fixture fix alone should
  already take the suite from ~20 minutes to low single-digit minutes;
  only worth revisiting if that's still not fast enough.
- **`pytest-testmon`/`pytest-picked`** (run only tests affected by
  changed files) were researched as alternatives to manual targeting.
  Both are real, maintained tools, but add a dependency (and for
  testmon, a coverage-instrumented cache file to maintain) for a
  problem `pytest -k <module-name>` already solves once file names
  consistently carry their domain, per this design's split.
  **Not adopted** — YAGNI given `-k` already works.

## Part 1 — Split the two oversized test files

Flat sibling files, matching the existing `tests/integration/`
convention (no new subdirectories):

**`test_api_patterns.py`** (1,151 lines / 50 tests / 8 classes) →
one file per class, matching the router's own sub-resource grouping:

- `test_api_patterns_clock_time.py` (`TestPatternsClockTime`)
- `test_api_patterns_turning_points.py` (`TestPatternsTurningPoints`)
- `test_api_patterns_pieces.py` (`TestPatternsPieces`)
- `test_api_patterns_positions.py` (`TestPatternsPositions`)
- `test_api_patterns_game_context.py` (`TestPatternsGameContext`)
- `test_api_patterns_comparisons.py` (`TestPatternsComparisons`)
- `test_api_patterns_sessions.py` (`TestPatternsSessions`)
- `test_api_patterns_summary.py` (`TestPatternsSummary`)

**`test_data_layer.py`** (2,523 lines / 123 tests / 22 classes) → one
file per `dashboard/data/*.py` module, grouping the classes that already
test that module (per its own inline imports):

- `test_data_overview.py` ← `TestOverviewData`
- `test_data_game_endings.py` ← `TestGameEndingsData`
- `test_data_openings.py` ← `TestOpeningsData`, `TestGetRepresentativePathForFamily`
- `test_data_matchups.py` ← `TestMatchupsData`
- `test_data_prep.py` ← `TestOpponentPrepData`, `TestListScoutedOpponents`
- `test_data_tactical.py` ← `TestTacticalData`
- `test_data_patterns.py` ← `TestPatternsData`, `TestPositionCharacterData`, `TestGetDecisiveMomentsBreakdown`
- `test_data_variations.py` ← `TestVariationsData`
- `test_data_shared.py` ← `TestSharedHelpers`
- `test_data_db_import.py` ← `TestDbImport`
- `test_data_points.py` ← `TestPointsData`, `TestGetConversionDrillPositions`, `TestGetDefenseDrillPositions`
- `test_data_srs.py` ← `TestSrsEfficacy`
- `test_data_game_explorer.py` ← `TestGameExplorerData`
- `test_data_evolution.py` ← `TestEvolutionData`
- `test_data_ai_coach.py` ← `TestAiCoachData`
- `test_data_board_chat.py` ← `TestBoardChatData`

Module-level helpers used by multiple classes (`_insert_game`,
`_insert_move`, `_duck_from_conn`, `_disk_from_conn`) move into whichever
new file(s) actually use them; if more than one file needs the same
helper, it goes in `tests/conftest.py` rather than being duplicated.

This is a pure mechanical split — move classes and their supporting
helpers to new files, keep all imports and test bodies unchanged. No
new `conftest.py` files: `migrated_db`, `migrated_db_path`, and
`populated_db` stay defined once in `tests/conftest.py`.

## Part 2 — Fix the per-test migration cost

Replace the function-scoped "migrate from scratch every test" fixtures
in `tests/conftest.py` with a session-scoped template built once, copied
per test:

```python
@pytest.fixture(scope="session")
def _migrated_template_db(tmp_path_factory):
    """Runs migrate() exactly once per test session."""
    from migrate import migrate
    template_path = tmp_path_factory.mktemp("template") / "template.db"
    migrate(str(template_path))
    return template_path


@pytest.fixture(scope="session")
def _populated_template_db(_migrated_template_db, tmp_path_factory):
    """Migrated template + the existing synthetic-game ingest, built once."""
    import shutil
    import sqlite3
    import ingest as ingest_mod

    template_path = tmp_path_factory.mktemp("populated") / "template.db"
    shutil.copy(_migrated_template_db, template_path)
    ingest_mod.ingest(
        pgn_path=str(SYNTHETIC_PGN),
        db_path=str(template_path),
        player_name="TestPlayerWhite",
    )
    conn = sqlite3.connect(template_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # ... existing eval_cp mock-data mutation, unchanged, run once here ...
    conn.commit()
    conn.close()
    return template_path


@pytest.fixture
def migrated_db_path(_migrated_template_db, tmp_path):
    """Path to a freshly-copied migrated SQLite DB file — same contract as
    before, but backed by a copy instead of a fresh migrate() run."""
    import shutil
    db_path = tmp_path / "test.db"
    shutil.copy(_migrated_template_db, db_path)
    return str(db_path)


@pytest.fixture
def migrated_db(migrated_db_path):
    # unchanged — sqlite3.connect(migrated_db_path), PRAGMA foreign_keys=ON


@pytest.fixture
def populated_db(_populated_template_db, tmp_path):
    """Same contract as before, backed by a copy of the pre-ingested
    template instead of running ingest() fresh every test."""
    import shutil
    import sqlite3
    db_path = tmp_path / "test.db"
    shutil.copy(_populated_template_db, db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()
```

Fixture names, yielded types (path vs. connection), and observable
contents are unchanged — this is an internal implementation swap, not
an API change. No test file should need to change because of this part.

**Confirmed safe** for `tests/integration/test_migrate.py`: its two
tests that exercise `migrate()` directly
(`test_all_migrations_run_cleanly`, `test_idempotent_on_second_run`)
call it on their own raw `tmp_path`, bypassing these fixtures entirely.
Every other test in that file only reads schema/data through
`migrated_db`/`migrated_db_path`, which is identical either way since
`migrate()` is deterministic given the same `migrations/` directory.

## Part 3 — Targeted test runs

No new tooling. Document in `README.md`:

> To run tests for one module, use `pytest -k <name>` — e.g.
> `pytest -k patterns` runs every `test_api_patterns_*.py` and
> `test_data_patterns.py` test. This works because pytest's `-k`
> matches against the full test ID including the file's module name,
> and every test file in this suite is now named after the
> router/module it covers.

This is the direct payoff of Part 1: today, `pytest -k patterns` only
catches 58 of the real ~70+ patterns-related tests, because classes like
`TestPositionCharacterData` and `TestGetDecisiveMomentsBreakdown` (which
test `data.patterns`) don't have "patterns" in their class name or
their current file (`test_data_layer.py`). After the split, every
patterns-related test lives in a file whose name contains "patterns",
so `-k patterns` becomes complete.

## Deferred (not part of this design)

- **`pytest-xdist`** for parallel workers — revisit only if the full
  suite is still too slow after Part 2 lands. Would need the
  `filelock`-based once-per-run pattern for the template fixtures
  above, since xdist workers are separate processes.
- **`test_data_layer.py`'s stale module docstring** — it currently
  claims "in-memory SQLite + a temp file for DuckDB," which doesn't
  match the actual (file-backed) `populated_db` fixture. Noticed
  incidentally; harmless, not touched here since it's not part of
  either stated goal. Worth a one-line fix whenever someone's next in
  that file.

## Testing

- After Part 1: full suite still collects the same 1,065 tests (file
  moves only, no test count change) and all still pass.
- After Part 2: full suite still passes with identical results; time
  the full run before and after to confirm the improvement (target:
  well under 5 minutes, down from ~20).
- Spot-check `pytest -k patterns` and `pytest -k overview` (or another
  domain) post-split to confirm they now pick up every related test
  across both API and data-layer files, matching the Part 3 claim.
