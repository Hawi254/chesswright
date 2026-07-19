# Achievements Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Achievements Service backend (schema, evaluation engine, 12-item seed catalog, pipeline hooks, backfill script) with zero UI, per the approved design spec.

**Architecture:** A Python registry of `Achievement` definitions evaluated by one `achievements.evaluate(conn, trigger)` engine, called directly from `sync.py`/`worker.py` at the end of their existing `run()` functions. Every unlock is permanent (binary, no progress tracking) and recorded in a new `achievements_unlocked` SQLite table.

**Tech Stack:** Plain `sqlite3` only — no DuckDB (see Global Constraints). Python stdlib (`dataclasses`, `datetime`), this repo's existing `config.py`/`db.py`/`migrate.py`/`analytics.py`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-11-achievements-service-design.md`. This plan corrects two things found while grounding that spec against real code — both are documented inline where they matter, not silently changed.
- **`achievements.py`'s `check()` functions take a plain `sqlite3.Connection` only — never a DuckDB connection.** `achievements.evaluate()` is called from `sync.py`/`worker.py`, standalone pipelines with no DuckDB machinery of their own. Giving it a `duck_conn` would mean attaching DuckDB to those processes for the first time, reintroducing the same-process DuckDB+SQLite hazard the dashboard's per-PID snapshot mechanism (see project memory `duckdb_sqlite_same_process_hazard`) was built to fix. This is a correction to the spec's Architecture section, which described a dual-connection convention that doesn't apply here — confirmed by reading `dashboard/data/game_explorer.get_game_badges`, which genuinely requires DuckDB window functions and is only ever called with the dashboard's `get_connections()`-managed `duck_conn`.
- Binary unlocked/not-unlocked only. No progress-toward-next state, no UI, no notifications, no Pro-gating decision (all explicit spec non-goals).
- Every achievement's `check()` result is permanent once unlocked — never re-evaluated, never revoked.
- Evaluation must never break the sync or analysis pipeline it's attached to: every pipeline call site wraps `achievements.evaluate()` in try/except that logs and swallows.
- New migration is `migrations/0039_add_achievements.sql` (0038 is the latest existing one).
- Config thresholds live in `config.yaml` under a new `achievements:` section. This is a **brand-new top-level section** — `config.py`'s `backfill_missing_keys()` only backfills keys within a section a user's config *already has*, by its own documented design ("a whole new top-level section is rare enough... left for a human to notice via the changelog"). This is a known, accepted limitation, not a bug to fix here — no pilot users have an installed config.yaml yet (packaging is still deferred, see project memory `packaging_scoping_2026-07-08`), so there's no real install this would silently miss today.
- Real thresholds used below are grounded in the actual dev `chess.db` (32,295 games, 1,495 analyzed, 81 distinct opening families, session sizes: median 8, 90th percentile 24; game length: 90th percentile 114 plies) — not guessed round numbers. See each threshold's inline comment for its specific grounding.

---

### Task 1: Migration + config

**Files:**
- Create: `migrations/0039_add_achievements.sql`
- Modify: `config.yaml`
- Test: `tests/integration/test_achievements.py` (new file)

**Interfaces:**
- Produces: table `achievements_unlocked(achievement_id TEXT PRIMARY KEY, unlocked_at TEXT NOT NULL, source_game_id TEXT REFERENCES games(id))`. `unlocked_at`/`source_game_id` use `TEXT`, matching every other datetime/nullable-FK column in this schema (e.g. `srs_reviews.reviewed_at`, `analysis_runs.started_at`) — not `TIMESTAMP`, which the spec's illustrative pseudocode used but which isn't this codebase's actual convention.
- Produces: `config.yaml`'s `achievements:` section with 7 keys, read later by Tasks 4-6 as `cfg["achievements"]["<key>"]`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_achievements.py`:

```python
"""Integration tests for achievements.py -- the Achievements Service.
See docs/superpowers/specs/2026-07-11-achievements-service-design.md.

Uses the real migrated schema (migrated_db fixture) throughout --
achievements.py is sqlite_conn-only (no DuckDB), so no _duck_from_conn
dance is needed here, unlike tests/integration/test_data_layer.py.
"""
import pytest


@pytest.mark.integration
class TestAchievementsMigration:
    def test_achievements_unlocked_table_exists(self, migrated_db):
        cols = {row[1] for row in migrated_db.execute(
            "PRAGMA table_info(achievements_unlocked)").fetchall()}
        assert cols == {"achievement_id", "unlocked_at", "source_game_id"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_achievements.py -v`
Expected: FAIL — `cols == set()` (no such table), assertion mismatch.

- [ ] **Step 3: Write the migration and config section**

Create `migrations/0039_add_achievements.sql`:

```sql
-- Achievements Service (docs/superpowers/specs/2026-07-11-achievements-service-design.md).
-- Permanent unlock record only -- binary unlocked/not-unlocked, no
-- progress-toward-next state (deliberately out of scope for v1).
CREATE TABLE achievements_unlocked (
    achievement_id  TEXT PRIMARY KEY,
    unlocked_at     TEXT NOT NULL,
    source_game_id  TEXT REFERENCES games(id)
);
```

In `config.yaml`, add a new top-level section (after the existing `sync_chesscom:` section, at the end of the file):

```yaml
achievements:                            # thresholds for achievements.py's seed catalog --
                                           # see docs/superpowers/specs/2026-07-11-achievements-service-design.md
  win_streak_length: 10                    # consecutive wins, ever, to unlock win_streak_10
  consistency_streak_days: 5                # consecutive calendar days with >=1 game played
  drill_streak_days: 5                       # consecutive calendar days with >=1 SRS review
  marathon_min_plies: 100                     # game length (plies) to unlock marathon_game --
                                                # 90th percentile on the real dev DB is 114 plies
  opening_explorer_min_distinct: 20            # distinct opening_family values to unlock
                                                # opening_explorer -- only 81 exist total on the
                                                # real dev DB, so 20 is real breadth, not trivial
  session_warrior_min_games: 20                 # games in one session to unlock session_warrior --
                                                # 90th percentile session size on the real dev DB
                                                # is 24 games, median is 8
  century_club_min_analyzed: 100                 # analysis_status='done' games to unlock century_club
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_achievements.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/0039_add_achievements.sql config.yaml tests/integration/test_achievements.py
git commit -m "Add achievements_unlocked table and achievements config section"
```

