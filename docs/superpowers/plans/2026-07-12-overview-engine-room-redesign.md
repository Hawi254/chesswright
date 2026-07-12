# Overview Page Redesign ("Engine Room") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `dashboard/overview_view.py`'s current front-loaded single-column layout with the "Engine Room" visual identity (copper/cyan instrument-panel palette, hairline panels, a compact eval-rail signature) reorganized into three zones — Identity, Evolution, Coaching — per `docs/superpowers/specs/2026-07-12-overview-engine-room-redesign-design.md`.

**Architecture:** Backend data tasks first (three new small queries in `dashboard/data/overview.py`, one in `achievements.py`, one accessor in `dashboard/live_engine.py`) — all independently testable and independent of each other. Then one page-scoped CSS block added directly inside `overview_view.py` (not `theme.py` — keeps every other page's validated styling untouched). Then the view-layer rewrite that consumes everything. Then verification.

**Tech Stack:** Streamlit 1.58.0 (native components only, no new custom component), DuckDB (`db.games`/`db.moves` queries), sqlite3 (`achievements_unlocked` read), pytest.

## Global Constraints

- New color tokens (`copper`/`cyan`) are additive and CSS-scoped to Overview only — never edit `theme.py`'s `POSITIVE`/`NEGATIVE`/`ACCENT_GOLD`/`BG`/`CSS` constants. Reuse `theme.POSITIVE`/`theme.NEGATIVE` as-is for win/loss semantics.
- No new custom React/JS component. All new UI is native Streamlit + one page-scoped `<style>` block injected via `st.markdown(..., unsafe_allow_html=True)` inside `overview_view.py`'s own `render()`.
- No raw `<div>` hand-wrapped around native Streamlit widgets across multiple `st.markdown()` calls — confirmed absent anywhere in this codebase and confirmed unreliable (each `st.*` call emits an independent DOM node; a tag opened in one `st.markdown()` call does not actually nest subsequently-rendered native widgets). Every "card" panel uses `st.container(border=True, key="...")`, restyled via CSS targeting that container's real generated class — not hand-authored `<div class="card">` wrappers around chart/button calls.
- `achievements.py` is sqlite-only by design (no DuckDB) — the new milestones query must take a `sqlite3.Connection`, not `duck_conn`.
- Every new DB-backed function needs a test against `migrated_db`/`_duck_from_conn`, following the exact existing conventions in `tests/integration/test_data_layer.py` and `tests/integration/test_achievements.py` (no shared `insert_game` helper exists in `test_data_layer.py` — hand-write inline `INSERT` statements per test, matching current style).
- Do not fake data the app can't back for real. Confirmed during spec/plan research: there is **no** "last synced at" timestamp anywhere in this codebase — do not render one. The mockup's "last sync 2h ago" line is dropped; only real values ship (games/analyzed counts, engine connection state via `live_engine.get_engine_service()`, app version via `dashboard/version.py`).
- No fake/non-functional search box or `⌘K` shortcut on Overview — Global Search already exists in the real sidebar; Overview does not duplicate it.

**Explicit deferral:** the design spec's "brand mark" signature element (a small three-bar SVG next to "Chesswright" in the sidebar) is NOT built by this plan. It requires editing `app.py`'s sidebar chrome, which is global to every page — outside this plan's Overview-only blast radius (see Global Constraints above). It's a small, low-risk, one-time addition; worth a short separate follow-up plan rather than folding into this one and widening every task's file-touch surface.

---

### Task 1: Achievements milestones read query

**Files:**
- Modify: `achievements.py` (append new function, after `evaluate()` — anywhere below line 84 is fine, e.g. right after `evaluate()` ends)
- Test: `tests/integration/test_achievements.py` (append new test class)

**Interfaces:**
- Consumes: `achievements.CATALOG` (existing `list[Achievement]`, fields `id, name, description, category, triggers, check`), the existing `achievements_unlocked` table (`achievement_id TEXT PRIMARY KEY, unlocked_at TEXT NOT NULL, source_game_id TEXT`).
- Produces: `get_unlocked_achievements(conn: sqlite3.Connection, limit: int = 4) -> list[dict]`, each dict `{"achievement_id": str, "name": str, "description": str, "unlocked_at": str}`, ordered newest-`unlocked_at`-first. Used by Task 5's `cached_unlocked_achievements` wrapper.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_achievements.py`:

```python
@pytest.mark.integration
class TestGetUnlockedAchievements:
    def test_returns_empty_list_when_none_unlocked(self, migrated_db):
        from achievements import get_unlocked_achievements
        result = get_unlocked_achievements(migrated_db)
        assert result == []

    def test_returns_unlocked_achievements_newest_first(self, migrated_db):
        from achievements import get_unlocked_achievements, CATALOG
        first_id = CATALOG[0].id
        second_id = CATALOG[1].id
        migrated_db.execute(
            "INSERT INTO achievements_unlocked (achievement_id, unlocked_at, source_game_id) "
            "VALUES (?, ?, NULL)", (first_id, "2026-05-01T10:00:00"))
        migrated_db.execute(
            "INSERT INTO achievements_unlocked (achievement_id, unlocked_at, source_game_id) "
            "VALUES (?, ?, NULL)", (second_id, "2026-06-01T10:00:00"))
        migrated_db.commit()

        result = get_unlocked_achievements(migrated_db, limit=4)

        assert len(result) == 2
        assert result[0]["achievement_id"] == second_id
        assert result[0]["name"] == next(a.name for a in CATALOG if a.id == second_id)
        assert result[1]["achievement_id"] == first_id

    def test_respects_limit(self, migrated_db):
        from achievements import get_unlocked_achievements, CATALOG
        for i, ach in enumerate(CATALOG[:3]):
            migrated_db.execute(
                "INSERT INTO achievements_unlocked (achievement_id, unlocked_at, source_game_id) "
                "VALUES (?, ?, NULL)", (ach.id, f"2026-0{i+1}-01T10:00:00"))
        migrated_db.commit()

        result = get_unlocked_achievements(migrated_db, limit=2)

        assert len(result) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/integration/test_achievements.py::TestGetUnlockedAchievements -v`
Expected: FAIL with `ImportError: cannot import name 'get_unlocked_achievements'`

- [ ] **Step 3: Write the implementation**

Append to `achievements.py` (after `evaluate()`):

```python
def get_unlocked_achievements(conn: sqlite3.Connection, limit: int = 4) -> list[dict]:
    """Read-only: powers the dashboard's milestones row (Overview, Evolution
    zone). Joins achievements_unlocked against the in-memory CATALOG -- there
    is no achievements name/description table in SQLite, that metadata only
    ever lives in CATALOG."""
    rows = conn.execute(
        "SELECT achievement_id, unlocked_at FROM achievements_unlocked "
        "ORDER BY unlocked_at DESC LIMIT ?", (limit,)
    ).fetchall()
    by_id = {a.id: a for a in CATALOG}
    result = []
    for achievement_id, unlocked_at in rows:
        achievement = by_id.get(achievement_id)
        if achievement is None:
            continue
        result.append({
            "achievement_id": achievement_id,
            "name": achievement.name,
            "description": achievement.description,
            "unlocked_at": unlocked_at,
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/integration/test_achievements.py::TestGetUnlockedAchievements -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add achievements.py tests/integration/test_achievements.py
git commit -m "Add get_unlocked_achievements() read query for the Overview milestones row"
```

---

### Task 2: Overview snapshot queries (rating, streak, recent form)

**Files:**
- Modify: `dashboard/data/overview.py` (append 3 functions after `get_win_rate_by_color`, line 101)
- Modify: `dashboard/data/__init__.py` (add 3 names to the existing `from .overview import (...)` block, lines 37-40)
- Test: `tests/integration/test_data_layer.py` (append to existing `TestOverviewData` class, lines 60-79)

**Interfaces:**
- Consumes: `db.games` columns `player_rating`, `outcome_for_player`, `opponent_name`, `utc_date`, `utc_time`, `player_rating_change` (all confirmed present, all board-derived, no analysis dependency).
- Produces:
  - `get_rating_snapshot(duck_conn) -> dict` — `{"current_rating": int|None, "peak_rating": int|None}`.
  - `get_current_streak(duck_conn) -> dict` — `{"outcome": "win"|"loss"|"draw"|None, "length": int}`.
  - `get_recent_form(duck_conn, n: int = 5) -> pandas.DataFrame` — columns `outcome_for_player, opponent_name, utc_date, player_rating_change`, newest game first.
  - All three importable as `data.get_rating_snapshot`, `data.get_current_streak`, `data.get_recent_form` after Step 5. Used by Task 5's `cached_rating_snapshot`/`cached_current_streak`/`cached_recent_form` wrappers.

- [ ] **Step 1: Write the failing tests**

Append to the `TestOverviewData` class in `tests/integration/test_data_layer.py` (after `test_get_rating_trajectory_on_empty_db`):

```python
    def test_get_rating_snapshot_on_empty_db(self, migrated_db):
        from data.overview import get_rating_snapshot
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_rating_snapshot(duck)
            assert result == {"current_rating": None, "peak_rating": None}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_rating_snapshot_returns_most_recent_and_peak(self, migrated_db):
        migrated_db.execute(
            "INSERT INTO games (id, player_rating, utc_date, utc_time, outcome_for_player) "
            "VALUES ('g1', 1500, '2026.01.01', '10:00:00', 'win')")
        migrated_db.execute(
            "INSERT INTO games (id, player_rating, utc_date, utc_time, outcome_for_player) "
            "VALUES ('g2', 1650, '2026.03.01', '10:00:00', 'win')")
        migrated_db.execute(
            "INSERT INTO games (id, player_rating, utc_date, utc_time, outcome_for_player) "
            "VALUES ('g3', 1600, '2026.06.01', '10:00:00', 'loss')")
        migrated_db.commit()
        from data.overview import get_rating_snapshot
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_rating_snapshot(duck)
            assert result == {"current_rating": 1600, "peak_rating": 1650}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_current_streak_on_empty_db(self, migrated_db):
        from data.overview import get_current_streak
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_current_streak(duck)
            assert result == {"outcome": None, "length": 0}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_current_streak_counts_consecutive_same_outcome(self, migrated_db):
        rows = [
            ("g1", "win", "2026.01.01"),
            ("g2", "loss", "2026.01.02"),
            ("g3", "win", "2026.01.03"),
            ("g4", "win", "2026.01.04"),
            ("g5", "win", "2026.01.05"),
        ]
        for game_id, outcome, date in rows:
            migrated_db.execute(
                "INSERT INTO games (id, outcome_for_player, utc_date, utc_time) "
                "VALUES (?, ?, ?, '10:00:00')", (game_id, outcome, date))
        migrated_db.commit()
        from data.overview import get_current_streak
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_current_streak(duck)
            assert result == {"outcome": "win", "length": 3}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_recent_form_returns_last_n_games_newest_first(self, migrated_db):
        rows = [
            ("g1", "win", "Alice", "2026.01.01", 8),
            ("g2", "loss", "Bob", "2026.01.02", -6),
            ("g3", "draw", "Carol", "2026.01.03", 1),
        ]
        for game_id, outcome, opponent, date, delta in rows:
            migrated_db.execute(
                "INSERT INTO games (id, outcome_for_player, opponent_name, utc_date, utc_time, "
                "player_rating_change) VALUES (?, ?, ?, ?, '10:00:00', ?)",
                (game_id, outcome, opponent, date, delta))
        migrated_db.commit()
        from data.overview import get_recent_form
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_recent_form(duck, n=2)
            assert len(df) == 2
            assert df.iloc[0]["opponent_name"] == "Carol"
            assert df.iloc[0]["player_rating_change"] == 1
            assert df.iloc[1]["opponent_name"] == "Bob"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/integration/test_data_layer.py::TestOverviewData -v`
Expected: 5 new FAILs with `ImportError: cannot import name 'get_rating_snapshot'` (etc.)

- [ ] **Step 3: Write the implementation**

Append to `dashboard/data/overview.py` (after `get_win_rate_by_color`, end of file):

```python
def get_rating_snapshot(duck_conn):
    """Current rating (most recent game's player_rating) and all-time peak.
    Board-derived, same population as get_rating_trajectory -- no analysis
    needed."""
    row = duck_conn.execute("""
        SELECT
            (SELECT player_rating FROM db.games
             WHERE player_rating IS NOT NULL
             ORDER BY utc_date DESC, utc_time DESC LIMIT 1) AS current_rating,
            (SELECT MAX(player_rating) FROM db.games) AS peak_rating
    """).fetchone()
    return {"current_rating": row[0], "peak_rating": row[1]}


def get_current_streak(duck_conn):
    """Current ACTIVE streak (consecutive most-recent games sharing the same
    outcome) -- distinct from achievements.py's _longest_win_streak_end,
    which computes the longest-EVER streak for unlock checks. All games, not
    analyzed-only: outcome_for_player needs no engine analysis."""
    df = duck_conn.execute("""
        SELECT outcome_for_player FROM db.games
        WHERE outcome_for_player IS NOT NULL
        ORDER BY utc_date DESC, utc_time DESC
    """).fetchdf()
    if len(df) == 0:
        return {"outcome": None, "length": 0}
    outcomes = df["outcome_for_player"].tolist()
    current = outcomes[0]
    length = 0
    for outcome in outcomes:
        if outcome != current:
            break
        length += 1
    return {"outcome": current, "length": length}


def get_recent_form(duck_conn, n=5):
    """Last n games for Overview's recent-form ticker. All board-derived
    (result/opponent/date/rating-change), no analysis dependency."""
    return duck_conn.execute("""
        SELECT outcome_for_player, opponent_name, utc_date, player_rating_change
        FROM db.games
        ORDER BY utc_date DESC, utc_time DESC
        LIMIT ?
    """, [n]).fetchdf()
```

- [ ] **Step 4: Register the new functions in the package export list**

In `dashboard/data/__init__.py`, change:

```python
from .overview import (
    get_rating_trajectory, get_acpl_trajectory, get_win_rate_by_color,
    get_progress_by_month,
)
```

to:

```python
from .overview import (
    get_rating_trajectory, get_acpl_trajectory, get_win_rate_by_color,
    get_progress_by_month, get_rating_snapshot, get_current_streak,
    get_recent_form,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/integration/test_data_layer.py::TestOverviewData -v`
Expected: 7 passed (2 existing + 5 new)

- [ ] **Step 6: Commit**

```bash
git add dashboard/data/overview.py dashboard/data/__init__.py tests/integration/test_data_layer.py
git commit -m "Add rating-snapshot, current-streak, and recent-form queries for Overview"
```

---

### Task 3: Engine status accessor

**Files:**
- Modify: `dashboard/live_engine.py` (append new function after `get_engine_service()`, line 144 onward)
- Test: `tests/unit/test_live_engine.py` (new file)

**Interfaces:**
- Consumes: the existing `get_engine_service() -> EngineService | None` (module-level, `@st.cache_resource`-wrapped) and `EngineService`'s private `_dead: bool` / `_engine_version: str` attributes — read from within `live_engine.py` itself, not from the view layer, so no other module reaches into `EngineService` internals.
- Produces: `get_engine_status_summary() -> dict`, `{"connected": bool, "version": str|None}`. Used by Task 5's status strip.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_live_engine.py`:

```python
import live_engine


class _FakeEngineService:
    def __init__(self, dead, version):
        self._dead = dead
        self._engine_version = version


def test_get_engine_status_summary_when_no_engine_detected(monkeypatch):
    monkeypatch.setattr(live_engine, "get_engine_service", lambda: None)
    result = live_engine.get_engine_status_summary()
    assert result == {"connected": False, "version": None}


def test_get_engine_status_summary_when_engine_connected(monkeypatch):
    fake = _FakeEngineService(dead=False, version="Stockfish 16")
    monkeypatch.setattr(live_engine, "get_engine_service", lambda: fake)
    result = live_engine.get_engine_status_summary()
    assert result == {"connected": True, "version": "Stockfish 16"}


def test_get_engine_status_summary_when_engine_dead(monkeypatch):
    fake = _FakeEngineService(dead=True, version="Stockfish 16")
    monkeypatch.setattr(live_engine, "get_engine_service", lambda: fake)
    result = live_engine.get_engine_status_summary()
    assert result == {"connected": False, "version": "Stockfish 16"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_live_engine.py -v`
Expected: FAIL with `AttributeError: module 'live_engine' has no attribute 'get_engine_status_summary'`

- [ ] **Step 3: Write the implementation**

Append to `dashboard/live_engine.py` (after `get_engine_service()`):

```python
def get_engine_status_summary() -> dict:
    """Cheap, read-only status for display (Overview's status strip). Reuses
    the cached get_engine_service() singleton -- never starts a new engine
    process just to check status."""
    service = get_engine_service()
    if service is None:
        return {"connected": False, "version": None}
    return {"connected": not service._dead, "version": service._engine_version or None}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_live_engine.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/live_engine.py tests/unit/test_live_engine.py
git commit -m "Add get_engine_status_summary() accessor for the Overview status strip"
```

---

### Task 4: Overview-scoped CSS

**Files:**
- Modify: `dashboard/overview_view.py` (add a new module-level `OVERVIEW_CSS` constant, near the top of the file after imports)

**Interfaces:**
- Consumes: `theme.POSITIVE`, `theme.NEGATIVE` (existing, reused not redefined).
- Produces: `OVERVIEW_CSS: str` — a complete `<style>...</style>` block, injected once per Overview render by Task 5's `render()`. Class names this provides for Task 5 to use: `.cw-ov` (wrapper), `.cw-ov-zone-head`, `.cw-ov-eyebrow`, `.cw-ov-trait-tag`, `.cw-ov-rating-num`, `.cw-ov-rating-trend`, `.cw-ov-exec-summary`, `.cw-ov-milestone`, `.cw-ov-ticker` (+ `.cw-ov-res.w/.l/.d`, `.cw-ov-delta.up/.down`), `.cw-ov-chip`, `.cw-ov-balance-row` (+ `.strength`/`.weakness` modifier), `.cw-ov-severity` (+ `.on` modifier), `.cw-ov-status-strip`, `.cw-ov-rail` (+ `.cw-ov-rail-fill`, `.cw-ov-rail-mid`), plus container-scoping classes `.st-key-cw_ov_progress`, `.st-key-cw_ov_recent_form`, `.st-key-cw_ov_highlight`, `.st-key-cw_ov_coaching_list` (Streamlit's `key=` parameter on `st.container` — confirm the exact generated class name live in Task 7; if it does not match `.st-key-<key>`, the fallback documented in Task 7 Step 2 applies).

