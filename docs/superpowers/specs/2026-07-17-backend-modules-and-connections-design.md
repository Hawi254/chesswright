# PyInstaller Backend-Modules Auto-Discovery + Connections Dedup — Design

Status: approved by user, pending self-review + doc-review gate
Date: 2026-07-17
Branch: `feature/eval-dedup-cache` (current branch)

## Context

Two separate, small refactor threads turned out to compose cleanly, so this
design covers both as one plan:

**1. `chesswright.spec`'s `BACKEND_MODULES` list has drifted from reality.**
It's a hand-maintained list of root-level `.py` files PyInstaller must bundle
as loose data (not traced by static `Analysis`, because they're only reached
at runtime through Streamlit's dynamic, file-path-based launch of
`dashboard/app.py` — see the comment block at the top of `chesswright.spec`).
Auditing the actual import graph reachable from `dashboard/` against the
current list found real drift: `achievements.py` (imported by
`dashboard/overview_view.py`) is **missing** — a frozen build would hit
`ModuleNotFoundError` on the Overview page — and `opening_explorer.py` is
listed but no longer reachable from `dashboard/` at all. No test covers this
file's correctness today, so nothing catches drift as it happens.

**2. `dashboard/db_connections.py` duplicates logic with
`worktree-frontend-spike`'s root-level `connections.py`.** The July 17
largest-file-modularization split moved `dashboard/_common.py`'s
Streamlit-free connection machinery into `dashboard/db_connections.py`. The
`worktree-frontend-spike` branch (a separate, ongoing React/FastAPI rewrite,
per `streamlit_frontend_dropped_2026-07-13`) independently did the same
extraction earlier (2026-07-13) into a root-level `connections.py` — but
went further: it also factored the migrate-then-open-connections logic
(including the disk-full check) out of the `@st.cache_resource`-decorated
`get_connections()` into a plain, Streamlit-free `DiskSpaceError` +
`open_connections()` pair, so `api/db.py` (FastAPI, no Streamlit dependency)
can share it.

This branch never caught up to that second half: `dashboard/_common.py`'s
`get_connections()` (lines 40-59) still inlines the migrate/disk-check logic
directly, calling `st.error()`/`st.stop()` from inside what should be
plain connection-opening code. That's duplicated *logic*, not just a
duplicated file — worth fixing on its own merits, independent of the other
branch.

**Why combine them:** relocating `dashboard/db_connections.py` to a
root-level `connections.py` (matching `worktree-frontend-spike`'s location,
closing that half of the divergence) only works cleanly if the new
root-level file gets bundled by `chesswright.spec` — which Goal 1's
glob-based `BACKEND_MODULES` does automatically, with no manual spec edit.
Doing Goal 1 first means Goal 2's relocation needs zero packaging changes.

**Explicit scope boundary (confirmed with user):** this design touches only
`feature/eval-dedup-cache`. It does **not** edit `worktree-frontend-spike`'s
`connections.py` or `api/db.py` — no cross-branch edits. The new function
extracted here is deliberately named differently from that branch's
`open_connections()` (see Architecture) specifically so a future merge
surfaces as "two related but differently-shaped functions to reconcile,"
not a silent same-name/different-behavior collision.

## Goals

1. `chesswright.spec`'s `BACKEND_MODULES` list is computed, not
   hand-maintained — any new root-level backend `.py` file is bundled
   automatically, with no spec edit, and the current `achievements.py` gap
   is fixed as a side effect.
2. `dashboard/db_connections.py` relocates to root-level `connections.py`
   (matching `worktree-frontend-spike`'s naming/location for the parts that
   overlap), and the migrate/disk-check logic duplicated between this
   branch and that one is extracted out of `dashboard/_common.py` into the
   relocated file, matching that branch's separation of concerns
   (Streamlit-free logic raises a plain exception; the Streamlit layer
   decides how to render it).
3. Zero behavior change beyond the disk-full error path moving from
   inline-in-`get_connections()` to a catch of a raised `DiskSpaceError` —
   same user-facing message, same `st.error()`+`st.stop()` outcome.

## Non-goals (explicit)

- **No edits to `worktree-frontend-spike`** (`connections.py`, `api/db.py`,
  or anything else on that branch/worktree) — confirmed with user.
- **No `open_connections()`-style module-level singleton + `clear_cache()`**
  on this branch. That machinery exists on `worktree-frontend-spike`
  because `api/db.py` has no Streamlit `@st.cache_resource` to lean on;
  this branch's only caller (`dashboard/_common.py::get_connections()`)
  already gets a singleton + `.clear()` from `@st.cache_resource` itself.
  Building an unused second caching layer here would be speculative.
- **No `chesswright-pro.spec` change** — separate private repo, not touched
  from here. Worth flagging to whoever maintains it that the same
  hand-maintained-list drift risk likely applies there; not a task in this
  plan.
- **No PyInstaller build/verification** as part of this pass — same
  precedent as the prior modularization plan (inspection-only, unless a
  real build is requested separately).
- **No other behavior changes** folded in, even ones noticed while moving
  code.

## Architecture

### Goal 1 — `chesswright.spec`

Replace the hardcoded list with a computed one:

```python
BACKEND_DATA_EXCLUDE = {"desktop_app.py", "desktop_preflight.py", "desktop_server.py"}
BACKEND_MODULES = sorted(
    p.name for p in ROOT.glob("*.py") if p.name not in BACKEND_DATA_EXCLUDE
)
```

