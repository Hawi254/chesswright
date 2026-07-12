"""FastAPI spike service -- 3 read-only endpoints wrapping existing,
Streamlit-free dashboard/data/overview.py functions. No new business
logic; no auth; no write paths. See
docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md.
"""
from fastapi import FastAPI

from api.db import get_db_connections

import data

app = FastAPI(title="Chesswright API (spike)")


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