**Note on scope reduction from the mockup** (see design spec's Non-goals + this plan's Global Constraints): no fake sidebar/topbar/search/last-sync chrome. The eval rail is reduced from a full-page rail to a compact, fixed-height element scoped to the Identity zone only — Streamlit has no confirmed column-height-stretch CSS today (verified: `theme.py` has no such rule), so a rail that must dynamically match an unpredictable, dynamically-tall content column is not something to build without new, unverified CSS work. A modest fixed-height rail next to the identity strip (whose content height is short and predictable) avoids that risk entirely while preserving the signature element's visual idea.

- [ ] **Step 1: Add the CSS constant**

In `dashboard/overview_view.py`, after the existing imports (after `from game_explorer_view import cached_game_explorer_table`), add:

```python
OVERVIEW_CSS = f"""<style>
.cw-ov {{ --cw-canvas:#0B0F14; --cw-panel:#131A22; --cw-panel-2:#0F141B;
    --cw-copper:#E08A3C; --cw-cyan:#4FB8C4; --cw-text:#ECEEF0;
    --cw-muted:#ECEEF099; --cw-line:#232B37; --cw-line-soft:#1a212b; }}

.cw-ov-zone-head {{ display:flex; align-items:baseline; gap:.8rem; margin:1.6rem 0 1rem; }}
.cw-ov-eyebrow {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.68rem;
    letter-spacing:.1em; text-transform:uppercase; color:var(--cw-cyan); white-space:nowrap; }}
.cw-ov-zone-head h2 {{ margin:0; font-family:"Archivo Narrow","Arial Narrow",sans-serif;
    font-weight:700; font-size:1.1rem; color:var(--cw-text); }}
.cw-ov-zone-head-rule {{ flex:1; height:1px; background:var(--cw-line); }}

.cw-ov-trait-tag {{ display:inline-block; font-family:"Archivo Narrow","Arial Narrow",sans-serif;
    font-size:.74rem; font-weight:600; padding:.4rem .75rem; margin:0 .4rem .4rem 0;
    border-radius:4px; background:var(--cw-panel); border:1px solid var(--cw-line); color:var(--cw-text); }}
.cw-ov-rating-num {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace;
    font-variant-numeric:tabular-nums; font-size:1.5rem; font-weight:600; color:var(--cw-text); }}
.cw-ov-rating-trend {{ font-size:.78rem; margin-left:.4rem; }}
.cw-ov-rating-trend.up {{ color:{theme.POSITIVE}; }}
.cw-ov-rating-trend.down {{ color:{theme.NEGATIVE}; }}
.cw-ov-exec-summary {{ font-style:italic; font-size:.98rem; line-height:1.6; color:var(--cw-muted);
    max-width:74ch; border-left:2px solid var(--cw-line); padding-left:.9rem; margin:0 0 1rem; }}

.cw-ov-status-strip {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.72rem;
    color:var(--cw-muted); display:flex; align-items:center; gap:.5rem; margin-bottom:.6rem; }}
.cw-ov-status-strip .dot {{ width:6px; height:6px; border-radius:50%; flex-shrink:0; }}
.cw-ov-status-strip .dot.on {{ background:var(--cw-cyan); }}
.cw-ov-status-strip .dot.off {{ background:var(--cw-line); }}

.cw-ov-rail {{ position:relative; background:var(--cw-panel-2); border-radius:3px; overflow:hidden;
    height:110px; border:1px solid var(--cw-line); }}
.cw-ov-rail-mid {{ position:absolute; left:0; right:0; top:50%; height:1px;
    background:rgba(236,238,240,.28); z-index:2; }}
.cw-ov-rail-fill {{ position:absolute; left:0; right:0; bottom:0; width:100%; z-index:1;
    background:linear-gradient(180deg, var(--cw-copper), #a95f22); }}
@keyframes cw-ov-rail-rise {{ from {{ height:50%; }} to {{ height: var(--cw-rail-target, 50%); }} }}

.cw-ov-milestone {{ display:inline-flex; align-items:center; gap:.55rem; background:var(--cw-panel);
    border:1px solid var(--cw-line); border-radius:5px; padding:.6rem .9rem; margin:0 .5rem .5rem 0;
    white-space:nowrap; }}
.cw-ov-milestone .tick {{ width:5px; height:5px; border-radius:50%; background:var(--cw-copper); flex-shrink:0; }}
.cw-ov-milestone .label {{ font-family:"Archivo Narrow","Arial Narrow",sans-serif; font-size:.78rem; color:var(--cw-text); }}
.cw-ov-milestone .date {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.68rem;
    color:var(--cw-muted); margin-left:.3rem; }}

.cw-ov-ticker {{ width:100%; border-collapse:collapse; }}
.cw-ov-ticker tr {{ border-bottom:1px solid var(--cw-line-soft); }}
.cw-ov-ticker tr:last-child {{ border-bottom:none; }}
.cw-ov-ticker td {{ padding:.5rem .3rem; }}
.cw-ov-res {{ font-family:"Archivo Narrow","Arial Narrow",sans-serif; font-size:.68rem; font-weight:700;
    padding:.15rem .5rem; border-radius:3px; letter-spacing:.04em; }}
.cw-ov-res.w {{ background:{theme.POSITIVE}29; color:{theme.POSITIVE}; }}
.cw-ov-res.l {{ background:{theme.NEGATIVE}29; color:{theme.NEGATIVE}; }}
.cw-ov-res.d {{ background:var(--cw-panel-2); color:var(--cw-muted); }}
.cw-ov-delta {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.8rem;
    font-variant-numeric:tabular-nums; text-align:right; }}
.cw-ov-delta.up {{ color:{theme.POSITIVE}; }}
.cw-ov-delta.down {{ color:{theme.NEGATIVE}; }}

.cw-ov-chip {{ font-family:"SF Mono","JetBrains Mono",Consolas,monospace; font-size:.66rem;
    padding:.2rem .55rem; border-radius:3px; background:var(--cw-panel-2); color:var(--cw-cyan);
    border:1px solid var(--cw-line); display:inline-block; margin:0 .35rem .35rem 0; }}

.cw-ov-balance-row {{ display:flex; align-items:flex-start; gap:.55rem; padding:.55rem 0;
    border-bottom:1px solid var(--cw-line-soft); }}
.cw-ov-balance-row:last-child {{ border-bottom:none; }}
.cw-ov-balance-row .mk {{ width:7px; height:7px; border-radius:50%; margin-top:.4rem; flex-shrink:0; }}
.cw-ov-balance-row.strength .mk {{ background:{theme.POSITIVE}; }}
.cw-ov-balance-row.weakness .mk {{ background:var(--cw-copper); }}
.cw-ov-balance-row .t {{ font-size:.86rem; color:var(--cw-text); font-weight:600; margin-bottom:.15rem;
    font-family:"Archivo Narrow","Arial Narrow",sans-serif; }}
.cw-ov-balance-row .d {{ font-size:.8rem; color:var(--cw-muted); line-height:1.45; }}

.cw-ov-severity {{ display:inline-flex; gap:3px; vertical-align:middle; margin-right:.6rem; }}
.cw-ov-severity .d {{ width:6px; height:6px; border-radius:50%; background:var(--cw-line); display:inline-block; }}
.cw-ov-severity .d.on {{ background:var(--cw-copper); }}

.st-key-cw_ov_progress[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cw_ov_recent_form[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cw_ov_highlight[data-testid="stVerticalBlockBorderWrapper"],
.st-key-cw_ov_coaching_list[data-testid="stVerticalBlockBorderWrapper"] {{
    background-color:var(--cw-panel); border:1px solid var(--cw-line); border-radius:6px;
    box-shadow:0 1px 0 rgba(255,255,255,.04) inset, 0 8px 22px rgba(0,0,0,.38);
}}

@media (prefers-reduced-motion: reduce) {{
    .cw-ov-rail-fill {{ animation-duration:.01ms !important; }}
}}
</style>"""
```