The exclude set is the entry file plus its two direct siblings — the only
root-level `.py` files PyInstaller's static `Analysis` already traces
correctly (normal `import` from `desktop_app.py`, not Streamlit's dynamic
path-based load). Everything else at repo root is backend/CLI code by
existing convention (dev/CI scripts live in `scripts/`, tests live in
`tests/`), so it's swept in unconditionally. The
`datas += [(str(ROOT / name), ".") for name in BACKEND_MODULES]` line stays
unchanged — same consumption, computed source.

Land this one first — Goal 2's new root-level `connections.py` then needs
no manual addition to get bundled.

### Goal 2 — `connections.py` + `dashboard/_common.py`

`dashboard/db_connections.py` → new root-level `connections.py`, same
content, plus two new pieces extracted from `dashboard/_common.py`:

```python
class DiskSpaceError(RuntimeError):
    """Raised by open_fresh_connections() when migrate.migrate() fails AND
    the volume holding the database has < 0.5 GB free -- almost certainly
    the actual cause. dashboard/_common.py's get_connections() catches
    this specifically to show a Streamlit-native error + st.stop()."""


def open_fresh_connections(db_path):
    """Migrates db_path then opens one SQLite + one DuckDB connection
    against it. Streamlit-free: raises DiskSpaceError (a plain exception)
    on a migration failure caused by a full disk, rather than calling into
    streamlit directly -- callers render that however fits their context.
    No caching/singleton behavior here (unlike worktree-frontend-spike's
    differently-named, differently-shaped open_connections(), which is a
    module-level singleton for a Streamlit-free FastAPI caller) --
    dashboard/_common.py's get_connections() below is already a singleton
    via @st.cache_resource, so a second caching layer here would be
    speculative."""
    try:
        migrate.migrate(db_path)
    except Exception as exc:
        free_gb = None
        try:
            db_dir = pathlib.Path(db_path).parent
            free_gb = shutil.disk_usage(db_dir).free / 1e9
        except Exception:
            pass
        if free_gb is not None and free_gb < 0.5:
            raise DiskSpaceError(
                f"**Database error — disk is almost full** "
                f"({free_gb:.1f} GB free on the volume holding your database). "
                "Free up at least 1 GB and restart Chesswright.\n\n"
                f"Database path: `{db_path}`"
            ) from exc
        raise
    return get_sqlite_connection(db_path), get_duckdb_connection(db_path)
```

`import shutil` is added to `connections.py` (not previously needed there).

`dashboard/_common.py::get_connections()` shrinks to a thin wrapper:

```python
@st.cache_resource(show_spinner="Opening your game database…")
def get_connections():
    """... existing docstring, unchanged reasoning ..."""
    db_path = resolve_db_path()
    try:
        return open_fresh_connections(db_path)
    except DiskSpaceError as e:
        st.error(str(e))
        st.stop()
```

Same outcome on every path: disk-full → same message, same
`st.error()`+`st.stop()`; any other migration failure → re-raised
unchanged (the inner `raise` with no disk-space match). `import migrate` is
dropped from `_common.py` (no longer called directly there); the module's
`from db_connections import (...)` block becomes `from connections import
(...)`, adding `DiskSpaceError, open_fresh_connections` to the imported
names.

**Other call sites to update** (confirmed complete via grep — only two
files reference `db_connections` on this branch):
- `dashboard/_common.py` — import + `get_connections()` body, as above.
- `tests/unit/test_duckdb_extension_loading.py` — `import db_connections` →
  `import connections`; its two `monkeypatch.setattr(db_connections,
  "_bundled_sqlite_extension_path", ...)` calls become
  `monkeypatch.setattr(connections, ...)`.

`dashboard/db_connections.py` is deleted. Its content no longer needs
`dashboard`'s wholesale `datas` entry to be bundled — Goal 1's glob covers
it as a plain root-level file, same as `config.py`/`db.py`/`migrate.py`
already are.

## Testing

- Full existing suite (`python3 -m pytest`) after each goal, before moving
  to the next — same discipline as the prior modularization plan.
- `tests/unit/test_duckdb_extension_loading.py` and
  `tests/unit/test_duck_snapshot.py` get an explicit individual check (not
  just relying on the full-suite run) since they're the tests closest to
  the moved code.
- No new tests for Goal 1 — correctness no longer depends on a
  human-maintained list, so there's nothing meaningful to regression-test
  beyond "the glob excludes exactly the right 3 files," which is visible
  by inspection (and by the existing suite still passing, since nothing
  currently depends on `BACKEND_MODULES`'s exact contents).
- No new tests for Goal 2 beyond the updated monkeypatch targets above —
  confirmed by grep that no existing test exercises `get_connections()`'s
  disk-full path today, and this refactor doesn't change that path's
  behavior (same message, same `st.error()`+`st.stop()`), so there's
  nothing new to cover and nothing existing to protect against
  regression.

## Sequencing

Two independent commits, in this order:
1. `chesswright.spec`'s `BACKEND_MODULES` → glob-based. Run full suite.
2. `dashboard/db_connections.py` → `connections.py` relocation +
   `DiskSpaceError`/`open_fresh_connections()` extraction +
   `dashboard/_common.py` update + test-file import updates. Run full
   suite.