---

### Task 2: Evaluation engine core

**Files:**
- Create: `achievements.py`
- Create: `tests/unit/test_achievements.py`

**Interfaces:**
- Consumes: `config.load_config(path=None) -> dict` (existing).
- Produces: `class Achievement` (frozen dataclass: `id: str, name: str, description: str, category: str, triggers: frozenset[str], check: Callable[[sqlite3.Connection, dict], str | bool | None]`); `CATALOG: list[Achievement]` (module-level, empty until Tasks 3-6 append to it); `evaluate(conn, trigger, config_path=None) -> list[str]` (returns the ids newly unlocked this call; `trigger=None` runs the whole catalog regardless of each entry's declared `triggers`, used by the backfill script in Task 8).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_achievements.py`:

```python
"""Unit tests for achievements.py's evaluation engine mechanics --
skip-if-unlocked, trigger filtering, and check()-exception containment.
Uses fake Achievement entries (monkeypatched onto CATALOG), not the real
seed catalog -- that's covered separately in tests/integration/test_achievements.py
once Tasks 3-6 populate CATALOG for real. No foreign_keys pragma or full
migration here, matching tests/unit/test_worker.py's own minimal-schema-
replica convention -- this table's REFERENCES games(id) isn't enforced
without PRAGMA foreign_keys=ON, so a bare achievements_unlocked table is
enough to exercise the engine in isolation."""
import sqlite3

import pytest

import achievements
from achievements import Achievement


def _minimal_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE achievements_unlocked "
        "(achievement_id TEXT PRIMARY KEY, unlocked_at TEXT NOT NULL, source_game_id TEXT)")
    return conn


@pytest.mark.unit
class TestEvaluateEngine:
    def test_unlocks_matching_achievement(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_a", "Fake A", "desc", "milestone",
                            frozenset({"sync"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == ["fake_a"]
        row = conn.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='fake_a'"
        ).fetchone()
        assert row[0] is None

    def test_records_source_game_id_when_check_returns_a_string(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_b", "Fake B", "desc", "narrative",
                            frozenset({"sync"}), lambda c, cfg: "g42")
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        achievements.evaluate(conn, "sync")
        row = conn.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='fake_b'"
        ).fetchone()
        assert row[0] == "g42"

    def test_already_unlocked_is_skipped_without_calling_check_again(self, monkeypatch):
        conn = _minimal_db()
        conn.execute(
            "INSERT INTO achievements_unlocked VALUES ('fake_c', '2025-01-01T00:00:00', NULL)")
        conn.commit()
        calls = []

        def _check(c, cfg):
            calls.append(1)
            return True

        fake = Achievement("fake_c", "Fake C", "desc", "milestone",
                            frozenset({"sync"}), _check)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == []
        assert calls == []

    def test_filters_by_trigger(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_d", "Fake D", "desc", "milestone",
                            frozenset({"analysis"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == []
        assert conn.execute("SELECT COUNT(*) FROM achievements_unlocked").fetchone()[0] == 0

    def test_trigger_none_runs_full_catalog_regardless_of_triggers(self, monkeypatch):
        conn = _minimal_db()
        fake = Achievement("fake_e", "Fake E", "desc", "milestone",
                            frozenset({"analysis"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [fake])
        unlocked = achievements.evaluate(conn, trigger=None)
        assert unlocked == ["fake_e"]

    def test_a_failing_check_is_caught_and_does_not_block_others(self, monkeypatch, capsys):
        conn = _minimal_db()

        def _boom(c, cfg):
            raise RuntimeError("boom")

        broken = Achievement("fake_f", "Fake F", "desc", "milestone",
                              frozenset({"sync"}), _boom)
        ok = Achievement("fake_g", "Fake G", "desc", "milestone",
                          frozenset({"sync"}), lambda c, cfg: True)
        monkeypatch.setattr(achievements, "CATALOG", [broken, ok])
        unlocked = achievements.evaluate(conn, "sync")
        assert unlocked == ["fake_g"]
        assert "fake_f" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_achievements.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'achievements'`.

- [ ] **Step 3: Write the minimal implementation**

Create `achievements.py`:

```python
"""Achievements Service -- evaluates achievement criteria against real
gameplay/analysis data and records permanent unlocks. See
docs/superpowers/specs/2026-07-11-achievements-service-design.md.

Deliberately sqlite_conn only -- no DuckDB. This module is called from
sync.py/worker.py, standalone CLI pipelines with no DuckDB machinery of
their own; giving it a duck_conn would mean attaching DuckDB to those
processes for the first time, reintroducing the same-process DuckDB+
SQLite hazard the dashboard's per-PID snapshot mechanism exists to fix
(see project memory: duckdb_sqlite_same_process_hazard). Every check()
in this module is plain SQL/Python instead.

CATALOG starts empty here and is extended in place, further down this
same file, by each seed-achievement batch -- see the design spec's
seed catalog table for the full list and its grounding.
"""
import dataclasses
import datetime
import sqlite3
from typing import Callable

from config import load_config


@dataclasses.dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    category: str  # "streak" | "milestone" | "skill" | "narrative"
    triggers: frozenset  # subset of {"sync", "analysis"}
    check: Callable[[sqlite3.Connection, dict], object]  # -> str | bool | None


CATALOG: list[Achievement] = []


def evaluate(conn, trigger, config_path=None):
    """Runs every not-yet-unlocked catalog entry relevant to `trigger`.
    trigger=None runs the full catalog regardless of each entry's
    declared `triggers` -- used by the one-off backfill script (Task 8)
    to sweep existing history once. Each check() failure is caught,
    logged, and skipped -- one bad achievement must never abort the
    whole pass, let alone the sync/analysis pipeline calling this.
    Returns the list of achievement ids newly unlocked this call."""
    cfg = load_config(config_path)
    already_unlocked = {row[0] for row in conn.execute(
        "SELECT achievement_id FROM achievements_unlocked").fetchall()}
    newly_unlocked = []
    for achievement in CATALOG:
        if achievement.id in already_unlocked:
            continue
        if trigger is not None and trigger not in achievement.triggers:
            continue
        try:
            result = achievement.check(conn, cfg)
        except Exception as e:
            print(f"WARNING: achievement '{achievement.id}' check failed: {e}")
            continue
        if not result:
            continue
        source_game_id = result if isinstance(result, str) else None
        conn.execute(
            "INSERT INTO achievements_unlocked (achievement_id, unlocked_at, source_game_id) "
            "VALUES (?, ?, ?)",
            (achievement.id, datetime.datetime.now(datetime.timezone.utc).isoformat(),
             source_game_id))
        newly_unlocked.append(achievement.id)
    if newly_unlocked:
        conn.commit()
    return newly_unlocked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_achievements.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add achievements.py tests/unit/test_achievements.py
git commit -m "Add achievements.py evaluation engine (empty catalog)"
```

---

### Task 3: Seed batch A — one-time board/outcome events

**Files:**
- Modify: `achievements.py`
- Modify: `tests/integration/test_achievements.py`

**Interfaces:**
- Consumes: `Achievement`, `CATALOG` from Task 2.
- Produces: three catalog entries — `first_win`, `giant_killer`, `comeback_kid` — appended to `CATALOG`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_achievements.py`:

```python
@pytest.mark.integration
class TestSeedCatalogOneTimeEvents:
    def _insert_game(self, conn, game_id, outcome_for_player, rating_diff=0,
                      utc_date="2025.01.01", utc_time="12:00:00", analysis_status="pending"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, rating_diff, "
            "utc_date, utc_time, analysis_status) VALUES (?, 'W', 'B', ?, ?, ?, ?, ?)",
            (game_id, outcome_for_player, rating_diff, utc_date, utc_time, analysis_status))
        conn.commit()

    def test_first_win_unlocks_on_first_win_game(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss")
        self._insert_game(migrated_db, "g2", "win", utc_date="2025.01.02")
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "first_win" in unlocked
        row = migrated_db.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='first_win'"
        ).fetchone()
        assert row[0] == "g2"

    def test_first_win_does_not_unlock_without_a_win(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss")
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "first_win" not in unlocked

    def test_giant_killer_unlocks_on_qualifying_upset(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "win", rating_diff=-350)
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "giant_killer" in unlocked

    def test_giant_killer_requires_a_win_not_just_the_rating_gap(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss", rating_diff=-350)
        unlocked = achievements.evaluate(migrated_db, "sync")
        assert "giant_killer" not in unlocked

    def test_comeback_kid_unlocks_on_recovered_win(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "win")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before) VALUES ('g1', 1, 1, 'w', 'e4', 1, 0.05)")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis")
        assert "comeback_kid" in unlocked

    def test_comeback_kid_requires_a_win_or_draw_outcome(self, migrated_db):
        import achievements
        self._insert_game(migrated_db, "g1", "loss")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before) VALUES ('g1', 1, 1, 'w', 'e4', 1, 0.05)")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis")
        assert "comeback_kid" not in unlocked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_achievements.py -v -k OneTimeEvents`
Expected: FAIL — `AssertionError`, `first_win`/`giant_killer`/`comeback_kid` never appear in `unlocked` (empty `CATALOG`).

- [ ] **Step 3: Write the minimal implementation**

Append to `achievements.py` (after the `evaluate()` function):

```python
# ---------------------------------------------------------------------------
# Seed catalog, batch A: one-time board/outcome events.
# ---------------------------------------------------------------------------