- [ ] **Step 2: Smoke-test the constant is well-formed**

Add to `dashboard/test_app.py` (or wherever simple import-level checks live in that file):

```python
def test_overview_css_is_well_formed_style_block():
    from overview_view import OVERVIEW_CSS
    assert OVERVIEW_CSS.strip().startswith("<style>")
    assert OVERVIEW_CSS.strip().endswith("</style>")
    assert ".cw-ov-rail" in OVERVIEW_CSS
    assert "theme.POSITIVE" not in OVERVIEW_CSS  # must be interpolated, not literal
```

Run: `.venv/bin/pytest dashboard/test_app.py -k test_overview_css_is_well_formed_style_block -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add dashboard/overview_view.py dashboard/test_app.py
git commit -m "Add page-scoped Engine Room CSS for the Overview redesign"
```

---

### Task 5: Rewrite Overview's layout into three zones

**Files:**
- Modify: `dashboard/overview_view.py` (imports, cached wrappers, `render()`, and all `_render_*` helpers)

**Interfaces:**
- Consumes: everything from Tasks 1-4 (`achievements.get_unlocked_achievements`, `data.get_rating_snapshot`/`get_current_streak`/`get_recent_form`, `live_engine.get_engine_status_summary`, `OVERVIEW_CSS`) plus existing `cached_headline_stats`, `cached_career_findings` (fields confirmed: `title, headline, detail, severity ("low"/"medium"/"high"), category, polarity ("strength"/"weakness"/"mixed"/"neutral")`), `cached_game_explorer_table`, `theme.chip_row_html`, `theme.BADGE_LEGEND`, `charts.line_chart`.
- Produces: `render(...)` — same public signature as today (`self_page, detail_page, *, patterns_page=None, matchups_page=None, endings_page=None, highlights_page=None, insights_page=None, openings_page=None`), no signature change, so `app.py`'s existing call site needs no edit.

