"""FastAPI spike service -- 3 read-only endpoints wrapping existing,
Streamlit-free dashboard/data/overview.py functions. No new business
logic; no auth; no write paths. See
docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import get_db_connections

import data

app = FastAPI(title="Chesswright API (spike)")

# The Vite dev server (5173) and this API (8123) are different origins,
# so the browser blocks the frontend's fetch() calls without this --
# found live while verifying Task 7 (requests failed with a CORS error,
# page stuck on "Loading..." forever). Wide open on purpose: spike-only,
# localhost-bound, no auth, read-only endpoints (see module docstring).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)


@app.get("/api/overview/headline-stats")
def headline_stats():
    sqlite_conn, duck_conn = get_db_connections()
    return data.get_headline_stats(duck_conn, sqlite_conn)


@app.get("/api/overview/rating-trajectory")
def rating_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_rating_trajectory(duck_conn)
    return df.to_dict(orient="records")


@app.get("/api/overview/rating-snapshot")
def rating_snapshot():
    _, duck_conn = get_db_connections()
    return data.get_rating_snapshot(duck_conn)