GIANT_KILLING_UPSET_THRESHOLD = -300   # keep aligned with dashboard/data/_shared.py's copy
COMEBACK_WP_THRESHOLD = 0.10           # keep aligned with dashboard/data/_shared.py's copy


def _check_first_win(conn, cfg):
    row = conn.execute(
        "SELECT id FROM games WHERE outcome_for_player='win' "
        "ORDER BY utc_date, utc_time, id LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _check_giant_killer(conn, cfg):
    row = conn.execute(
        "SELECT id FROM games WHERE rating_diff <= ? AND outcome_for_player='win' "
        "ORDER BY utc_date, utc_time, id LIMIT 1",
        (GIANT_KILLING_UPSET_THRESHOLD,)
    ).fetchone()
    return row[0] if row else None


def _first_game_with_min_wp_at_most(conn, threshold, outcomes):
    """Shared by comeback_kid (batch A) and swindle_artist (batch D,
    Task 6) -- same "how low did the player's win probability go in this
    game" shape, differing only in the threshold and which final
    outcomes count. min_wp reuses the exact mover-POV-flip expression
    dashboard/data/game_explorer.get_game_badges uses for is_comeback,
    but as a plain SQLite GROUP BY (no window function needed for a MIN,
    unlike that function's LAG-based lead-change count), so it works
    outside the dashboard's DuckDB-only process."""
    placeholders = ",".join("?" * len(outcomes))
    row = conn.execute(f"""
        SELECT g.id
        FROM games g
        JOIN (
            SELECT game_id,
                   MIN(CASE WHEN is_player_move=1 THEN win_prob_before
                            ELSE 1 - win_prob_before END) AS min_wp
            FROM moves
            WHERE win_prob_before IS NOT NULL
            GROUP BY game_id
        ) m ON m.game_id = g.id
        WHERE m.min_wp <= ? AND g.outcome_for_player IN ({placeholders})
        ORDER BY g.utc_date, g.utc_time, g.id
        LIMIT 1
    """, (threshold, *outcomes)).fetchone()
    return row[0] if row else None


def _check_comeback_kid(conn, cfg):
    return _first_game_with_min_wp_at_most(conn, COMEBACK_WP_THRESHOLD, ("win", "draw"))


CATALOG.extend([
    Achievement("first_win", "First Win", "Win your first recorded game.",
                "milestone", frozenset({"sync"}), _check_first_win),
    Achievement("giant_killer", "Giant Killer",
                "Beat an opponent rated 300+ points above you.",
                "narrative", frozenset({"sync"}), _check_giant_killer),
    Achievement("comeback_kid", "Comeback Kid",
                "Win or draw a game you were nearly lost in.",
                "narrative", frozenset({"analysis"}), _check_comeback_kid),
])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_achievements.py -v -k OneTimeEvents`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add achievements.py tests/integration/test_achievements.py
git commit -m "Add first_win, giant_killer, comeback_kid achievements"
```

---

### Task 4: Seed batch B — count/threshold achievements

**Files:**
- Modify: `achievements.py`
- Modify: `tests/integration/test_achievements.py`

**Interfaces:**
- Produces: four catalog entries — `century_club`, `marathon_game`, `opening_explorer`, `blunder_free_game` — appended to `CATALOG`.
- Produces: `achievements_config` pytest fixture (small thresholds, for deterministic tests independent of the real `config.yaml`'s actual values), reused by Tasks 5 and 6.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_achievements.py` (fixture first, then the test class):

```python
@pytest.fixture
def achievements_config(tmp_path):
    """Small thresholds so seed-catalog tests are deterministic and don't
    depend on the real config.yaml's actual values (which are tuned for
    the real ~32k-game dev DB, not a handful of hand-seeded test rows)."""
    cfg_text = (
        "achievements:\n"
        "  win_streak_length: 3\n"
        "  consistency_streak_days: 3\n"
        "  drill_streak_days: 3\n"
        "  marathon_min_plies: 40\n"
        "  opening_explorer_min_distinct: 2\n"
        "  session_warrior_min_games: 3\n"
        "  century_club_min_analyzed: 2\n"
        "analytics:\n"
        "  session_gap_minutes: 60\n"
    )
    cfg_path = tmp_path / "achievements_config.yaml"
    cfg_path.write_text(cfg_text)
    return str(cfg_path)


@pytest.mark.integration
class TestSeedCatalogThresholds:
    def _insert_game(self, conn, game_id, outcome_for_player="win", num_plies=10,
                      opening_family=None, analysis_status="pending",
                      utc_date="2025.01.01", utc_time="12:00:00"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, num_plies, "
            "opening_family, analysis_status, utc_date, utc_time) "
            "VALUES (?, 'W', 'B', ?, ?, ?, ?, ?, ?)",
            (game_id, outcome_for_player, num_plies, opening_family, analysis_status,
             utc_date, utc_time))
        conn.commit()

    def test_century_club_unlocks_at_threshold(self, migrated_db, achievements_config):
        import achievements
        for i in range(2):
            self._insert_game(migrated_db, f"g{i}", analysis_status="done")
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "century_club" in unlocked

    def test_century_club_not_unlocked_below_threshold(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", analysis_status="done")
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "century_club" not in unlocked

    def test_marathon_game_unlocks_on_long_game(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", num_plies=45)
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "marathon_game" in unlocked

    def test_opening_explorer_unlocks_on_enough_variety(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", opening_family="Italian Game")
        self._insert_game(migrated_db, "g1", opening_family="Sicilian Defense")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "opening_explorer" in unlocked

    def test_blunder_free_game_unlocks_on_clean_analyzed_game(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", analysis_status="done")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "classification) VALUES ('g0', 1, 1, 'w', 'e4', 1, 'good')")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "blunder_free_game" in unlocked

    def test_blunder_free_game_not_unlocked_with_a_blunder(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", analysis_status="done")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "classification) VALUES ('g0', 1, 1, 'w', 'e4', 1, 'blunder')")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "blunder_free_game" not in unlocked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_achievements.py -v -k Thresholds`
Expected: FAIL — none of the four ids ever appear in `unlocked`.

- [ ] **Step 3: Write the minimal implementation**

Append to `achievements.py`:

```python
# ---------------------------------------------------------------------------
# Seed catalog, batch B: count/threshold achievements.
# ---------------------------------------------------------------------------

def _check_century_club(conn, cfg):
    threshold = cfg["achievements"]["century_club_min_analyzed"]
    n = conn.execute("SELECT COUNT(*) FROM games WHERE analysis_status='done'").fetchone()[0]
    return n >= threshold


def _check_marathon_game(conn, cfg):
    threshold = cfg["achievements"]["marathon_min_plies"]
    row = conn.execute(
        "SELECT id FROM games WHERE num_plies >= ? ORDER BY utc_date, utc_time, id LIMIT 1",
        (threshold,)
    ).fetchone()
    return row[0] if row else None


def _check_opening_explorer(conn, cfg):
    threshold = cfg["achievements"]["opening_explorer_min_distinct"]
    n = conn.execute(
        "SELECT COUNT(DISTINCT opening_family) FROM games WHERE opening_family IS NOT NULL"
    ).fetchone()[0]
    return n >= threshold


def _check_blunder_free_game(conn, cfg):
    row = conn.execute("""
        SELECT g.id FROM games g
        WHERE g.analysis_status = 'done'
          AND EXISTS (SELECT 1 FROM moves m WHERE m.game_id = g.id AND m.is_player_move = 1)
          AND NOT EXISTS (
              SELECT 1 FROM moves m
              WHERE m.game_id = g.id AND m.is_player_move = 1 AND m.classification = 'blunder'
          )
        ORDER BY g.utc_date, g.utc_time, g.id
        LIMIT 1
    """).fetchone()
    return row[0] if row else None


CATALOG.extend([
    Achievement("century_club", "Century Club", "Get 100 games fully analyzed.",
                "milestone", frozenset({"analysis"}), _check_century_club),
    Achievement("marathon_game", "Marathon", "Play a game that goes the distance.",
                "milestone", frozenset({"sync"}), _check_marathon_game),
    Achievement("opening_explorer", "Opening Explorer", "Play 20 different openings.",
                "milestone", frozenset({"sync"}), _check_opening_explorer),
    Achievement("blunder_free_game", "Clean Sheet",
                "Complete a fully analyzed game with zero blunders.",
                "skill", frozenset({"analysis"}), _check_blunder_free_game),
])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_achievements.py -v -k Thresholds`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add achievements.py tests/integration/test_achievements.py
git commit -m "Add century_club, marathon_game, opening_explorer, blunder_free_game achievements"
```

---

### Task 5: Seed batch C — streak achievements

**Files:**
- Modify: `achievements.py`
- Modify: `tests/integration/test_achievements.py`

**Interfaces:**
- Produces: two shared helpers (`_longest_win_streak_end`, `_longest_consecutive_day_run`) and three catalog entries — `win_streak_10`, `consistency_streak`, `drill_streak` — appended to `CATALOG`.
- **Documented tradeoff on `drill_streak`**: its underlying data (`srs_reviews`, written when a user takes an SRS drill in the dashboard UI) has no pipeline hook of its own in this plan — SRS Drills' practice UI lives in the private `chesswright-pro` repo, out of scope for this backend-only, core-repo plan. Rather than drop the achievement or invent a third hook point in a private repo this plan doesn't touch, `drill_streak` is tagged with `triggers={"sync", "analysis"}` — it gets swept opportunistically whenever either existing pipeline runs (which happens regularly), so it unlocks within one sync/analysis cycle of qualifying rather than immediately. This is a real, stated tradeoff, not a silent gap — say so again in code as a comment at the definition site.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_achievements.py`:

```python
@pytest.mark.integration
class TestSeedCatalogStreaks:
    def _insert_game(self, conn, game_id, outcome_for_player, utc_date, utc_time="12:00:00"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
            "VALUES (?, 'W', 'B', ?, ?, ?)",
            (game_id, outcome_for_player, utc_date, utc_time))
        conn.commit()

    def test_win_streak_unlocks_at_threshold_and_records_last_game(
            self, migrated_db, achievements_config):
        import achievements
        for i in range(3):
            self._insert_game(migrated_db, f"g{i}", "win", f"2025.01.0{i+1}")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "win_streak_10" in unlocked
        row = migrated_db.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='win_streak_10'"
        ).fetchone()
        assert row[0] == "g2"

    def test_win_streak_not_unlocked_when_streak_is_broken(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", "win", "2025.01.01")
        self._insert_game(migrated_db, "g1", "loss", "2025.01.02")
        self._insert_game(migrated_db, "g2", "win", "2025.01.03")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "win_streak_10" not in unlocked

    def test_consistency_streak_unlocks_on_consecutive_days(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", "win", "2025.01.01")
        self._insert_game(migrated_db, "g1", "win", "2025.01.02")
        self._insert_game(migrated_db, "g2", "win", "2025.01.03")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "consistency_streak" in unlocked

    def test_consistency_streak_not_unlocked_with_a_gap_day(self, migrated_db, achievements_config):
        import achievements
        self._insert_game(migrated_db, "g0", "win", "2025.01.01")
        self._insert_game(migrated_db, "g1", "win", "2025.01.03")
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "consistency_streak" not in unlocked

    def test_drill_streak_unlocks_on_consecutive_review_days(self, migrated_db, achievements_config):
        import achievements
        migrated_db.execute(
            "INSERT INTO srs_cards (fen, source, best_move_san, next_due, added_at) "
            "VALUES ('fen1', 'motif', 'e4', '2025-02-01', '2025-01-01')")
        card_id = migrated_db.execute("SELECT id FROM srs_cards").fetchone()[0]
        for day in ("2025-01-01", "2025-01-02", "2025-01-03"):
            migrated_db.execute(
                "INSERT INTO srs_reviews (card_id, reviewed_at, rating, interval_days_after) "
                "VALUES (?, ?, 2, 1)", (card_id, f"{day}T10:00:00"))
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "drill_streak" in unlocked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_achievements.py -v -k Streaks`
Expected: FAIL — none of the three ids ever appear in `unlocked`.

- [ ] **Step 3: Write the minimal implementation**

Append to `achievements.py` (add `import datetime` is already present from Task 2):

```python
# ---------------------------------------------------------------------------
# Seed catalog, batch C: streak achievements.
# ---------------------------------------------------------------------------

def _longest_win_streak_end(rows):
    """rows: [(game_id, outcome_for_player), ...] in chronological order.
    Returns (run_length, game_id_of_last_game_in_the_longest_run)."""
    best_len, best_id = 0, None
    cur_len, cur_id = 0, None
    for game_id, outcome in rows:
        if outcome == "win":
            cur_len += 1
            cur_id = game_id
        else:
            cur_len, cur_id = 0, None
        if cur_len > best_len:
            best_len, best_id = cur_len, cur_id
    return best_len, best_id


def _longest_consecutive_day_run(dates):
    """dates: iterable of 'YYYY-MM-DD' strings (any order, dupes ok).
    Returns the longest run length of calendar-consecutive days."""
    unique_days = sorted({datetime.date.fromisoformat(d) for d in dates})
    if not unique_days:
        return 0
    best = cur = 1
    for prev, nxt in zip(unique_days, unique_days[1:]):
        cur = cur + 1 if (nxt - prev).days == 1 else 1
        best = max(best, cur)
    return best


def _check_win_streak(conn, cfg):
    threshold = cfg["achievements"]["win_streak_length"]
    rows = conn.execute(
        "SELECT id, outcome_for_player FROM games "
        "WHERE outcome_for_player IS NOT NULL ORDER BY utc_date, utc_time, id"
    ).fetchall()
    best_len, best_id = _longest_win_streak_end(rows)
    return best_id if best_len >= threshold else None


def _check_consistency_streak(conn, cfg):
    threshold = cfg["achievements"]["consistency_streak_days"]
    rows = conn.execute("SELECT DISTINCT utc_date FROM games WHERE utc_date IS NOT NULL").fetchall()
    # utc_date is stored 'YYYY.MM.DD' (PGN date format) -- ISO-ify for date math.
    dates = [d.replace(".", "-") for (d,) in rows]
    return _longest_consecutive_day_run(dates) >= threshold


def _check_drill_streak(conn, cfg):
    """Tagged with triggers={"sync","analysis"} below, not a dedicated
    trigger of its own: srs_reviews is written by the dashboard's SRS
    Drills page (private chesswright-pro UI), which has no pipeline hook
    in this plan. This achievement is swept opportunistically whenever
    sync or analysis runs instead of reacting immediately -- a real,
    accepted lag (up to one sync/analysis cycle), not a silent gap."""
    threshold = cfg["achievements"]["drill_streak_days"]
    rows = conn.execute("SELECT DISTINCT substr(reviewed_at, 1, 10) FROM srs_reviews").fetchall()
    dates = [d for (d,) in rows]
    return _longest_consecutive_day_run(dates) >= threshold


CATALOG.extend([
    Achievement("win_streak_10", "On a Roll", "Win 10 games in a row.",
                "streak", frozenset({"sync"}), _check_win_streak),
    Achievement("consistency_streak", "Creature of Habit",
                "Play at least one game on 5 consecutive days.",
                "streak", frozenset({"sync"}), _check_consistency_streak),
    Achievement("drill_streak", "Dedicated Student",
                "Review SRS drill cards on 5 consecutive days.",
                "streak", frozenset({"sync", "analysis"}), _check_drill_streak),
])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_achievements.py -v -k Streaks`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add achievements.py tests/integration/test_achievements.py
git commit -m "Add win_streak_10, consistency_streak, drill_streak achievements"
```

---

### Task 6: Seed batch D — swindle_artist + session_warrior

**Files:**
- Modify: `achievements.py`
- Modify: `tests/integration/test_achievements.py`

**Interfaces:**
- Consumes: `analytics.ensure_session_ctx(conn, session_gap_minutes)` (existing, creates a TEMP TABLE `session_ctx` with columns including `game_id`, `session_start`, `session_game_number` — confirmed in `dashboard/data/patterns.get_session_rollup`'s usage).
- Produces: two catalog entries — `swindle_artist`, `session_warrior` — appended to `CATALOG`. Refactors `_check_comeback_kid` (Task 3) to call the shared `_first_game_with_min_wp_at_most` helper with `swindle_artist`'s own threshold/outcome — this is a real DRY fix on code this task is already touching, not scope creep: both achievements are "how low did win probability go in this game" checks, differing only in threshold (`COMEBACK_WP_THRESHOLD=0.10` vs. `points.py`'s `LOST_WP=0.25`) and which outcomes count (`("win","draw")` vs. `("win",)`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_achievements.py`:

```python
@pytest.mark.integration
class TestSeedCatalogBespoke:
    def _insert_game_with_move(self, conn, game_id, outcome, min_wp, utc_date="2025.01.01"):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
            "VALUES (?, 'W', 'B', ?, ?, '12:00:00')", (game_id, outcome, utc_date))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before) VALUES (?, 1, 1, 'w', 'e4', 1, ?)", (game_id, min_wp))
        conn.commit()

    def test_swindle_artist_unlocks_on_win_from_a_lost_position(
            self, migrated_db, achievements_config):
        import achievements
        self._insert_game_with_move(migrated_db, "g0", "win", 0.10)
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "swindle_artist" in unlocked

    def test_swindle_artist_does_not_unlock_on_a_draw(self, migrated_db, achievements_config):
        import achievements
        self._insert_game_with_move(migrated_db, "g0", "draw", 0.10)
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "swindle_artist" not in unlocked

    def test_comeback_kid_still_works_after_the_shared_helper_refactor(
            self, migrated_db, achievements_config):
        import achievements
        self._insert_game_with_move(migrated_db, "g0", "draw", 0.05)
        unlocked = achievements.evaluate(migrated_db, "analysis", config_path=achievements_config)
        assert "comeback_kid" in unlocked

    def test_session_warrior_unlocks_on_a_large_session(self, migrated_db, achievements_config):
        import achievements
        for i, minute in enumerate((0, 5, 10)):
            migrated_db.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
                "VALUES (?, 'W', 'B', 'win', '2025.01.01', ?)",
                (f"g{i}", f"10:{minute:02d}:00"))
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "session_warrior" in unlocked
        row = migrated_db.execute(
            "SELECT source_game_id FROM achievements_unlocked WHERE achievement_id='session_warrior'"
        ).fetchone()
        assert row[0] == "g2"

    def test_session_warrior_not_unlocked_below_threshold(self, migrated_db, achievements_config):
        import achievements
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
            "VALUES ('g0', 'W', 'B', 'win', '2025.01.01', '10:00:00')")
        migrated_db.commit()
        unlocked = achievements.evaluate(migrated_db, "sync", config_path=achievements_config)
        assert "session_warrior" not in unlocked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_achievements.py -v -k Bespoke`
Expected: FAIL — `swindle_artist`/`session_warrior` never unlock (not in `CATALOG` yet); the `comeback_kid` regression test passes already (it's testing pre-existing Task 3 behavior), which is fine at this stage.

- [ ] **Step 3: Write the minimal implementation**

`_check_comeback_kid` already has this exact shape from Task 3 (it was written there calling `_first_game_with_min_wp_at_most` directly) — no edit to that function is needed in this task. What Task 6 actually adds is the new threshold constant and the two new functions below.

Add near the top of the batch-A section (alongside `GIANT_KILLING_UPSET_THRESHOLD`/`COMEBACK_WP_THRESHOLD`):

```python
LOST_WP = 0.25   # keep aligned with points.py's copy
```

Append at the end of `achievements.py`, and add `import analytics` to the top-of-file imports (alongside `from config import load_config`):

```python
# ---------------------------------------------------------------------------
# Seed catalog, batch D: swindle_artist + session_warrior.
# ---------------------------------------------------------------------------

def _check_swindle_artist(conn, cfg):
    return _first_game_with_min_wp_at_most(conn, LOST_WP, ("win",))


def _check_session_warrior(conn, cfg):
    threshold = cfg["achievements"]["session_warrior_min_games"]
    gap_minutes = cfg["analytics"]["session_gap_minutes"]
    analytics.ensure_session_ctx(conn, gap_minutes)
    row = conn.execute("""
        SELECT game_id FROM session_ctx
        WHERE session_start = (
            SELECT session_start FROM session_ctx
            GROUP BY session_start
            HAVING COUNT(*) >= ?
            ORDER BY session_start LIMIT 1
        )
        ORDER BY session_game_number DESC LIMIT 1
    """, (threshold,)).fetchone()
    return row[0] if row else None


CATALOG.extend([
    Achievement("swindle_artist", "Swindle Artist", "Win a game you were losing badly.",
                "narrative", frozenset({"analysis"}), _check_swindle_artist),
    Achievement("session_warrior", "Session Warrior", "Play a marathon session in one sitting.",
                "milestone", frozenset({"sync"}), _check_session_warrior),
])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_achievements.py -v -k Bespoke`
Expected: PASS (5 tests). Also rerun the full file to confirm the refactor didn't regress earlier batches:

Run: `pytest tests/integration/test_achievements.py -v`
Expected: PASS (all tests from Tasks 1, 3, 4, 5, 6)

- [ ] **Step 5: Commit**

```bash
git add achievements.py tests/integration/test_achievements.py
git commit -m "Add swindle_artist, session_warrior achievements; DRY comeback_kid/swindle_artist"
```

---

### Task 7: Pipeline hooks

**Files:**
- Modify: `worker.py`
- Modify: `sync.py`
- Test: `tests/integration/test_achievements.py`

**Interfaces:**
- Consumes: `achievements.evaluate(conn, trigger, config_path=None) -> list[str]` (Task 2).
- Both hooks call `achievements.evaluate` via the **module reference** (`import achievements` then `achievements.evaluate(...)`), not `from achievements import evaluate` — required so tests can `monkeypatch.setattr(achievements, "evaluate", ...)` and have `worker.py`/`sync.py` see the patched version at their call sites.

- [ ] **Step 1: Write the failing test for the worker.py hook**

Add `import pathlib` and `import sqlite3` to the top of `tests/integration/test_achievements.py`, alongside the existing `import pytest` (Task 8 also needs `sqlite3`, already available from this point on — no need to add it again there).

Then append to the bottom of the file. This reuses the existing `REAL_STOCKFISH`/`FakeAnalysisEngine`-style precedent from `tests/integration/test_eval_reuse_cache.py` (a real, tiny-depth Stockfish run, skipped if none is installed) — worker.py's own `run()` has never been tested with anything less than a real engine in this codebase, so this plan doesn't invent a new mocking strategy just for this hook:

```python
FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"


def _find_real_stockfish():
    from worker import find_engine_path
    return find_engine_path(None)


REAL_STOCKFISH = _find_real_stockfish()


@pytest.mark.integration
@pytest.mark.skipif(REAL_STOCKFISH is None, reason="no Stockfish binary on this machine")
def test_worker_run_calls_achievements_evaluate_after_analyzing(tmp_path, monkeypatch):
    import migrate as migrate_mod
    import ingest
    import worker
    import achievements

    db_path = str(tmp_path / "test.db")
    migrate_mod.migrate(db_path)
    ingest.ingest(pgn_path=str(FIXTURES_DIR / "synthetic_games.pgn"), db_path=db_path,
                  player_name="TestPlayerWhite")

    calls = []
    monkeypatch.setattr(achievements, "evaluate",
                         lambda conn, trigger, **kw: calls.append(trigger))
    monkeypatch.setattr(worker.joblock, "LOCK_PATH", tmp_path / "test.db.lock")
    monkeypatch.setattr(worker.joblock, "_lock_fd", None)

    worker.run(db_path, depth=6, multipv=1, threads=1, hash_mb=16, pv_max_len=10,
               engine_path=REAL_STOCKFISH, max_games=3, max_duration_s=None,
               consecutive_failure_limit=3, commit_every_n_moves=1)
    worker.joblock.release()

    assert calls == ["analysis"]
```

Run: `pytest tests/integration/test_achievements.py -v -k worker_run_calls`
Expected: FAIL — `assert [] == ["analysis"]` (no hook exists yet).

- [ ] **Step 2: Write the failing test for the sync.py hook**

Append to the same file. Monkeypatches `sync.fetch_new_games_pgn` to return a **copy** of the fixture PGN (not the fixture file itself — `sync.run()`'s `finally: os.unlink(pgn_path)` deletes whatever path it's given, so pointing it at the real fixture directly would delete a tracked repo file):

```python
@pytest.mark.integration
def test_sync_run_calls_achievements_evaluate_after_new_games(tmp_path, monkeypatch):
    import shutil
    import migrate as migrate_mod
    import sync
    import achievements

    db_path = str(tmp_path / "test.db")
    migrate_mod.migrate(db_path)

    def _fake_fetch(player_name, since_ms, timeout_seconds, max_games=None):
        copy_path = str(tmp_path / "fetched.pgn")
        shutil.copy(str(FIXTURES_DIR / "synthetic_games.pgn"), copy_path)
        return copy_path

    monkeypatch.setattr(sync, "fetch_new_games_pgn", _fake_fetch)
    calls = []
    monkeypatch.setattr(achievements, "evaluate",
                         lambda conn, trigger, **kw: calls.append(trigger))

    sync.run(db_path, "TestPlayerWhite", queue_strategy="chronological",
             berserk_max_fraction=1.0, variant_policy="skip", timeout_seconds=5)

    assert calls == ["sync"]
```

Run: `pytest tests/integration/test_achievements.py -v -k sync_run_calls`
Expected: FAIL — `assert [] == ["sync"]` (no hook exists yet).

- [ ] **Step 3: Add the worker.py hook**

In `worker.py`, add `import achievements` to the top-of-file imports (alongside the other local imports such as `from db import get_connection`).

In `worker.py`'s `run()` function, immediately after the existing `finally:` block that closes with `joblock.release()` (the block ending `engine.quit(); conn.close(); joblock.release()`) and before the `summary_cache_fragment = ""` line, insert:

```python
    if games_done > 0:
        try:
            achievements_conn = get_connection(db_path)
            achievements.evaluate(achievements_conn, "analysis")
            achievements_conn.close()
        except Exception as e:
            print(f"WARNING: achievement evaluation failed (analysis batch unaffected): {e}")
```

`conn` from the pipeline's own `finally` block is already closed at this point, so this opens its own fresh connection — same pattern as the sync.py hook below. Guarded by `games_done > 0` so a batch that analyzed nothing (empty queue) doesn't pay for a no-op evaluation pass.

- [ ] **Step 4: Add the sync.py hook and run all four tests to verify they pass**

In `sync.py`, add `import achievements` to the top-of-file imports.

In `sync.py`'s `run()` function, immediately after the block `bump_new_games_to_front_of_queue(conn, truly_new_ids); conn.commit(); conn.close()` and before the `print(f"Synced {n} game(s)...")` line, insert:

```python
    try:
        achievements_conn = get_connection(db_path)
        achievements.evaluate(achievements_conn, "sync")
        achievements_conn.close()
    except Exception as e:
        print(f"WARNING: achievement evaluation failed (sync unaffected): {e}")
```

Run: `pytest tests/integration/test_achievements.py -v -k "worker_run_calls or sync_run_calls"`
Expected: PASS (2 tests; the worker one skips if no local Stockfish, which is fine)

Run the full test file once more to confirm nothing else regressed:

Run: `pytest tests/integration/test_achievements.py tests/unit/test_achievements.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add worker.py sync.py tests/integration/test_achievements.py
git commit -m "Hook achievements.evaluate() into sync.py and worker.py"
```

---

### Task 8: Backfill script

**Files:**
- Create: `backfill_achievements.py`
- Test: `tests/integration/test_achievements.py`

**Interfaces:**
- Consumes: `achievements.evaluate(conn, trigger=None, config_path=None)` (Task 2 — `trigger=None` sweeps the whole catalog regardless of each entry's declared `triggers`).
- Produces: `backfill(db_path, config_path=None) -> None`, callable directly from tests without going through `argparse`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_achievements.py`:

```python
@pytest.mark.integration
def test_backfill_achievements_is_idempotent(migrated_db_path):
    import backfill_achievements

    conn = sqlite3.connect(migrated_db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, utc_date, utc_time) "
        "VALUES ('g1', 'W', 'B', 'win', '2025.01.01', '12:00:00')")
    conn.commit()
    conn.close()

    backfill_achievements.backfill(migrated_db_path)
    conn = sqlite3.connect(migrated_db_path)
    first_count = conn.execute("SELECT COUNT(*) FROM achievements_unlocked").fetchone()[0]
    conn.close()
    assert first_count >= 1  # at least first_win

    backfill_achievements.backfill(migrated_db_path)
    conn = sqlite3.connect(migrated_db_path)
    second_count = conn.execute("SELECT COUNT(*) FROM achievements_unlocked").fetchone()[0]
    conn.close()
    assert second_count == first_count
```

Run: `pytest tests/integration/test_achievements.py -v -k idempotent`
Expected: FAIL with `ModuleNotFoundError: No module named 'backfill_achievements'`.

- [ ] **Step 2: Run test to verify it fails**

(Same command/expectation as Step 1 — already confirmed above.)

- [ ] **Step 3: Write the minimal implementation**

Create `backfill_achievements.py`, modeled on `backfill_legal_reply_count.py`'s existing structure:

```python
#!/usr/bin/env python3
"""
One-time (but safe to re-run) sweep: evaluates the full Achievements
Service catalog against ALL existing history, regardless of each
achievement's declared `triggers` -- so achievements already earned by
past games/reviews unlock immediately once this service is deployed,
rather than only reacting to games synced or analyzed after this ships.

Idempotent: achievements.evaluate() only ever inserts a row for an
achievement not already in achievements_unlocked, so re-running finds
nothing new the second time.

Usage:
    python3 backfill_achievements.py
"""
import argparse

from migrate import migrate
from db import get_connection
from config import load_config, pick
import achievements


def backfill(db_path: str, config_path=None):
    migrate(db_path)
    conn = get_connection(db_path)
    newly_unlocked = achievements.evaluate(conn, trigger=None, config_path=config_path)
    conn.close()
    if newly_unlocked:
        print(f"Unlocked {len(newly_unlocked)} achievement(s): {newly_unlocked}")
    else:
        print("No new achievements unlocked.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    backfill(db_path, config_path=args.config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_achievements.py -v -k idempotent`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backfill_achievements.py tests/integration/test_achievements.py
git commit -m "Add backfill_achievements.py one-off history sweep"
```

---

### Task 9: Full suite + manual verification against real data

**Files:** none (verification only, no code changes).

**Interfaces:** none — this task consumes everything built in Tasks 1-8.

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest -v`
Expected: all tests pass except this repo's known pre-existing unrelated failures (per project memory, currently 3 — confirm the count/names haven't changed before proceeding; do not treat a NEW failure as pre-existing without checking `git stash` against unmodified `main` first).

- [ ] **Step 2: Back up and copy the real dev database**

```bash
cp chess.db "chess.db.pre-achievements-backup-$(date +%Y%m%d%H%M%S).db"
cp chess.db /tmp/achievements_verify.db
```

- [ ] **Step 3: Run the backfill script against the copy**

```bash
python3 backfill_achievements.py --db /tmp/achievements_verify.db
```

Record the printed output (which achievement ids unlocked).

- [ ] **Step 4: Inspect the results directly**

```bash
sqlite3 /tmp/achievements_verify.db "SELECT achievement_id, unlocked_at, source_game_id FROM achievements_unlocked ORDER BY achievement_id;"
```

Sanity-check the output makes sense given the real dev DB's known shape (32,295 games, 1,495 analyzed, 81 distinct opening families) — e.g. `century_club` and `opening_explorer` should both be present (thresholds 100 and 20 respectively, both comfortably below the real totals); `drill_streak` may legitimately be absent if the real `srs_reviews` table is still empty (per project memory, it was empty as of the 2026-07-07 drill-down survey — check current state rather than assuming).

- [ ] **Step 5: Re-run the backfill to confirm idempotency against real data, then clean up**

```bash
python3 backfill_achievements.py --db /tmp/achievements_verify.db
```

Expected output: "No new achievements unlocked." Then:

```bash
rm /tmp/achievements_verify.db
```

Leave the timestamped backup from Step 2 on disk (matches this project's established backfill-verification precedent — kept as insurance, not deleted). No commit for this task; report the achievement-unlock findings back in conversation (and, if a durable record is wanted, as a project-memory update, not a plan-file edit).