- [ ] **Step 1: Update imports**

At the top of `dashboard/overview_view.py`, change:

```python
import html
import streamlit as st

import charts
import data
import narrative
import theme
from _common import get_connections
from cached_queries import cached_career_findings, cached_headline_stats
from game_explorer_view import cached_game_explorer_table
```

to:

```python
import html
import streamlit as st

import achievements
import charts
import data
import live_engine
import narrative
import theme
from _common import get_connections
from cached_queries import cached_career_findings, cached_headline_stats
from game_explorer_view import cached_game_explorer_table
from version import __version__
```

- [ ] **Step 2: Add new cached wrappers**

After the existing `cached_win_rate_by_color`/`cached_progress_by_month` wrappers (before `def render(`), add:

```python
@st.cache_data(show_spinner="Loading your rating snapshot…")
def cached_rating_snapshot(_duck_conn):
    return data.get_rating_snapshot(_duck_conn)


@st.cache_data(show_spinner="Loading your current streak…")
def cached_current_streak(_duck_conn):
    return data.get_current_streak(_duck_conn)


@st.cache_data(show_spinner="Loading your recent games…")
def cached_recent_form(_duck_conn):
    return data.get_recent_form(_duck_conn, n=5)


@st.cache_data(show_spinner="Loading your milestones…")
def cached_unlocked_achievements(_sqlite_conn):
    return achievements.get_unlocked_achievements(_sqlite_conn, limit=4)
```

