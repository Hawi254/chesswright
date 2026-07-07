"""Batch Impact page queries -- what a specific analysis run changed.

Extracted from analysis_jobs_view.py's ephemeral "last batch" digest
(BRIEF §6u), which lived only in st.session_state (gone on the next batch
or app restart) and covered four numbers (ACPL, blunder rate, new
blunders/brilliancies, top motif). analysis_runs already has a permanent
row per worker session and moves.analysis_run_id already links every move
back to the run that analyzed it -- this module makes that history
queryable for ANY past run, not just the one that just finished, and
extends the before/after treatment to phase accuracy, endgame-type
accuracy, and tactical motif frequency.

Real fix made during the extraction, not just a copy: the original
`_get_batch_delta` split moves into "this run" (analysis_run_id = run_id)
vs "before" (analysis_run_id IS NULL OR != run_id) vs "after" (all
current moves, unconditionally). That's only correct when read
immediately after run_id finishes, before any later run can exist --
exactly how the ephemeral version was always used. Once a run picker lets
you open an OLD run after newer ones have since completed, `!= run_id`
would let a later run's moves leak into "before" (they're also != run_id),
and the unconditional "after" would silently include batches that hadn't
happened yet when run_id actually finished. Fixed here by using
analysis_runs.id's own AUTOINCREMENT ordering (strictly chronological --
only one run can ever be in progress at a time, per joblock.py):
  before = analysis_run_id IS NULL OR analysis_run_id <  run_id
  after  = analysis_run_id IS NULL OR analysis_run_id <= run_id
NULL (moves analyzed before analysis_runs existed at all, migration 0006)
precedes every run chronologically, so it belongs on both sides of every
split.

Scoped-but-skipped, per the same "don't force in metrics that aren't
affected" discipline as Repertoire Evolution's pairing section: the Where
Your Points Go ledger is NOT split here. It's genuinely sensitive to
newly-populated cpl/win_prob values, but the correct boundary is per-GAME
("was this game's curve complete as of run_id"), not per-move -- a game's
moves can span more than one run if analysis was paused and resumed, so
the right test is MAX(analysis_run_id) per completed game, not the
move-level split every function below uses. Real extra machinery for a
metric that already has its own dedicated page; revisit only if a real
batch-to-batch points question comes up.

Also NOT split here: endgame win/draw/loss rates (data.game_endings'
conversion percentages). structure_ctx's endgame_sig is derived purely
from move sequences/material, not engine output, so it (and the games
that reach it) doesn't shift because of a fresh analysis batch -- it
shifts when new games are SYNCED, which is Repertoire Evolution's
calendar-time axis, not this page's batch axis. Only the ACPL/blunder-rate
half of endgame-type performance (which needs cpl) is genuinely batch-
sensitive, so that's the only half reproduced here.
"""
import collections

import pandas as pd

import analytics
from _common import get_config

from .game_endings import _classify_endgame_type


def list_analysis_runs(sqlite_conn) -> pd.DataFrame:
    """Every analysis_runs row, most recent first -- the run-picker's
    source. One tiny table (one row per worker session), so no caching
    layer is needed at this level."""
    return pd.read_sql_query("""
        SELECT id, started_at, ended_at, engine_version, depth, multipv,
               threads, hash_mb, games_analyzed, plies_analyzed
        FROM analysis_runs
        ORDER BY id DESC
    """, sqlite_conn)


def get_batch_counter(sqlite_conn) -> dict:
    """Lifetime totals across every analysis_runs row -- how many batches
    have ever been run and how many games they've analyzed in total.
    Deliberately independent of any selected run_id: this is a running
    tally of total effort, not a before/after split, so it reads the same
    regardless of which run the page's picker has selected. No new
    tracking needed -- both numbers are already sitting in analysis_runs,
    same as everything else in this module."""
    total_batches, total_games = sqlite_conn.execute(
        "SELECT COUNT(*), SUM(games_analyzed) FROM analysis_runs"
    ).fetchone()
    return {
        "total_batches": total_batches or 0,
        "total_games_analyzed": total_games or 0,
    }


