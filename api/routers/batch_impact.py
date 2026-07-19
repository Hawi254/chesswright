"""GET /api/batch-impact/summary -- before/after impact of one analysis
batch run, or a range of runs (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md; router
added per that plan's Deviation #1 -- this page shipped 2026-07-16 and the
spec's own file-layout list predates it). No cache -- reads directly on
every call, same as the original.
"""
from fastapi import APIRouter, HTTPException

from api.db import get_db_connections
from api.serialization import _json_safe

import data

router = APIRouter()


def _run_label(row) -> str:
    when = row.ended_at or row.started_at or "in progress"
    return f"Run #{row.id} — {when} — {row.games_analyzed or 0} games"


def _records_in_range(trend_df, run_a, run_b):
    """Linear scan over the full get_batch_trend() history (already fetched
    once for the trend chart, so this reuses it rather than issuing N
    redundant range-filtered queries) tracking a running-best ACPL/blunder
    rate ACROSS THE WHOLE HISTORY (not reset at the range boundary), and
    flagging a run as a record only when it's in (run_a, run_b] AND it beat
    a real prior best. Mirrors get_batch_record_flags's own "a first
    annotated batch is trivially 'best' against nothing, and flagging that
    on every fresh install would be meaningless noise" principle: best_acpl/
    best_blunder_rate start as None, and a None best never triggers a
    record -- so the very first annotated run in an account's entire
    history is never flagged even when it falls inside a Start-anchored
    range."""
    records = []
    best_acpl = None
    best_blunder_rate = None
    for row in trend_df.itertuples():
        in_range = (run_a is None or row.run_id > run_a) and row.run_id <= run_b
        if row.this_run_acpl is not None:
            if best_acpl is not None and in_range and row.this_run_acpl < best_acpl:
                records.append({"runId": int(row.run_id), "metric": "acpl",
                                 "value": row.this_run_acpl, "priorBest": best_acpl})
            if best_acpl is None or row.this_run_acpl < best_acpl:
                best_acpl = row.this_run_acpl
        if row.this_run_blunder_rate is not None:
            if best_blunder_rate is not None and in_range and row.this_run_blunder_rate < best_blunder_rate:
                records.append({"runId": int(row.run_id), "metric": "blunder_rate",
                                 "value": row.this_run_blunder_rate, "priorBest": best_blunder_rate})
            if best_blunder_rate is None or row.this_run_blunder_rate < best_blunder_rate:
                best_blunder_rate = row.this_run_blunder_rate
    return records


def _empty_batch_impact_response():
    return {
        "runs": [], "counter": {"totalBatches": 0, "totalGamesAnalyzed": 0},
        "range": {"runA": None, "runB": None}, "pendingAnnotation": False,
        "headline": None, "records": [], "trend": [], "phase": [], "endgame": [],
        "motifs": [], "newBlunders": [],
    }


@router.get("/api/batch-impact/summary")
def batch_impact_summary(run_a: str | None = None, run_b: int | None = None):
    sqlite_conn, _ = get_db_connections()
    runs_df = data.list_analysis_runs(sqlite_conn)  # DESC, most-recent-first
    if runs_df.empty:
        return _json_safe(_empty_batch_impact_response())

    ids_desc = runs_df["id"].tolist()
    resolved_run_b = run_b if run_b is not None else ids_desc[0]
    if resolved_run_b not in ids_desc:
        raise HTTPException(status_code=404, detail=f"analysis run {resolved_run_b} not found")

    if run_a is None:
        # Smart default: the run immediately before resolved_run_b -- this
        # is what makes BatchFinishedCard's `?runB=<id>` link (no runA at
        # all) resolve to "previous run, or Start" with no special case.
        idx = ids_desc.index(resolved_run_b)
        resolved_run_a = ids_desc[idx + 1] if idx + 1 < len(ids_desc) else None
    elif run_a == "start":
        resolved_run_a = None
    else:
        resolved_run_a = int(run_a)

    if resolved_run_a is not None and resolved_run_a > resolved_run_b:
        resolved_run_a, resolved_run_b = resolved_run_b, resolved_run_a

    delta = data.get_batch_range_delta(sqlite_conn, resolved_run_a, resolved_run_b)
    if delta is None:
        raise HTTPException(status_code=404, detail=f"analysis run {resolved_run_b} not found")
    pending = delta["annotated_run_b"] == 0

    trend_df = data.get_batch_trend(sqlite_conn)
    counter = data.get_batch_counter(sqlite_conn)
    records = _records_in_range(trend_df, resolved_run_a, resolved_run_b)
    label_by_id = {int(r.id): _run_label(r) for r in runs_df.itertuples()}
    for rec in records:
        rec["label"] = label_by_id.get(rec["runId"], f"Run #{rec['runId']}")

    phase_df = data.get_phase_accuracy_batch_range_delta(sqlite_conn, resolved_run_a, resolved_run_b)
    endgame_df = data.get_endgame_type_batch_range_delta(sqlite_conn, resolved_run_a, resolved_run_b)
    motif_df = data.get_motif_batch_range_delta(sqlite_conn, resolved_run_a, resolved_run_b)
    blunders_df = data.get_new_blunders_in_range(sqlite_conn, resolved_run_a, resolved_run_b)

    return _json_safe({
        "runs": [
            {"id": int(r.id), "label": _run_label(r), "gamesAnalyzed": r.games_analyzed, "endedAt": r.ended_at}
            for r in runs_df.itertuples()
        ],
        "counter": {"totalBatches": counter["total_batches"], "totalGamesAnalyzed": counter["total_games_analyzed"]},
        "range": {"runA": resolved_run_a, "runB": resolved_run_b},
        "pendingAnnotation": pending,
        "headline": None if pending else {
            "gamesInRange": delta["games_in_range"],
            "acplBefore": delta["before_acpl"], "acplAfter": delta["after_acpl"],
            "blunderRateBefore": delta["before_blunder_rate"], "blunderRateAfter": delta["after_blunder_rate"],
            "newBlunders": delta["new_blunders"], "newBrilliant": delta["new_brilliant"],
            "topMotif": delta["top_motif"], "topMotifCount": delta["top_motif_count"],
        },
        "records": records,
        "trend": [
            {"runId": int(r.run_id), "endedAt": r.ended_at, "gamesAnalyzed": r.games_analyzed,
             "cumulativeAcpl": r.cumulative_acpl, "cumulativeBlunderRate": r.cumulative_blunder_rate}
            for r in trend_df.itertuples()
        ],
        "phase": [
            {"phase": r.phase, "acplBefore": r.before_acpl, "acplAfter": r.after_acpl,
             "blunderRateBefore": r.before_blunder_rate, "blunderRateAfter": r.after_blunder_rate,
             "nMovesInRange": r.n_moves_in_range}
            for r in phase_df.itertuples()
        ],
        "endgame": [
            {"endgameType": r.endgame_type, "acplBefore": r.before_acpl, "acplAfter": r.after_acpl,
             "blunderRateBefore": r.before_blunder_rate, "blunderRateAfter": r.after_blunder_rate,
             "nMovesInRange": r.n_moves_in_range}
            for r in endgame_df.itertuples()
        ],
        "motifs": motif_df.head(10)[["motif", "n_before", "n_after", "n_in_range"]].rename(
            columns={"n_before": "before", "n_after": "after", "n_in_range": "delta"}
        ).to_dict(orient="records"),
        "newBlunders": blunders_df.rename(columns={"game_id": "gameId"}).to_dict(orient="records"),
    })