- [ ] **Step 3: Add the polarity-split helper**

Replace the `_FINDING_DEST` dict's neighboring `_render_focus_card` function (delete it — its job is absorbed into the new coaching zone) but keep `_FINDING_DEST` itself unchanged (still used for routing). Add this new helper right after `_FINDING_DEST`:

```python
def _split_by_polarity(findings):
    """(strengths, weaknesses) -- top 2 of each, by the order
    get_career_findings() already returns (severity-ranked)."""
    strengths = [f for f in findings if f["polarity"] == "strength"][:2]
    weaknesses = [f for f in findings if f["polarity"] in ("weakness", "mixed")][:2]
    return strengths, weaknesses


_SEVERITY_DOTS = {"high": 3, "medium": 2, "low": 1}
```

- [ ] **Step 4: Write the identity-zone renderer**

Delete the old `_render_focus_card` function entirely (its content is superseded). In its place, add:

```python
def _render_identity_zone(stats, rating_snapshot, streak, strengths, weaknesses, narrative_text):
    st.markdown('<div class="cw-ov-zone-head"><span class="cw-ov-eyebrow">Who you are</span>'
                '<h2>Your chess identity</h2><span class="cw-ov-zone-head-rule"></span></div>',
                unsafe_allow_html=True)

    tags = [f["title"] for f in (strengths + weaknesses)[:3]]

    rail_col, id_col = st.columns([1, 14])
    with rail_col:
        win_pct = stats.get("win_pct") or 0
        st.markdown(
            f'<div class="cw-ov-rail" style="--cw-rail-target: {win_pct:.0f}%;">'
            f'<div class="cw-ov-rail-mid"></div>'
            f'<div class="cw-ov-rail-fill" '
            f'style="height:{win_pct:.0f}%; animation: cw-ov-rail-rise 1.4s cubic-bezier(.16,.9,.25,1) .1s both;">'
            f'</div></div>', unsafe_allow_html=True)
    with id_col:
        tags_html = "".join(f'<span class="cw-ov-trait-tag">{html.escape(t)}</span>' for t in tags)
        st.markdown(f'<div>{tags_html}</div>', unsafe_allow_html=True)

        current = rating_snapshot.get("current_rating")
        peak = rating_snapshot.get("peak_rating")
        if current is not None:
            trend_html = ""
            if peak is not None and current < peak:
                trend_html = f'<span class="cw-ov-rating-trend down">peak {peak}</span>'
            elif peak is not None:
                trend_html = '<span class="cw-ov-rating-trend up">at peak</span>'
            streak_bit = ""
            if streak.get("length", 0) >= 2:
                streak_bit = f' · {streak["length"]}-game {streak["outcome"]} streak'
            st.markdown(
                f'<div><span class="cw-ov-rating-num">{current}</span>{trend_html}'
                f'<div style="font-family:\'SF Mono\',monospace; font-size:.68rem; color:var(--cw-muted); '
                f'margin-top:.2rem;">Current rating{streak_bit}</div></div>',
                unsafe_allow_html=True)

    st.markdown(f'<p class="cw-ov-exec-summary">{html.escape(narrative_text)}</p>',
                unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total games", f"{stats['total_games']:,}",
                help="Every game synced from your online accounts.")
    col2.metric("Analyzed games", f"{stats['analyzed_games']:,}",
                help="Games your engine has analyzed so far — accuracy stats only "
                     "count these. Run more batches from Analysis Jobs to grow this.")
    col3.metric("Win rate", f"{stats['win_pct']:.1f}%" if stats['win_pct'] is not None else "--",
                help="Wins as a share of all games.")
    col4.metric("ACPL", f"{stats['acpl']:.1f}" if stats['acpl'] is not None else "--",
                help="Average centipawn loss — measures move accuracy across analyzed games. Lower is better.")
```