def get_batch_headline_delta(sqlite_conn, run_id: int) -> dict | None:
    """Same four headline numbers as the original ephemeral digest
    (games_analyzed, ACPL before/after, blunder rate before/after, new
    blunders/brilliancies this run, top missed motif this run), but with
    the before/after boundary fixed for a historical run_id (see module
    docstring). Returns None only if run_id no longer exists.
    before_acpl/before_blunder_rate are None when run_id is the earliest
    run (no prior history) -- same "first-ever batch" case the original
    handled."""
    run = sqlite_conn.execute(
        "SELECT games_analyzed, plies_analyzed, started_at, ended_at "
        "FROM analysis_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        return None
    games_analyzed, plies_analyzed, started_at, ended_at = run

    before = sqlite_conn.execute("""
        SELECT AVG(cpl),
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
        FROM moves
        WHERE is_player_move=1 AND cpl IS NOT NULL
          AND (analysis_run_id IS NULL OR analysis_run_id < ?)
    """, (run_id,)).fetchone()

    after = sqlite_conn.execute("""
        SELECT AVG(cpl),
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
        FROM moves
        WHERE is_player_move=1 AND cpl IS NOT NULL
          AND (analysis_run_id IS NULL OR analysis_run_id <= ?)
    """, (run_id,)).fetchone()

    this_run = sqlite_conn.execute("""
        SELECT
            COUNT(CASE WHEN classification='blunder' THEN 1 END),
            COUNT(CASE WHEN is_brilliant_candidate=1 THEN 1 END),
            COUNT(CASE WHEN cpl IS NOT NULL THEN 1 END)
        FROM moves
        WHERE is_player_move=1 AND analysis_run_id=?
    """, (run_id,)).fetchone()

    motif_row = sqlite_conn.execute("""
        SELECT motif, COUNT(*) AS n
        FROM moves
        WHERE is_player_move=1 AND classification='blunder'
          AND motif IS NOT NULL AND motif != ''
          AND analysis_run_id=?
        GROUP BY motif ORDER BY n DESC LIMIT 1
    """, (run_id,)).fetchone()

    return {
        "run_id":              run_id,
        "games_analyzed":      games_analyzed or 0,
        "plies_analyzed":      plies_analyzed or 0,
        "started_at":          started_at,
        "ended_at":            ended_at,
        "before_acpl":         before[0],
        "before_blunder_rate": before[1],
        "after_acpl":          after[0],
        "after_blunder_rate":  after[1],
        "new_blunders":        this_run[0] or 0,
        "new_brilliant":       this_run[1] or 0,
        "annotated_this_run":  this_run[2] or 0,
        "top_motif":           motif_row[0] if motif_row else None,
        "top_motif_count":     motif_row[1] if motif_row else 0,
    }


def get_phase_accuracy_batch_delta(sqlite_conn, run_id: int, config_path=None) -> pd.DataFrame:
    """Opening/middlegame/endgame ACPL and blunder rate, before this run
    vs. after it -- the same exclusive CASE-based phase partition
    patterns.get_phase_accuracy uses, computed in one pass (conditional
    SUMs for both sides of the boundary, not two separate scans)."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]
    rows = sqlite_conn.execute(f"""
        SELECT CASE WHEN m.ply < {middlegame_ply} THEN 'opening'
                    WHEN sc.endgame_ply IS NULL OR m.ply < sc.endgame_ply THEN 'middlegame'
                    ELSE 'endgame' END AS phase,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id < ?) THEN 1 ELSE 0 END) AS n_before,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id < ?) THEN m.cpl ELSE 0 END) AS sum_cpl_before,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id < ?) AND m.classification='blunder'
                        THEN 1 ELSE 0 END) AS blunders_before,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id <= ?) THEN 1 ELSE 0 END) AS n_after,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id <= ?) THEN m.cpl ELSE 0 END) AS sum_cpl_after,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id <= ?) AND m.classification='blunder'
                        THEN 1 ELSE 0 END) AS blunders_after
        FROM moves m JOIN games g ON g.id = m.game_id
        JOIN structure_ctx sc ON sc.game_id = g.id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
        GROUP BY phase
        ORDER BY CASE phase WHEN 'opening' THEN 0 WHEN 'middlegame' THEN 1 ELSE 2 END
    """, (run_id,) * 6).fetchall()

    out = []
    for phase, n_b, sum_b, bl_b, n_a, sum_a, bl_a in rows:
        out.append({
            "phase": phase,
            "n_moves_this_run": n_a - n_b,
            "before_acpl": (sum_b / n_b) if n_b else None,
            "after_acpl": (sum_a / n_a) if n_a else None,
            "before_blunder_rate": (100.0 * bl_b / n_b) if n_b else None,
            "after_blunder_rate": (100.0 * bl_a / n_a) if n_a else None,
        })
    return pd.DataFrame(out, columns=["phase", "n_moves_this_run", "before_acpl", "after_acpl",
                                       "before_blunder_rate", "after_blunder_rate"])


def get_endgame_type_batch_delta(sqlite_conn, run_id: int, config_path=None) -> pd.DataFrame:
    """ACPL/blunder-rate only (see module docstring for why win/draw/loss
    isn't reproduced here), before this run vs. after, broken down by the
    same broad endgame-material categories as
    game_endings.get_endgame_type_performance (reuses its classifier
    directly rather than re-deriving the Q/R/minor/K+P mapping)."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)

    rows = sqlite_conn.execute("""
        SELECT sc.endgame_sig,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id < ?) THEN 1 ELSE 0 END) AS n_before,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id < ?) THEN m.cpl ELSE 0 END) AS sum_cpl_before,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id < ?) AND m.classification='blunder'
                        THEN 1 ELSE 0 END) AS blunders_before,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id <= ?) THEN 1 ELSE 0 END) AS n_after,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id <= ?) THEN m.cpl ELSE 0 END) AS sum_cpl_after,
               SUM(CASE WHEN (m.analysis_run_id IS NULL OR m.analysis_run_id <= ?) AND m.classification='blunder'
                        THEN 1 ELSE 0 END) AS blunders_after
        FROM structure_ctx sc JOIN moves m ON m.game_id = sc.game_id
        WHERE sc.endgame_sig IS NOT NULL AND sc.endgame_ply IS NOT NULL
          AND m.ply >= sc.endgame_ply AND m.is_player_move=1 AND m.cpl IS NOT NULL
        GROUP BY sc.endgame_sig
    """, (run_id,) * 6).fetchall()

    # Weighted accumulation across every endgame_sig mapping to the same
    # broad type -- AVG(AVG) would be wrong when sigs have different move
    # counts (same reasoning as get_endgame_type_performance).
    acc = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0.0, 0])
    for sig, n_b, sum_b, bl_b, n_a, sum_a, bl_a in rows:
        etype = _classify_endgame_type(sig)
        if not etype:
            continue
        a = acc[etype]
        a[0] += n_b or 0; a[1] += sum_b or 0.0; a[2] += bl_b or 0
        a[3] += n_a or 0; a[4] += sum_a or 0.0; a[5] += bl_a or 0

    out = []
    for etype in ("Queen", "Rook", "Minor piece", "King & pawn"):
        if etype not in acc:
            continue
        n_b, sum_b, bl_b, n_a, sum_a, bl_a = acc[etype]
        out.append({
            "endgame_type": etype,
            "n_moves_this_run": n_a - n_b,
            "before_acpl": (sum_b / n_b) if n_b else None,
            "after_acpl": (sum_a / n_a) if n_a else None,
            "before_blunder_rate": (100.0 * bl_b / n_b) if n_b else None,
            "after_blunder_rate": (100.0 * bl_a / n_a) if n_a else None,
        })
    return pd.DataFrame(out, columns=["endgame_type", "n_moves_this_run", "before_acpl", "after_acpl",
                                       "before_blunder_rate", "after_blunder_rate"])


