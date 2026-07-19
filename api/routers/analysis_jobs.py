"""GET/POST /api/analysis-jobs/* -- the analysis batch runner's status
rail, start/stop/lock controls, settings, and maintenance actions (moved
from api/main.py, docs/superpowers/specs/2026-07-17-api-main-router-split-
design.md).
"""
import dataclasses

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import get_db_connections

import annotate
import backfill_batch_eval_cache
import config
import job_runner
import joblock
import worker
from connections import resolve_db_path

router = APIRouter()


def _analysis_job_status_payload():
    """Bundles everything the rail + telemetry column need on one 2s
    poll tick -- mirrors analysis_jobs_view.py's own _render_status(),
    which already computes all of this together for the same reason."""
    sqlite_conn, _ = get_db_connections()
    cfg = config.load_config()
    state = job_runner.get_state()
    running = job_runner.is_running()
    lock_info = joblock.status()

    pending, done, failed = sqlite_conn.execute("""
        SELECT
            SUM(CASE WHEN analysis_status IN ('pending','in_progress') THEN 1 ELSE 0 END),
            SUM(CASE WHEN analysis_status = 'done' THEN 1 ELSE 0 END),
            SUM(CASE WHEN analysis_status = 'failed' THEN 1 ELSE 0 END)
        FROM games
    """).fetchone()
    queue = {
        "waiting": pending or 0, "analyzed": done or 0, "failed": failed or 0,
        "awaitingAnnotation": annotate.count_games_awaiting_annotation(sqlite_conn),
    }

    telemetry = None
    run = None
    if running:
        run = {"gamesDone": state.get("games_done", 0)}
        active = sqlite_conn.execute(
            "SELECT id, started_at FROM analysis_runs WHERE ended_at IS NULL "
            "ORDER BY id DESC LIMIT 1").fetchone()
        if active is not None:
            run_id, started_at = active
            run["runId"], run["startedAt"] = run_id, started_at
            reused, engine_n, avg_ms = sqlite_conn.execute("""
                SELECT SUM(CASE WHEN eval_source='reuse' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN eval_source='engine' THEN 1 ELSE 0 END),
                       AVG(CASE WHEN eval_source='engine' THEN search_time_ms END)
                FROM moves WHERE analysis_run_id=? AND ply <= ?
            """, (run_id, worker.REUSE_EVAL_MAX_PLY)).fetchone()
            reused, engine_n = reused or 0, engine_n or 0
            eligible = reused + engine_n
            reuse_evals_on = cfg["engine"].get("reuse_evals", True)
            telemetry = {
                "reuseEvalsOn": reuse_evals_on,
                "cacheHitRate": (reused / eligible) if (reuse_evals_on and eligible) else None,
                "estTimeSavedSec": (reused * avg_ms / 1000) if (reused and avg_ms) else None,
                "eta": None,  # computed client-side from startedAt/gamesDone/queue.waiting
            }

    return {
        "status": state.get("status", "idle"),
        "runSeq": state.get("run_seq", 0),
        "completedRunId": state.get("completed_run_id"),
        "error": state.get("error"),
        "run": run,
        "queue": queue,
        "telemetry": telemetry,
        "lock": dataclasses.asdict(lock_info) if lock_info else None,
        "maintenance": {
            "annotationPending": queue["awaitingAnnotation"],
            "backfillPending": backfill_batch_eval_cache.count_pending_groups(sqlite_conn),
            "motifBackfillNeeded": annotate.motif_backfill_needed(sqlite_conn),
        },
    }


@router.get("/api/analysis-jobs/status")
def analysis_job_status():
    return _analysis_job_status_payload()


@router.post("/api/analysis-jobs/start")
def start_analysis_job():
    cfg = config.load_config()
    try:
        job_runner.start(
            resolve_db_path(), cfg["engine"]["depth"], cfg["engine"]["multipv"],
            cfg["engine"]["threads"], cfg["engine"]["hash_mb"], cfg["engine"]["pv_max_len"],
            cfg["engine"]["path"], cfg["worker"]["max_games"],
            worker.parse_duration(cfg["worker"]["max_duration"]),
            cfg["worker"]["consecutive_failure_limit"], cfg["worker"]["commit_every_n_moves"],
            backlog_quota=cfg["ingestion"]["backlog_quota"],
            backlog_quota_window=cfg["ingestion"]["backlog_quota_window"])
    except (RuntimeError, joblock.LockHeldError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


@router.post("/api/analysis-jobs/stop")
def stop_analysis_job():
    job_runner.stop()
    return {"ok": True}


@router.post("/api/analysis-jobs/lock/clear")
def clear_analysis_job_lock():
    joblock.force_release()
    return {"ok": True}


class SaveJobSettingsRequest(BaseModel):
    depth: int
    multipv: int
    max_games: int | None
    max_duration: str | None
    threads: int
    hash_mb: int


@router.get("/api/analysis-jobs/settings")
def get_analysis_job_settings():
    cfg = config.load_config()
    return {
        "depth": cfg["engine"]["depth"], "multipv": cfg["engine"]["multipv"],
        "threads": cfg["engine"]["threads"], "hashMb": cfg["engine"]["hash_mb"],
        "maxGames": cfg["worker"]["max_games"], "maxDuration": cfg["worker"]["max_duration"],
    }


@router.put("/api/analysis-jobs/settings")
def save_analysis_job_settings(body: SaveJobSettingsRequest):
    if job_runner.is_running():
        raise HTTPException(status_code=409, detail="Settings are read-only while a batch is running.")
    config.set_engine_setting("depth", body.depth)
    config.set_engine_setting("multipv", body.multipv)
    config.set_engine_setting("threads", body.threads)
    config.set_engine_setting("hash_mb", body.hash_mb)
    config.set_worker_setting("max_games", body.max_games)
    config.set_worker_setting("max_duration", body.max_duration)
    return {"ok": True}


@router.post("/api/analysis-jobs/annotate")
def run_annotation_pass():
    sqlite_conn, _ = get_db_connections()
    cfg = config.load_config()
    annotate.run(resolve_db_path(), cfg["annotation"]["mate_score_cap_cp"],
                  cfg["annotation"]["thresholds"], cfg["annotation"]["brilliant_material_threshold_cp"],
                  cfg["annotation"]["puzzle"], cfg["annotation"]["best_move_streak"], game_id=None)
    return {"ok": True}


@router.post("/api/analysis-jobs/backfill")
def run_cache_backfill():
    stats = backfill_batch_eval_cache.backfill(resolve_db_path())
    return {"insertedCount": stats.inserted, "groupsSeen": stats.groups_seen}