- [ ] **Step 5: Write the evolution-zone renderer**

Add:

```python
def _render_evolution_zone(duck_conn, sqlite_conn, top_game, self_page, detail_page):
    st.markdown('<div class="cw-ov-zone-head"><span class="cw-ov-eyebrow">How you\'ve evolved</span>'
                '<h2>Progress &amp; milestones</h2><span class="cw-ov-zone-head-rule"></span></div>',
                unsafe_allow_html=True)

    with st.container(border=True, key="cw_ov_progress"):
        st.subheader("Rating & accuracy over time")
        rating_df = cached_rating_trajectory(duck_conn)
        acpl_df = cached_acpl_trajectory(duck_conn)
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.plotly_chart(charts.line_chart(rating_df, "year", "avg_rating", theme.ACCENT_GOLD,
                                                x_title="Year", y_title="Average rating", height=200),
                             theme=None, width='stretch')
        with chart_col2:
            acpl_df = acpl_df.assign(
                hover_coverage=acpl_df.apply(
                    lambda r: f"{int(r.n_games)} of {int(r.n_total_games)} games ({r.coverage_pct:.1f}%)",
                    axis=1))
            st.plotly_chart(charts.line_chart(acpl_df, "year", "acpl", theme.NEGATIVE, height=200,
                                                x_title="Year", y_title="ACPL",
                                                hover_extra=("hover_coverage", "Analyzed")),
                             theme=None, width='stretch')
        if len(acpl_df) >= 2:
            min_row = acpl_df.loc[acpl_df.coverage_pct.idxmin()]
            max_row = acpl_df.loc[acpl_df.coverage_pct.idxmax()]
            if max_row.coverage_pct >= 2 * max(min_row.coverage_pct, 0.1):
                st.caption(f"⚠️ Analysis coverage varies sharply by year — from "
                           f"{min_row.coverage_pct:.1f}% in {int(min_row.year)} to "
                           f"{max_row.coverage_pct:.1f}% in {int(max_row.year)}.")

    milestones = cached_unlocked_achievements(sqlite_conn)
    if milestones:
        chips = "".join(
            f'<div class="cw-ov-milestone"><span class="tick"></span>'
            f'<span class="label">{html.escape(m["name"])}</span>'
            f'<span class="date">{html.escape(m["unlocked_at"][:10])}</span></div>'
            for m in milestones)
        st.markdown(f'<div>{chips}</div>', unsafe_allow_html=True)

    with st.container(border=True, key="cw_ov_recent_form"):
        st.subheader("Recent form")
        form_df = cached_recent_form(duck_conn)
        if len(form_df) == 0:
            st.caption("No games yet.")
        else:
            rows_html = ""
            for _, row in form_df.iterrows():
                outcome = row["outcome_for_player"]
                res_class = {"win": "w", "loss": "l", "draw": "d"}.get(outcome, "d")
                delta = row["player_rating_change"]
                delta_html = "—"
                if delta is not None:
                    delta_class = "up" if delta >= 0 else "down"
                    sign = "+" if delta >= 0 else ""
                    delta_html = f'<span class="cw-ov-delta {delta_class}">{sign}{int(delta)}</span>'
                rows_html += (
                    f'<tr><td><span class="cw-ov-res {res_class}">{outcome.upper()}</span></td>'
                    f'<td>{html.escape(row["opponent_name"] or "Unknown")}</td>'
                    f'<td style="color:var(--cw-muted); font-size:.8rem;">{row["utc_date"]}</td>'
                    f'<td>{delta_html}</td></tr>')
            st.markdown(f'<table class="cw-ov-ticker">{rows_html}</table>', unsafe_allow_html=True)

    if top_game is not None:
        with st.container(border=True, key="cw_ov_highlight"):
            st.subheader("Career highlight")
            chips_html = theme.chip_row_html(top_game)
            if chips_html:
                st.markdown(chips_html, unsafe_allow_html=True)
                st.caption(theme.BADGE_LEGEND)
            st.write(f"vs. {top_game.opponent_name} on {top_game.utc_date} "
                     f"({top_game.outcome_for_player})")
            if st.button("View this game →", key="cw_ov_view_highlight"):
                st.session_state["selected_game_id"] = top_game.game_id
                st.session_state["return_page"] = self_page
                st.session_state["return_page_label"] = "Overview"
                st.switch_page(detail_page)
```