def get_motif_batch_delta(sqlite_conn, run_id: int) -> pd.DataFrame:
    """Frequency of every missed tactical motif, before this run vs.
    after -- the full breakdown the original digest's single "top motif
    this run" line only ever named once. Same idx_moves_motif partial
    index as tactical.get_motif_breakdown (sqlite_conn, not duck_conn --
    see the audit-dashboard-queries recipe)."""
    rows = sqlite_conn.execute("""
        SELECT motif,
               SUM(CASE WHEN (analysis_run_id IS NULL OR analysis_run_id < ?) THEN 1 ELSE 0 END) AS n_before,
               SUM(CASE WHEN (analysis_run_id IS NULL OR analysis_run_id <= ?) THEN 1 ELSE 0 END) AS n_after
        FROM moves
        WHERE is_player_move=1 AND classification IN ('mistake', 'blunder')
          AND motif IS NOT NULL AND motif != ''
        GROUP BY motif
    """, (run_id, run_id)).fetchall()
    df = pd.DataFrame(rows, columns=["motif", "n_before", "n_after"])
    if df.empty:
        return df.assign(n_this_run=pd.Series(dtype=int))
    df["n_this_run"] = df["n_after"] - df["n_before"]
    return df.sort_values(["n_this_run", "n_after"], ascending=False).reset_index(drop=True)


