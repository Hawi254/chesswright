# Streamlit UI Tests: Opt-In, Not Default — Design

Status: design approved by user, pending spec review
Branch: worktree-frontend-spike

## Context

This session set out to scope a full retirement of the Streamlit
dashboard (`chesswright.spec`, `dashboard/*_view.py`), on the premise
(from memory: `streamlit_frontend_dropped_2026-07-13`) that "React is now
the sole shipped frontend."

Investigation before any planning found that premise doesn't hold yet.
`frontend/`, `api/`, and `chesswright-react.spec` exist **only** on this
branch (`worktree-frontend-spike`) — not on `main`, not on
`feature/eval-dedup-cache`. Those branches are Streamlit-only; there is
no React code there at all. And on this branch, checked directly against
`frontend/src/App.tsx`'s `PAGE_COMPONENTS` map and `api/main.py`'s
router table (not the stale `docs/frontend_migration_status.md`, last
grounded 2026-07-14): 16 of 21 Streamlit pages are genuinely ported
(Overview, Game Explorer, Game Detail, Openings, Insights, Matchups,
Patterns, Analysis Jobs, Tactical Highlights, Game Endings, Repertoire
Evolution, Points, Batch Impact, Opening Tree, Opponent Prep, Ask). Five
are not: **Settings** (the API-key/chess.com/Pro-license/DB-import page —
`api/routers/settings.py` is a 27-line stub covering only
pro-status/key-status/nav-list), **Onboarding** (no React page exists at
all), **Training Queue**, **Drill Export**, **SRS Drills** (no router, no
page for any of these three). Settings and Onboarding are load-bearing —
without them a React-only build can't configure an API key, link
chess.com, or walk a new user through first run. `chesswright.spec`
(Streamlit) is also still the only artifact that has ever actually shipped
to a pilot tester (George, Windows) — the React side has never been
released.

**Conclusion: full decommission is premature and out of scope for this
session.** What's still worth doing now, independent of when the page gap
closes: `tests/ui/test_pages.py` (23 tests, `@pytest.mark.ui`) and
`dashboard/test_app.py` (9 tests, currently unmarked) are both Streamlit
`AppTest`-based page-render suites that run by default on every `pytest`
invocation on this branch, specifically because this branch — uniquely —
carries both frontends' test suites side by side. Measured directly
(not estimated): `pytest -m ui` (the 23 marked tests) took **143.7s**;
`pytest dashboard/test_app.py` (the 9 unmarked tests) took **125.7s**.
Combined, **~270s (4.5 min)** of every default `pytest` run is Streamlit
page-render testing, on a branch whose main current work is the React
side.

Separately confirmed: `.github/workflows/build.yml` never invokes
`pytest` at all (it only runs PyInstaller build/import/boot-smoke
checks) — so pytest is exclusively a manual/local/sub-agent-run thing on
this repo today, and this change has zero CI surface to update.

## Goal

Make the Streamlit UI test cost opt-in rather than default, with no code
deletion and no change to what CI does (nothing, today) — purely a
local/default developer-experience change. Keep it easy to still run the
full suite including Streamlit, since Streamlit remains the actual
shipped, pilot-tested artifact and this change removes the only place
that currently exercises it.

## Design

A custom `--run-streamlit-ui` pytest flag, via a new root-level
`conftest.py`. Root-level (not `tests/conftest.py`, which already exists)
because `tests/` and `dashboard/` are sibling directories — a hook needs
to sit above both to catch `dashboard/test_app.py`'s tests too, and
pytest's conftest.py plugin scoping follows directory ancestry of the
file being collected, not `testpaths`.

```python
# conftest.py (new, repo root)
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-streamlit-ui",
        action="store_true",
        default=False,
        help="Run Streamlit AppTest page-render tests (skipped by default).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-streamlit-ui"):
        return
    skip_streamlit_ui = pytest.mark.skip(
        reason="Streamlit UI test -- pass --run-streamlit-ui to run"
    )
    for item in items:
        if "ui" in item.keywords:
            item.add_marker(skip_streamlit_ui)
```

`dashboard/test_app.py`'s 9 test functions each get `@pytest.mark.ui`
added (the marker is already registered in `pyproject.toml`'s
`markers = [...]` list — "ui: Streamlit AppTest-based page render
tests" — this file was just never tagged with it). No other changes to
that file's logic.

Resulting behavior:
- `pytest` — fast default, ~270s faster, all 32 Streamlit tests reported
  as **skipped** (not silently absent — still visible in the summary
  line with a reason).
- `pytest --run-streamlit-ui` — everything, including both Streamlit
  files, unchanged from today's behavior.
- `pytest -m ui --run-streamlit-ui` — only the Streamlit tests.
- `pytest -m ui` alone (without the flag) still deselects to zero, same
  as it does today for `tests/ui/test_pages.py` — the skip hook and the
  `-m` filter compose, they don't conflict.

## Docs updates

- `README.md`'s "Testing" section (currently: "Run the full suite:
  `pytest`") gets corrected — `pytest` is the fast default now,
  `pytest --run-streamlit-ui` is the true full suite.
- `BRIEF.md` Conventions section gains a new numbered entry: this opt-in
  exists specifically because `worktree-frontend-spike` carries both
  frontends; since CI never runs pytest at all, `--run-streamlit-ui` is
  now the **only** thing that exercises Streamlit's test coverage, and
  must be run manually before tagging any release or pilot build for as
  long as `chesswright.spec` is still the real shipped artifact.

## Testing

- Run `pytest` (no flag): confirm the summary shows 32 skipped (23 from
  `test_pages.py` + 9 from `test_app.py`), all with the
  `--run-streamlit-ui` reason string, and confirm the run finishes ~270s
  faster than before this change.
- Run `pytest --run-streamlit-ui`: confirm all 32 execute, with the same
  single pre-existing `pro_gate` TESTING BYPASS failure as today (no new
  failures, nothing newly broken by adding markers/conftest).
- Run `pytest -m ui --run-streamlit-ui`: confirm it selects exactly the
  32 (both files), a spot-check that the marker was actually added
  correctly to all 9 `test_app.py` functions.