- [ ] **Step 6: Write the coaching-zone renderer**

Add:

```python
def _render_coaching_zone(strengths, weaknesses, findings, sqlite_conn, insights_page, page_refs):
    st.markdown('<div class="cw-ov-zone-head"><span class="cw-ov-eyebrow">What to work on</span>'
                '<h2>Your coaching plan</h2><span class="cw-ov-zone-head-rule"></span></div>',
                unsafe_allow_html=True)

    if strengths or weaknesses:
        bal_col1, bal_col2 = st.columns(2)
        with bal_col1:
            st.markdown('<div style="font-family:\'Archivo Narrow\',sans-serif; font-size:.7rem; '
                        f'letter-spacing:.12em; text-transform:uppercase; color:{theme.POSITIVE}; '
                        'font-weight:700; margin-bottom:.6rem;">Strengths</div>', unsafe_allow_html=True)
            for f in strengths:
                st.markdown(
                    f'<div class="cw-ov-balance-row strength"><span class="mk"></span><div>'
                    f'<div class="t">{html.escape(f["title"])}</div>'
                    f'<div class="d">{html.escape(f["detail"])}</div></div></div>',
                    unsafe_allow_html=True)
            if not strengths:
                st.caption("Nothing surfaced yet — check back after more games are analyzed.")
        with bal_col2:
            st.markdown('<div style="font-family:\'Archivo Narrow\',sans-serif; font-size:.7rem; '
                        'letter-spacing:.12em; text-transform:uppercase; color:var(--cw-copper); '
                        'font-weight:700; margin-bottom:.6rem;">Focus areas</div>', unsafe_allow_html=True)
            for f in weaknesses:
                st.markdown(
                    f'<div class="cw-ov-balance-row weakness"><span class="mk"></span><div>'
                    f'<div class="t">{html.escape(f["title"])}</div>'
                    f'<div class="d">{html.escape(f["detail"])}</div></div></div>',
                    unsafe_allow_html=True)
            if not weaknesses:
                st.caption("Nothing surfaced yet — check back after more games are analyzed.")

    ranked = sorted(weaknesses, key=lambda f: _SEVERITY_DOTS.get(f["severity"], 0), reverse=True)[:3]
    if ranked:
        with st.container(border=True, key="cw_ov_coaching_list"):
            for f in ranked:
                dots_on = _SEVERITY_DOTS.get(f["severity"], 0)
                dots_html = "".join(
                    f'<span class="d{" on" if i < dots_on else ""}"></span>' for i in range(3))
                ref_key, dest_name, dest_tab = _FINDING_DEST.get(f["title"], (None, None, None))
                dest_page = page_refs.get(ref_key) if ref_key else None
                row_col, link_col = st.columns([6, 1])
                with row_col:
                    st.markdown(
                        f'<div><span class="cw-ov-severity">{dots_html}</span>'
                        f'<strong>{html.escape(f["title"])}</strong><br>'
                        f'<span style="color:var(--cw-muted); font-size:.85rem;">{html.escape(f["detail"])}</span>'
                        f'</div>', unsafe_allow_html=True)
                with link_col:
                    if dest_page is not None:
                        if st.button(dest_name or "View", key=f"cw_ov_coach_{f['title']}"):
                            st.switch_page(dest_page)

    top_weakness = ranked[0]["title"] if ranked else None
    cached = data.get_cached_narrative(sqlite_conn, "coaching", "recommendations")
    cta_col, links_col = st.columns([2, 3])
    with cta_col:
        if top_weakness:
            st.caption(f"Because **{top_weakness}** is your top focus area —")
        button_label = "View your coaching plan →" if cached else "Get your coaching plan →"
        if st.button(button_label, key="cw_ov_coaching_cta") and insights_page is not None:
            st.switch_page(insights_page)
    with links_col:
        links = [
            ("insights", "🔍 Insights", page_refs.get("insights_page")),
            ("patterns", "📊 Patterns & Tendencies", page_refs.get("patterns_page")),
            ("openings", "♟️ Openings & Repertoire", page_refs.get("openings_page")),
        ]
        links = [(key, label, page) for key, label, page in links if page is not None]
        if links:
            cols = st.columns(len(links))
            for col, (key, label, page) in zip(cols, links):
                with col:
                    if st.button(label, key=f"cw_ov_quick_{key}", width='stretch'):
                        st.switch_page(page)
```

- [ ] **Step 7: Write the status strip and rewrite `render()`**

Add this small helper right before `render()`:

```python
def _status_strip_html(stats, engine_status):
    dot_class = "on" if engine_status["connected"] else "off"
    version_bit = f'Stockfish {engine_status["version"]}' if engine_status["version"] else "Engine not detected"
    return (
        f'<div class="cw-ov-status-strip"><span class="dot {dot_class}"></span>'
        f'Chesswright v{__version__} · {stats["total_games"]:,} games · '
        f'{stats["analyzed_games"]:,} analyzed · {version_bit}</div>')
```

Replace the entire `render()` function with:

```python
def render(self_page, detail_page, *, patterns_page=None, matchups_page=None,
           endings_page=None, highlights_page=None, insights_page=None,
           openings_page=None):
    sqlite_conn, duck_conn = get_connections()
    st.markdown(OVERVIEW_CSS, unsafe_allow_html=True)
    st.title("Overview")

    if st.session_state.pop("just_completed_onboarding", False):
        st.info("Your starter batch is analyzed and ready. Use the sidebar to explore — "
                "each section looks at your games from a different angle.")

    stats = cached_headline_stats(duck_conn, sqlite_conn)
    engine_status = live_engine.get_engine_status_summary()
    st.markdown(_status_strip_html(stats, engine_status), unsafe_allow_html=True)

    rating_df = cached_rating_trajectory(duck_conn)
    rating_snapshot = cached_rating_snapshot(duck_conn)
    streak = cached_current_streak(duck_conn)
    explorer_df = cached_game_explorer_table(duck_conn)
    top_game = explorer_df.iloc[0] if len(explorer_df) else None

    findings = []
    if stats.get("analyzed_games", 0) > 0:
        findings = cached_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))
    strengths, weaknesses = _split_by_polarity(findings)

    narrative_text = narrative.generate_career_narrative(stats, rating_df, top_game)

    page_refs = {
        "patterns_page": patterns_page, "matchups_page": matchups_page,
        "endings_page": endings_page, "highlights_page": highlights_page,
        "insights_page": insights_page, "openings_page": openings_page,
    }

    _render_identity_zone(stats, rating_snapshot, streak, strengths, weaknesses, narrative_text)
    _render_evolution_zone(duck_conn, sqlite_conn, top_game, self_page, detail_page)
    _render_coaching_zone(strengths, weaknesses, findings, sqlite_conn, insights_page, page_refs)
```