def get_new_blunders_this_run(sqlite_conn, run_id: int) -> pd.DataFrame:
    """One row per blunder found in this specific run -- drill-down source
    for the page's "new blunders this run" table. Point lookup on
    idx_moves_run (migration 0006), so sqlite_conn, not duck_conn."""
    return pd.read_sql_query("""
        SELECT game_id, ply, san, cpl, motif
        FROM moves
        WHERE is_player_move=1 AND classification='blunder' AND analysis_run_id=?
        ORDER BY cpl DESC
    """, sqlite_conn, params=[run_id])


def get_batch_trend(sqlite_conn) -> pd.DataFrame:
    """One row per analysis_runs row, chronological (ascending id) order,
    with TWO distinct ACPL/blunder-rate series -- deliberately not one,
    since they answer different questions and conflating them would make
    neither trustworthy:
      - cumulative_acpl/cumulative_blunder_rate: the running "as of this
        run" average across every move analyzed so far -- the same
        before/after boundary get_batch_headline_delta already computes for
        one run_id, extended to every checkpoint. This is the big-picture
        trend line.
      - this_run_acpl/this_run_blunder_rate: the average/blunder-rate of
        ONLY the moves analyzed in that specific run, independent of how
        much prior history dilutes it -- the fair per-batch comparison
        get_batch_record_flags needs. A cumulative delta mechanically
        shrinks as history grows, so it would be a bad "personal record"
        metric (later batches could almost never win); an isolated per-run
        average doesn't have that bias.

    Single GROUP BY over moves.analysis_run_id (idx_moves_run) rather than
    calling get_batch_headline_delta once per run_id -- one full scan
    instead of two range-filtered scans per run.

    Runs with zero annotated moves yet (annotated_this_run==0 in
    get_batch_headline_delta -- the real gap BRIEF §6u found live) get
    this_run_acpl/this_run_blunder_rate = None, and their cumulative values
    simply carry forward unchanged -- NOT zero, which would misread as
    "this batch was flawless."
    """
    runs = list_analysis_runs(sqlite_conn)[
        ["id", "started_at", "ended_at", "games_analyzed"]
    ].sort_values("id")  # list_analysis_runs is DESC; trend needs ASC

    per_run = pd.read_sql_query("""
        SELECT analysis_run_id AS run_id, COUNT(*) AS n,
               SUM(cpl) AS sum_cpl,
               SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) AS n_blunders
        FROM moves
        WHERE is_player_move=1 AND cpl IS NOT NULL
        GROUP BY analysis_run_id
    """, sqlite_conn)

    baseline = per_run[per_run["run_id"].isna()]
    cum_n = int(baseline["n"].iloc[0]) if not baseline.empty else 0
    cum_sum = float(baseline["sum_cpl"].iloc[0]) if not baseline.empty else 0.0
    cum_bl = int(baseline["n_blunders"].iloc[0]) if not baseline.empty else 0

    by_run = per_run.dropna(subset=["run_id"]).set_index("run_id")

    rows = []
    for r in runs.itertuples():
        if r.id in by_run.index:
            row = by_run.loc[r.id]
            n, bl = int(row["n"]), int(row["n_blunders"])
            s = float(row["sum_cpl"]) if row["sum_cpl"] is not None else 0.0
        else:
            n, s, bl = 0, 0.0, 0
        this_run_acpl = (s / n) if n else None
        this_run_blunder_rate = (100.0 * bl / n) if n else None
        cum_n += n
        cum_sum += s
        cum_bl += bl
        rows.append({
            "run_id": r.id,
            "ended_at": r.ended_at,
            "games_analyzed": r.games_analyzed,
            "this_run_acpl": this_run_acpl,
            "this_run_blunder_rate": this_run_blunder_rate,
            "cumulative_acpl": (cum_sum / cum_n) if cum_n else None,
            "cumulative_blunder_rate": (100.0 * cum_bl / cum_n) if cum_n else None,
        })
    return pd.DataFrame(rows, columns=[
        "run_id", "ended_at", "games_analyzed", "this_run_acpl",
        "this_run_blunder_rate", "cumulative_acpl", "cumulative_blunder_rate",
    ])


