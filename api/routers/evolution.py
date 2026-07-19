"""GET /api/evolution/* -- the opening-family repertoire evolution over
time page (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
from fastapi import APIRouter

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe

import data

router = APIRouter()

_evolution_counts_cache = TTLCache(60)     # unkeyed: get_family_period_counts is one bulk scan
_evolution_acpl_cache: dict[tuple, TTLCache] = {}   # lazily keyed on (family, color, time_control)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _evolution_counts_cache.clear()
    for _cache in _evolution_acpl_cache.values():
        _cache.clear()


def _get_evolution_counts():
    _, duck_conn = get_db_connections()
    return _evolution_counts_cache.get(lambda: data.get_family_period_counts(duck_conn))


@router.get("/api/evolution/summary")
def evolution_summary(color: str, time_control: str | None = None, grouping: str = "family"):
    counts = _get_evolution_counts()
    filtered = data.filter_counts(counts, color, time_control, grouping)
    shares, top = data.period_shares(filtered)
    ledger = data.classify_evolution(filtered)
    strips = data.ledger_period_shares(filtered, ledger["family"].tolist())
    return _json_safe({
        "total_games": int(filtered["n_games"].sum()) if not filtered.empty else 0,
        "n_periods": int(filtered["period"].nunique()) if not filtered.empty else 0,
        "composition": {"shares": shares.to_dict(orient="records"), "top": top},
        "ledger": ledger.to_dict(orient="records"),
        "strips": strips.to_dict(orient="records"),
    })


@router.get("/api/evolution/family-trend")
def evolution_family_trend(family: str, color: str, time_control: str | None = None):
    counts = _get_evolution_counts()
    filtered = data.filter_counts(counts, color, time_control, "family")
    return data.family_win_trend(filtered, family).to_dict(orient="records")


@router.get("/api/evolution/family-acpl")
def evolution_family_acpl(family: str, color: str, time_control: str | None = None):
    _, duck_conn = get_db_connections()
    key = (family, color, time_control)
    cache = _evolution_acpl_cache.setdefault(key, TTLCache(60))
    return cache.get(lambda: data.get_family_acpl_by_period(
        duck_conn, family, color, time_control).to_dict(orient="records"))