Delete the now-unused `_render_coaching_teaser` and `_render_quick_explore` functions (both fully absorbed into `_render_coaching_zone` above).

- [ ] **Step 8: Run the existing Overview-related test suite**

Run: `.venv/bin/pytest dashboard/test_app.py tests/integration/test_data_layer.py::TestOverviewData tests/integration/test_achievements.py -v`
Expected: all pass except any test that was already failing before this plan started (confirm the pre-existing baseline first with `git stash` if any unexpected failure appears — see project convention of never assuming a new failure is pre-existing without checking).

- [ ] **Step 9: Commit**

```bash
git add dashboard/overview_view.py
git commit -m "Rewrite Overview into three zones: identity, evolution, coaching"
```

---

### Task 6: Extend Streamlit AppTest smoke coverage

**Files:**
- Modify: `dashboard/test_app.py` (find the existing Overview `AppTest` test — search for `"Overview"` — and extend it; do not remove existing assertions)

**Interfaces:**
- Consumes: `streamlit.testing.v1.AppTest`, `APP_PATH` (module-level constant already defined at `dashboard/test_app.py:15`, `str(pathlib.Path(__file__).resolve().parent / "app.py")`). Confirmed exact existing pattern (`dashboard/test_app.py:37-44`, `test_app_runs_without_exception`): `at = AppTest.from_file(APP_PATH)`, `at.run(timeout=60)`, `assert not at.exception`. `AppTest.from_file(APP_PATH)` always renders Overview specifically, since it's `app.py`'s `default=True` page (confirmed by that test's own docstring) — no page-switch needed. Confirmed element-access pattern for asserting on rendered content (`dashboard/test_app.py:109`, `test_headline_metrics_match_known_values`): `{m.label: m.value for m in at.metric}` for `st.metric` calls; the equivalent for raw `st.markdown()` output is `at.markdown` (list of markdown elements, each with a `.value` string).

- [ ] **Step 1: Write the failing test**

Add to `dashboard/test_app.py`, right after `test_app_runs_without_exception` (after line 44):

```python
def test_overview_page_shows_three_zone_headers():
    """Confirms the Task 5 rewrite actually renders all three zones, not
    just that the page loads without an exception."""
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    assert not at.exception, f"App raised: {at.exception}"
    page_text = "\n".join(m.value for m in at.markdown)
    assert "Your chess identity" in page_text
    assert "Progress" in page_text and "milestones" in page_text
    assert "Your coaching plan" in page_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest dashboard/test_app.py -k test_overview_page_shows_three_zone_headers -v`
Expected: at this point in the plan (after Task 5), this should already PASS, since Task 5's zone headers already exist. If it fails, treat that as a real regression to investigate now — do not proceed to Step 3 by loosening the assertions to match whatever text happens to be present.

- [ ] **Step 3: Run full file to confirm no regression**

Run: `.venv/bin/pytest dashboard/test_app.py -v`
Expected: all pass (this file has no pytest markers gating it — confirmed it's runnable directly as `python3 dashboard/test_app.py` per its own module docstring, and also collectible by plain `pytest`).

- [ ] **Step 4: Commit**

```bash
git add dashboard/test_app.py
git commit -m "Extend Overview AppTest coverage for the three-zone layout"
```

---

### Task 7: Full suite + live verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -x -q` (or without `-x` if you want the complete failure list rather than stopping at the first)
Expected: all pass except the project's documented pre-existing failures (confirm the current baseline with `git log`/prior CI results before this branch's work — do not assume any new failure is "pre-existing" without checking via `git stash`).

- [ ] **Step 2: Live-verify via the `verify-live-dashboard` skill**

Launch a scratch-config copy of the dashboard against the real dev `chess.db` (per this project's established `verify-live-dashboard` skill / scratch-config pattern) and check, in a real browser, all of the following — each is a specific, previously-flagged uncertainty from the design spec and this plan, not a generic smoke check:

1. **Container CSS scoping actually works.** Confirm the four `st.container(border=True, key="cw_ov_...")` panels render with the new copper/cyan hairline styling (not default Streamlit gray boxes). If they don't, the `.st-key-<key>` selector assumption was wrong — inspect the real DOM (browser devtools) for the actual class Streamlit 1.58 generates on that container, and update `OVERVIEW_CSS`'s selectors in Task 4 to match.
2. **No CSS leak to other pages.** Navigate from Overview to a different page (e.g. Patterns & Tendencies) and confirm its existing `st.container(border=True)` panels still render in the OLD default style, not copper/cyan — confirms `OVERVIEW_CSS`'s page-scoped injection lifecycle (only injected while Overview's `render()` runs) does not bleed into other pages.
3. **Eval rail renders sensibly.** Confirm the compact rail in the Identity zone shows a filled bar roughly matching the real win-rate percentage, with the center reference line visible, and that it doesn't look broken/overflowing at the fixed 110px height against real content.
4. **Milestones row.** If the real dev DB has any rows in `achievements_unlocked` (check via `sqlite3 chess.db "SELECT COUNT(*) FROM achievements_unlocked"` first), confirm the milestones row renders with real names/dates. If zero rows exist, confirm the page still renders cleanly with the row simply absent (no empty box, no error) — `_render_evolution_zone`'s `if milestones:` guard should handle this, but verify live rather than trusting the guard alone.
5. **Strengths/weaknesses split.** Confirm both columns show real findings pulled from the actual dev DB's `get_career_findings()` output, not empty — if `polarity == "strength"` never appears in the real data, note that as a real finding (not a bug) and report it back, since it would mean the "Strengths" column's empty-state caption is what most users will actually see today.
6. **Zero console errors** (browser devtools console), matching this project's standing verification bar for every dashboard change.

- [ ] **Step 3: Report findings**

Summarize what was confirmed vs. what needed a selector/approach correction, following this project's existing "trust but verify" convention — do not report this task as complete without having actually looked at the rendered page.