def get_batch_record_flags(sqlite_conn, run_id: int) -> dict:
    """Whether run_id set a personal record on its OWN isolated ACPL/blunder
    rate (this_run_acpl/this_run_blunder_rate from get_batch_trend, not the
    cumulative trend -- see that function's docstring for why) among every
    *other* annotated run at or before it. Lower is better for both, same
    convention as the headline's delta_color="inverse".

    Only compares against runs <= run_id (same boundary discipline as every
    before/after split in this module) -- reopening an old run must not get
    credit or blame for records a LATER run set. Requires at least one
    other annotated run to compare against, or every flag is False/None: a
    first annotated batch is trivially "best" against nothing, and flagging
    that as a record on every fresh install would be meaningless noise, not
    a real signal.
    """
    trend = get_batch_trend(sqlite_conn)
    eligible = trend[(trend["run_id"] <= run_id) & trend["this_run_acpl"].notna()]
    no_record = {
        "this_run_acpl": None, "this_run_blunder_rate": None,
        "is_best_acpl": False, "is_best_blunder_rate": False,
        "prior_best_acpl": None, "prior_best_blunder_rate": None,
        "prior_best_acpl_run_id": None,
    }
    if len(eligible) < 2 or run_id not in eligible["run_id"].values:
        return no_record

    this = eligible[eligible["run_id"] == run_id].iloc[0]
    prior = eligible[eligible["run_id"] != run_id]
    prior_best_acpl = prior["this_run_acpl"].min()
    prior_best_blunder_rate = prior["this_run_blunder_rate"].min()
    prior_best_acpl_run_id = int(prior.loc[prior["this_run_acpl"].idxmin(), "run_id"])

    return {
        "this_run_acpl": this["this_run_acpl"],
        "this_run_blunder_rate": this["this_run_blunder_rate"],
        "is_best_acpl": bool(this["this_run_acpl"] < prior_best_acpl),
        "is_best_blunder_rate": bool(this["this_run_blunder_rate"] < prior_best_blunder_rate),
        "prior_best_acpl": prior_best_acpl,
        "prior_best_blunder_rate": prior_best_blunder_rate,
        "prior_best_acpl_run_id": prior_best_acpl_run_id,
    }
