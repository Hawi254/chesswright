"""GET/POST /api/training/* -- the merged Training page (Weaknesses/Build
Set/Review tabs, replacing the separate Drill Export/Training Queue/SRS
Drills pages), see
docs/superpowers/specs/2026-07-18-training-page-merge-design.md.

Weaknesses tab data comes from the existing /api/overview/career-findings
endpoint unchanged (no route here) -- this module only adds the one small
motif-backfill-needed check that endpoint doesn't carry, plus the new
Build Set and Review routes added in later tasks.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.db import get_db_connections

import analytics
import chess_display
import data
import pro_gate

router = APIRouter()


@router.get("/api/training/motif-backfill-needed")
def motif_backfill_needed():
    _, duck_conn = get_db_connections()
    return {"needed": data.motif_backfill_needed(duck_conn)}


_PREVIEW_COLUMNS = ["opening", "move_number", "phase", "motif", "cpl",
                     "wp_drop", "hole_score", "best_move_san"]


def _collect_drill_groups(sqlite_conn, duck_conn, include_motifs, include_moments,
                          include_holes, motif_filter, top_n):
    """Mirrors dashboard/drill_export_view.py's three-source collection
    (Missed Tactics / Decisive Moments / Repertoire Holes), called fresh
    per request -- unlike the Streamlit view's @st.cache_data wrappers,
    there's no per-rerun cost to avoid here."""
    groups: dict = {}

    if include_motifs:
        df = data.get_motif_drill_positions(sqlite_conn, motif=motif_filter, top_n=top_n)
        if not df.empty:
            groups["Missed Tactics"] = df

    if include_moments:
        df = data.get_decisive_moment_positions(duck_conn, top_n=top_n)
        if not df.empty:
            groups["Decisive Moments"] = df

    if include_holes:
        analytics.ensure_repertoire_holes_cache(sqlite_conn)
        df = data.get_repertoire_holes(sqlite_conn, min_appearances=5, top_n=top_n)
        if not df.empty:
            df = df.rename(columns={"most_played_san": "best_move_san"})
            groups["Repertoire Holes"] = df

    return groups


_SOURCE_KEYS = {
    "Missed Tactics": "missed_tactics",
    "Decisive Moments": "decisive_moments",
    "Repertoire Holes": "repertoire_holes",
}


@router.get("/api/training/build-set/preview")
def build_set_preview(include_motifs: bool = True, include_moments: bool = True,
                      include_holes: bool = True, motif_filter: str | None = None,
                      top_n: int = 20):
    sqlite_conn, duck_conn = get_db_connections()
    groups = _collect_drill_groups(sqlite_conn, duck_conn, include_motifs,
                                   include_moments, include_holes, motif_filter, top_n)
    sources = []
    total = 0
    for label, df in groups.items():
        cols = [c for c in _PREVIEW_COLUMNS if c in df.columns]
        positions = df[cols].to_dict(orient="records")
        sources.append({"key": _SOURCE_KEYS[label], "label": label,
                        "count": len(positions), "positions": positions})
        total += len(positions)
    return {"sources": sources, "total": total}


@router.get("/api/training/build-set/download-pgn")
def build_set_download_pgn(include_motifs: bool = True, include_moments: bool = True,
                           include_holes: bool = True, motif_filter: str | None = None,
                           top_n: int = 20):
    sqlite_conn, duck_conn = get_db_connections()
    groups = _collect_drill_groups(sqlite_conn, duck_conn, include_motifs,
                                   include_moments, include_holes, motif_filter, top_n)
    pgn_str = chess_display.drills_to_pgn_study(groups)
    return Response(
        content=pgn_str, media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="chesswright_drills.pgn"'},
    )


@router.get("/api/training/build-set/download-anki")
def build_set_download_anki(include_motifs: bool = True, include_moments: bool = True,
                            include_holes: bool = True, motif_filter: str | None = None,
                            top_n: int = 20):
    sqlite_conn, duck_conn = get_db_connections()
    groups = _collect_drill_groups(sqlite_conn, duck_conn, include_motifs,
                                   include_moments, include_holes, motif_filter, top_n)
    csv_str = chess_display.drills_to_anki_csv(groups)
    return Response(
        content=csv_str, media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="chesswright_drills.txt"'},
    )


class AddToReviewRequest(BaseModel):
    include_motifs: bool = True
    include_moments: bool = True
    include_holes: bool = True
    top_n: int = 20


@router.post("/api/training/build-set/add-to-review")
def build_set_add_to_review(body: AddToReviewRequest):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    sqlite_conn, duck_conn = get_db_connections()
    sources = set()
    if body.include_motifs:
        sources.add("motifs")
    if body.include_moments:
        sources.add("moments")
    if body.include_holes:
        sources.add("holes")
    if not sources:
        return {"added": 0}
    cards = data.build_drill_cards(sqlite_conn, duck_conn, sources=sources, top_n=body.top_n)
    added = data.add_cards(sqlite_conn, cards)
    return {"added": added}


@router.get("/api/training/review/stats")
def review_stats():
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    sqlite_conn, _ = get_db_connections()
    counts = data.get_card_counts(sqlite_conn)
    history = data.get_review_history(sqlite_conn)
    weekly = data.weekly_recall(history)
    curve = data.learning_curve(history)
    by_source = data.recall_by_source(history)
    if not weekly.empty:
        weekly = weekly.assign(week=weekly.week.dt.strftime("%Y-%m-%d"))
    return {
        "counts": counts,
        "weekly_recall": weekly.to_dict(orient="records"),
        "learning_curve": curve.to_dict(orient="records"),
        "recall_by_source": by_source.to_dict(orient="records"),
    }


@router.get("/api/training/review/due-cards")
def review_due_cards(limit: int = 50):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    sqlite_conn, _ = get_db_connections()
    cards = data.get_due_cards(sqlite_conn, limit=limit)
    return [card._asdict() for card in cards]


class RateCardRequest(BaseModel):
    card_id: int
    rating: int


@router.post("/api/training/review/rate")
def review_rate(body: RateCardRequest):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    sqlite_conn, _ = get_db_connections()
    interval_days = data.apply_rating(sqlite_conn, body.card_id, body.rating)
    return {"interval_days": interval_days}


class SkipCardRequest(BaseModel):
    card_id: int


@router.post("/api/training/review/skip")
def review_skip(body: SkipCardRequest):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    sqlite_conn, _ = get_db_connections()
    data.delete_card(sqlite_conn, body.card_id)
    return {}
