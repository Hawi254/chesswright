"""FastAPI service wrapping existing, Streamlit-free dashboard/data/*.py
and dashboard/narrative.py functions via one APIRouter module per
page/feature area under api/routers/. No new business logic; no auth.
See docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md,
docs/superpowers/specs/2026-07-13-game-detail-completion-design.md,
docs/superpowers/specs/2026-07-13-game-detail-slice2-variation-mode-design.md,
and docs/superpowers/specs/2026-07-17-api-main-router-split-design.md.
"""
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.routers import (
    analysis_jobs, annotations, ask, batch_impact, board_chat, evolution,
    game_endings, games, insights, matchups, opening_tree, openings,
    opponent_prep, overview, patterns, points, settings, tactical_highlights,
    training, variations,
)
import api.shared_data as shared_data

app = FastAPI(title="Chesswright API")

# The Vite dev server (5173) and this API (8123) are different origins,
# so the browser blocks the frontend's fetch() calls without this --
# found live while verifying Task 7 (requests failed with a CORS error,
# page stuck on "Loading..." forever). Wide open on purpose: spike-only,
# localhost-bound, no auth, read-only endpoints (see module docstring).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
)

app.include_router(analysis_jobs.router)
app.include_router(opponent_prep.router)
app.include_router(board_chat.router)
app.include_router(variations.router)
app.include_router(annotations.router)
app.include_router(games.router)
app.include_router(openings.router)
app.include_router(opening_tree.router)
app.include_router(game_endings.router)
app.include_router(points.router)
app.include_router(batch_impact.router)
app.include_router(tactical_highlights.router)
app.include_router(evolution.router)
app.include_router(insights.router)
app.include_router(ask.router)
app.include_router(matchups.router)
app.include_router(settings.router)
app.include_router(patterns.router)
app.include_router(overview.router)
app.include_router(training.router)

# Where the built React frontend lives -- frontend/dist relative to this
# file's own directory's parent, both in a source checkout (frontend/dist
# is produced by `npm run build` in frontend/) and frozen (chesswright-
# react.spec bundles it to the same relative location under _internal/,
# since api/main.py itself is bundled at _internal/api/main.py). A plain
# module-level constant (not resolved inside a function) so tests can
# monkeypatch it directly -- see test_api_static.py.
FRONTEND_DIST_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "dist"


def reset_caches():
    """Test-only hook: api.main is a singleton module shared across every
    test in a pytest process, so a cache populated by one test would
    otherwise leak into the next one. Delegates to each router module's own
    reset_caches() -- main.py already imports every one of them to call
    include_router(), so it already "knows about" all of them; no separate
    cache registry is needed (see
    docs/superpowers/specs/2026-07-17-api-main-router-split-design.md)."""
    shared_data.reset_caches()
    overview.reset_caches()
    games.reset_caches()
    openings.reset_caches()
    game_endings.reset_caches()
    points.reset_caches()
    evolution.reset_caches()
    insights.reset_caches()
    ask.reset_caches()
    matchups.reset_caches()
    patterns.reset_caches()


@app.get("/assets/{asset_path:path}")
def frontend_asset(asset_path: str):
    """Serves frontend/dist/assets/* -- the built React app's JS/CSS
    bundle (Vite emits root-absolute /assets/... references in
    index.html). Path-traversal-safe: resolves the joined path and
    verifies it's still inside assets_dir before serving, rather than
    trusting the path parameter directly."""
    assets_dir = (FRONTEND_DIST_DIR / "assets").resolve()
    candidate = (assets_dir / asset_path).resolve()
    try:
        candidate.relative_to(assets_dir)
    except ValueError:
        raise HTTPException(status_code=404)
    if not candidate.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(candidate)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Catch-all SPA-fallback for the built React app's client-side
    routing (react-router-dom) -- must be the LAST route registered in
    this file so it never shadows the /api/* routes above. Returns a
    plain 404 (not a crash) when the frontend hasn't been built yet --
    api/main.py must still work standalone against a bare `npm run dev`
    Vite server on 5173, where this route is never hit at all.

    Being registered LAST only protects routes that already exist above
    it -- an /api/* path that ISN'T one of those (a typo, or an endpoint
    the frontend calls before it's implemented) would otherwise still
    match this catch-all and get back a 200 OK with index.html's HTML
    instead of a clean 404, which a fetch()-and-parse-as-JSON caller
    would see as a confusing JSON-parse error rather than an obvious
    missing-endpoint one (confirmed live 2026-07-13 against the real
    frozen build -- see the react-frontend-packaging plan's Task 9).
    Explicitly excluding the /api/ prefix here keeps that failure mode
    honest without having to enumerate every real route twice."""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    index_path = FRONTEND_DIST_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Frontend not built -- run `npm run build` in frontend/ first.",
        )
    return FileResponse(index_path)
