"""GET /api/pro-status, /api/settings/claude-key-status, /api/nav/pages --
Pro-license status, whether a Claude API key is configured, and the page
list the sidebar/nav renders (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import pathlib
import uuid

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import api_key_store
import claude_narrative
import config
import connections
import data
import db_import
import engine_status
import pro_gate
import sync_chesscom
import worker
from connections import resolve_db_path

router = APIRouter()

TEMPLATE_CONFIG_PATH = pathlib.Path(config.__file__).resolve().parent / "config.yaml"

try:
    from chesswright_pro import license as pro_license
except ImportError:
    pro_license = None


@router.get("/api/pro-status")
def pro_status():
    return {"active": pro_gate.is_pro_active()}


@router.get("/api/settings/claude-key-status")
def claude_key_status():
    return {"available": claude_narrative.api_key_available()}


@router.get("/api/nav/pages")
def nav_pages():
    return data.PAGE_CANDIDATES + data.SETTINGS_CANDIDATES


class AnalyticsSettingsRequest(BaseModel):
    utc_offset_hours: int = Field(ge=-12, le=14)
    min_sample_size: int = Field(ge=1, le=100)


def _analytics_payload():
    cfg = config.load_config()["analytics"]
    return {"utcOffsetHours": cfg["utc_offset_hours"], "minSampleSize": cfg["min_sample_size"]}


@router.get("/api/settings/analytics")
def analytics_settings():
    return _analytics_payload()


@router.post("/api/settings/analytics")
def save_analytics_settings(body: AnalyticsSettingsRequest):
    config.set_analytics_setting("utc_offset_hours", body.utc_offset_hours)
    config.set_analytics_setting("min_sample_size", body.min_sample_size)
    return _analytics_payload()


@router.post("/api/settings/analytics/reset")
def reset_analytics_settings():
    template_cfg = config.load_config(str(TEMPLATE_CONFIG_PATH))["analytics"]
    config.set_analytics_setting("utc_offset_hours", template_cfg["utc_offset_hours"])
    config.set_analytics_setting("min_sample_size", template_cfg["min_sample_size"])
    return _analytics_payload()


VARIANT_POLICIES = {"skip", "include"}
QUEUE_STRATEGIES = {"interleaved_by_year", "chronological", "reverse_chronological"}


class IngestionSettingsRequest(BaseModel):
    variant_policy: str
    queue_strategy: str


def _ingestion_payload():
    cfg = config.load_config()["ingestion"]
    return {"variantPolicy": cfg["variant_policy"], "queueStrategy": cfg["queue_strategy"]}


@router.get("/api/settings/ingestion")
def ingestion_settings():
    return _ingestion_payload()


@router.post("/api/settings/ingestion")
def save_ingestion_settings(body: IngestionSettingsRequest):
    if body.variant_policy not in VARIANT_POLICIES:
        raise HTTPException(status_code=400, detail=f"variant_policy must be one of {sorted(VARIANT_POLICIES)}")
    if body.queue_strategy not in QUEUE_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"queue_strategy must be one of {sorted(QUEUE_STRATEGIES)}")
    config.set_ingestion_setting("variant_policy", body.variant_policy)
    config.set_ingestion_setting("queue_strategy", body.queue_strategy)
    return _ingestion_payload()


@router.post("/api/settings/ingestion/reset")
def reset_ingestion_settings():
    template_cfg = config.load_config(str(TEMPLATE_CONFIG_PATH))["ingestion"]
    config.set_ingestion_setting("variant_policy", template_cfg["variant_policy"])
    config.set_ingestion_setting("queue_strategy", template_cfg["queue_strategy"])
    return _ingestion_payload()


class AdvancedSettingsRequest(BaseModel):
    pv_max_len: int = Field(ge=1, le=60)
    reuse_evals: bool
    consecutive_failure_limit: int = Field(ge=1, le=100)
    commit_every_n_moves: int = Field(ge=1, le=100)
    berserk_max_clock_fraction: float = Field(ge=0.0, le=1.0)
    backlog_quota: float = Field(ge=0.0, le=1.0)
    backlog_quota_window: int = Field(ge=1, le=1000)
    sync_request_timeout_seconds: int = Field(ge=1, le=300)
    sync_chesscom_request_timeout_seconds: int = Field(ge=1, le=300)


def _advanced_payload():
    cfg = config.load_config()
    return {
        "pvMaxLen": cfg["engine"]["pv_max_len"],
        "reuseEvals": cfg["engine"]["reuse_evals"],
        "consecutiveFailureLimit": cfg["worker"]["consecutive_failure_limit"],
        "commitEveryNMoves": cfg["worker"]["commit_every_n_moves"],
        "berserkMaxClockFraction": cfg["ingestion"]["berserk_max_clock_fraction"],
        "backlogQuota": cfg["ingestion"]["backlog_quota"],
        "backlogQuotaWindow": cfg["ingestion"]["backlog_quota_window"],
        "syncRequestTimeoutSeconds": cfg["sync"]["request_timeout_seconds"],
        "syncChesscomRequestTimeoutSeconds": cfg["sync_chesscom"]["request_timeout_seconds"],
    }


@router.get("/api/settings/advanced")
def advanced_settings():
    return _advanced_payload()


@router.post("/api/settings/advanced")
def save_advanced_settings(body: AdvancedSettingsRequest):
    config.set_engine_setting("pv_max_len", body.pv_max_len)
    config.set_engine_setting("reuse_evals", body.reuse_evals)
    config.set_worker_setting("consecutive_failure_limit", body.consecutive_failure_limit)
    config.set_worker_setting("commit_every_n_moves", body.commit_every_n_moves)
    config.set_ingestion_setting("berserk_max_clock_fraction", round(body.berserk_max_clock_fraction, 2))
    config.set_ingestion_setting("backlog_quota", round(body.backlog_quota, 2))
    config.set_ingestion_setting("backlog_quota_window", body.backlog_quota_window)
    config.set_sync_setting("request_timeout_seconds", body.sync_request_timeout_seconds)
    config.set_sync_chesscom_setting("request_timeout_seconds", body.sync_chesscom_request_timeout_seconds)
    return _advanced_payload()


class EnginePathRequest(BaseModel):
    path: str


class LiveEngineRequest(BaseModel):
    time_sec: float = Field(ge=0.1, le=10.0)
    depth: int = Field(ge=5, le=40)
    threads: int = Field(ge=1, le=8)
    hash_mb: int = Field(ge=16, le=1024)
    store_threshold: int = Field(ge=0, le=50)
    use_lichess_cloud_eval: bool


def _engine_payload():
    cfg = config.load_config()
    current_path = cfg["engine"].get("path")
    ie = cfg.get("interactive_engine", {})
    return {
        "path": current_path,
        "detectedPath": current_path or worker.find_engine_path(None),
        "live": {
            "timeSec": ie.get("time_sec", 0.5),
            "depth": ie.get("depth", 20),
            "threads": ie.get("threads", 1),
            "hashMb": ie.get("hash_mb", 32),
            "storeThreshold": ie.get("store_threshold", 20),
            "useLichessCloudEval": ie.get("use_lichess_cloud_eval", True),
        },
    }


@router.get("/api/settings/engine")
def engine_settings():
    return _engine_payload()


@router.post("/api/settings/engine/path")
def engine_set_path(body: EnginePathRequest):
    path = body.path.strip()
    try:
        worker.validate_engine_path(path)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    config.set_engine_path(path)
    engine_status.clear_engine_service_cache()
    return _engine_payload()


@router.post("/api/settings/engine/redetect")
def engine_redetect():
    found = worker.find_engine_path(None)
    if not found:
        raise HTTPException(status_code=404, detail="No Stockfish installation was found on this computer.")
    config.set_engine_path(found)
    engine_status.clear_engine_service_cache()
    return _engine_payload()


@router.post("/api/settings/engine/live")
def engine_save_live(body: LiveEngineRequest):
    config.save_interactive_engine({
        "time_sec": round(body.time_sec, 1),
        "depth": body.depth,
        "threads": body.threads,
        "hash_mb": body.hash_mb,
        "store_threshold": body.store_threshold,
        "use_lichess_cloud_eval": body.use_lichess_cloud_eval,
    })
    engine_status.clear_engine_service_cache()
    return _engine_payload()


@router.post("/api/settings/engine/reset")
def engine_reset():
    config.reset_engine_path()
    template_cfg = config.load_config(str(TEMPLATE_CONFIG_PATH))
    config.save_interactive_engine(template_cfg["interactive_engine"])
    engine_status.clear_engine_service_cache()
    return _engine_payload()


class SaveEngineProfileRequest(BaseModel):
    name: str


@router.get("/api/settings/engine-profiles")
def list_engine_profiles_route():
    return {"profiles": config.list_engine_profiles()}


@router.post("/api/settings/engine-profiles")
def save_engine_profile_route(body: SaveEngineProfileRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required.")
    config.save_engine_profile(name)
    return {"profiles": config.list_engine_profiles()}


@router.post("/api/settings/engine-profiles/{name}/apply")
def apply_engine_profile_route(name: str):
    try:
        config.apply_engine_profile(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No engine profile named '{name}'.")
    engine_status.clear_engine_service_cache()
    return _engine_payload()


@router.delete("/api/settings/engine-profiles/{name}")
def delete_engine_profile_route(name: str):
    config.delete_engine_profile(name)
    return {"profiles": config.list_engine_profiles()}


class ApiKeyRequest(BaseModel):
    key: str


@router.get("/api/settings/api-key")
def api_key_status():
    current = api_key_store.get_api_key()
    masked = None
    if current:
        masked = f"{current[:6]}...{current[-4:]}" if len(current) > 12 else "set"
    return {
        "configured": bool(current),
        "masked": masked,
        "secureBackend": api_key_store.using_secure_backend(),
    }


@router.post("/api/settings/api-key")
def save_api_key(body: ApiKeyRequest):
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key is required.")
    stored_securely = api_key_store.set_api_key(key)
    return {"ok": True, "securelyStored": stored_securely}


@router.delete("/api/settings/api-key")
def remove_api_key():
    api_key_store.clear_api_key()
    return {"ok": True}


_pending_imports: dict[str, str] = {}


class DbImportRequest(BaseModel):
    path: str


class DbImportConfirmRequest(BaseModel):
    pending_id: str
    username: str


class DbImportCancelRequest(BaseModel):
    pending_id: str


@router.post("/api/settings/db-import")
def db_import_start(body: DbImportRequest):
    dest_dir = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent
    try:
        imported_path = db_import.import_database(pathlib.Path(body.path.strip()), dest_dir)
    except db_import.DatabaseImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pending_id = uuid.uuid4().hex
    _pending_imports[pending_id] = str(imported_path)
    suggested = db_import.suggest_player_name(imported_path) or ""
    return {"pendingId": pending_id, "suggestedUsername": suggested}


@router.post("/api/settings/db-import/confirm")
def db_import_confirm(body: DbImportConfirmRequest):
    pending_path = _pending_imports.get(body.pending_id)
    if pending_path is None:
        raise HTTPException(status_code=404, detail="No pending import with that id.")
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    config.set_database_path(pending_path)
    config.set_player_name(username)
    connections.clear_cache()
    del _pending_imports[body.pending_id]
    return {"ok": True}


@router.post("/api/settings/db-import/cancel")
def db_import_cancel(body: DbImportCancelRequest):
    pending_path = _pending_imports.pop(body.pending_id, None)
    if pending_path is None:
        raise HTTPException(status_code=404, detail="No pending import with that id.")
    pathlib.Path(pending_path).unlink(missing_ok=True)
    return {"ok": True}


class ChesscomConnectRequest(BaseModel):
    username: str


@router.get("/api/settings/chesscom")
def chesscom_status():
    cfg = config.load_config()
    return {"username": cfg["player"].get("chesscom_username")}


@router.post("/api/settings/chesscom")
def chesscom_connect(body: ChesscomConnectRequest):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    config.set_chesscom_username(username)
    return {"username": username}


@router.delete("/api/settings/chesscom")
def chesscom_disconnect():
    config.set_chesscom_username(None)
    return {"ok": True}


@router.post("/api/settings/chesscom/sync")
def chesscom_sync():
    cfg = config.load_config()
    username = cfg["player"].get("chesscom_username")
    if not username:
        raise HTTPException(status_code=400, detail="Chess.com account is not connected.")
    db_path = resolve_db_path()
    try:
        sync_chesscom.run(
            db_path, username,
            cfg["ingestion"]["queue_strategy"], cfg["ingestion"]["variant_policy"],
            cfg["sync_chesscom"]["request_timeout_seconds"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True}


@router.get("/api/settings/pro-license")
def pro_license_status():
    if pro_license is None:
        return {"available": False}
    key = pro_license.get_license_key()
    info = pro_license.get_license_info() if key else None
    masked = None
    if key:
        masked = f"{key[:8]}...{key[-4:]}" if len(key) > 14 else "set"
    return {
        "available": True,
        "configured": bool(key),
        "masked": masked,
        "purchaseEmail": (info or {}).get("purchase_email"),
    }


class ProActivateRequest(BaseModel):
    key: str


@router.post("/api/settings/pro/activate")
def pro_activate(body: ProActivateRequest):
    if pro_license is None:
        raise HTTPException(status_code=404, detail="Chesswright Pro is not installed.")
    ok, msg = pro_license.activate(body.key.strip())
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@router.post("/api/settings/pro/deactivate")
def pro_deactivate():
    if pro_license is None:
        raise HTTPException(status_code=404, detail="Chesswright Pro is not installed.")
    pro_license.deactivate()
    return {"ok": True}
