"""Material-structure and bishop-ending queries -- one of eight topic
modules split out of the former dashboard/data/patterns.py.
"""
import collections

import pandas as pd

import analytics
import chess_utils
from connections import get_config
from confidence import default_thresholds

from .._shared import _classify_endgame_type, _classify_middlegame_trade_tier


def get_material_structure_table(sqlite_conn, structure_type="endgame", config_path=None, top_n=15):
    """structure_type: 'middlegame' or 'endgame'. Bulk GROUP BY for both
    outcome and ACPL, not one query pair per structure -- the original
    version (one analytics.structure_outcome_and_acpl call per candidate)
    measured ~10s for 15 structures; this does the same work in 2 queries
    total, same reasoning as the get_openings_table fix above."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    # Config-driven (not a hardcoded constant like this module's other
    # thresholds), but still doubles as confidence.py's "low" tier
    # threshold via default_thresholds() -- see confidence.py's module
    # docstring for the shared 3x/8x scheme. Not attached to the returned
    # frame as a column: patterns_view.py renders it via st.dataframe with
    # no column allowlist, so a new column would leak into the UI -- left
    # as a future badge hook, not wired in here.
    min_games = cfg["analytics"]["structure_min_games_per_group"]
    _thresholds = default_thresholds(min_games)  # noqa: F841 (future badge hook)
    sig_col = "middlegame_sig" if structure_type == "middlegame" else "endgame_sig"

    counts = sqlite_conn.execute(f"""
        SELECT {sig_col}, COUNT(*) AS n FROM structure_ctx
        WHERE {sig_col} IS NOT NULL GROUP BY {sig_col} HAVING COUNT(*) >= ?
        ORDER BY n DESC LIMIT ?
    """, (min_games, top_n)).fetchall()
    sigs = [sig for sig, _ in counts]
    if not sigs:
        return pd.DataFrame(columns=["material_sig", "n_games", "win_pct", "draw_pct", "loss_pct",
                                      "acpl", "n_analyzed"])
    placeholders = ",".join("?" * len(sigs))

    outcomes = sqlite_conn.execute(f"""
        SELECT sc.{sig_col}, g.outcome_for_player, COUNT(*) FROM structure_ctx sc
        JOIN games g ON g.id = sc.game_id
        WHERE sc.{sig_col} IN ({placeholders})
        GROUP BY sc.{sig_col}, g.outcome_for_player
    """, sigs).fetchall()
    outcome_lookup = {}
    for sig, outcome, n in outcomes:
        outcome_lookup.setdefault(sig, {})[outcome] = n

    if structure_type == "middlegame":
        ply_condition = "m.ply = ?"
        acpl_params = [cfg["analytics"]["middlegame_ply"]] + sigs
    else:
        ply_condition = "m.ply = sc.endgame_ply"
        acpl_params = sigs
    acpl_rows = sqlite_conn.execute(f"""
        SELECT sc.{sig_col}, COUNT(DISTINCT m.game_id), AVG(m.cpl)
        FROM moves m JOIN structure_ctx sc ON sc.game_id = m.game_id
        WHERE {ply_condition} AND m.is_player_move=1 AND m.cpl IS NOT NULL
          AND sc.{sig_col} IN ({placeholders})
        GROUP BY sc.{sig_col}
    """, acpl_params).fetchall()
    acpl_lookup = {sig: (n_analyzed, acpl) for sig, n_analyzed, acpl in acpl_rows}

    rows = []
    for sig, n in counts:
        o = outcome_lookup.get(sig, {})
        win, draw, loss = o.get("win", 0), o.get("draw", 0), o.get("loss", 0)
        n_analyzed, acpl = acpl_lookup.get(sig, (0, None))
        rows.append((sig, n, 100.0 * win / n, 100.0 * draw / n, 100.0 * loss / n, acpl, n_analyzed))
    return pd.DataFrame(rows, columns=["material_sig", "n_games", "win_pct", "draw_pct", "loss_pct",
                                        "acpl", "n_analyzed"])


def get_material_structure_bucket_table(sqlite_conn, structure_type="endgame", config_path=None):
    """Same win/draw/loss/ACPL shape as get_material_structure_table, but
    grouped by a coarse taxonomy bucket instead of the exact material_sig
    string -- Tier 1 of the Material Structure Explorer (roadmap §17 Q1 /
    §18): endgame reuses game_endings.py's Queen/Rook/Minor piece/King &
    pawn classifier (already shipped there, promoted to _shared.py so this
    page can reuse it instead of re-deriving it); middlegame uses a
    separate trade-tier classifier since piece TYPE isn't a useful split
    there (97.1% of real middlegame_sig rows still contain a queen).

    Unlike get_material_structure_table, this aggregates over ALL
    structure_ctx rows, not just the top_n most-frequent exact signatures --
    bucketing already collapses cardinality down to 4 rows, so there's no
    long-tail-readability reason to cap the input population the way the
    per-signature table does."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    sig_col = "middlegame_sig" if structure_type == "middlegame" else "endgame_sig"
    if structure_type == "middlegame":
        classify = _classify_middlegame_trade_tier
        bucket_order = ["No trades", "Light trades", "Moderate trades", "Heavy trades"]
        ply_condition = "m.ply = ?"
        acpl_params = [cfg["analytics"]["middlegame_ply"]]
    else:
        classify = _classify_endgame_type
        bucket_order = ["Queen", "Rook", "Minor piece", "King & pawn"]
        ply_condition = "m.ply = sc.endgame_ply"
        acpl_params = []

    outcome_rows = sqlite_conn.execute(f"""
        SELECT sc.{sig_col}, g.outcome_for_player, COUNT(*) AS n
        FROM structure_ctx sc
        JOIN games g ON g.id = sc.game_id
        WHERE sc.{sig_col} IS NOT NULL
        GROUP BY sc.{sig_col}, g.outcome_for_player
    """).fetchall()

    # SUM(cpl) + COUNT(DISTINCT game_id) + COUNT(*), same weighted-average
    # reasoning as get_endgame_type_performance -- AVG(AVG) across multiple
    # sigs mapping to the same bucket is wrong when sigs have different
    # move counts.
    acpl_rows = sqlite_conn.execute(f"""
        SELECT sc.{sig_col},
               COUNT(DISTINCT m.game_id)                                     AS n_analyzed,
               SUM(m.cpl)                                                    AS sum_cpl,
               COUNT(*)                                                      AS n_moves,
               SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END)  AS n_blunders
        FROM structure_ctx sc
        JOIN moves m ON m.game_id = sc.game_id
        WHERE sc.{sig_col} IS NOT NULL AND {ply_condition}
          AND m.is_player_move = 1 AND m.cpl IS NOT NULL
        GROUP BY sc.{sig_col}
    """, acpl_params).fetchall()

    tally = collections.defaultdict(lambda: {"win": 0, "draw": 0, "loss": 0, "n": 0})
    for sig, outcome, n in outcome_rows:
        bucket = classify(sig)
        if bucket:
            tally[bucket][outcome] = tally[bucket].get(outcome, 0) + n
            tally[bucket]["n"] += n

    acpl_acc = collections.defaultdict(lambda: [0, 0, 0.0, 0])  # n_analyzed, n_moves, sum_cpl, n_blunders
    for sig, n_analyzed, sum_cpl, n_moves, n_blunders in acpl_rows:
        bucket = classify(sig)
        if bucket and n_moves:
            acc = acpl_acc[bucket]
            acc[0] += n_analyzed or 0
            acc[1] += n_moves
            acc[2] += sum_cpl or 0.0
            acc[3] += n_blunders or 0

    rows = []
    for bucket in bucket_order:
        if bucket not in tally:
            continue
        counts = tally[bucket]
        total = counts["n"]
        n_analyzed, n_moves, sum_cpl, _n_blunders = acpl_acc.get(bucket, [0, 0, 0.0, 0])
        rows.append((bucket, total, 100.0 * counts.get("win", 0) / total,
                     100.0 * counts.get("draw", 0) / total, 100.0 * counts.get("loss", 0) / total,
                     sum_cpl / n_moves if n_moves else None, n_analyzed))
    return pd.DataFrame(rows, columns=["bucket", "n_games", "win_pct", "draw_pct", "loss_pct",
                                        "acpl", "n_analyzed"])


def get_bishop_color_ending_performance(duck_conn, sqlite_conn, config_path=None) -> pd.DataFrame:
    """Same-color vs. opposite-color bishop endings, by ACPL -- Material
    Structure Explorer Tier 2 (roadmap §17 Q1 / §22): the one axis
    material_sig can never express (piece COUNTS only, no square color),
    classified instead from the endgame-checkpoint FEN via
    chess_utils.classify_bishop_color_ending. Only meaningful when each
    side has exactly one bishop at that checkpoint (the classifier returns
    None otherwise) -- those games are excluded, same "no row" convention
    as every other structure_ctx consumer.

    Returns the raw per-bucket ("same"/"opposite") DataFrame -- columns
    `bucket`, `n_moves`, `acpl` -- with no confidence-tier filtering and no
    finding-dict wrapping. This is the shared computation extracted from
    insights.py's `_bishop_color_endings` finding (roadmap §22): that
    finding calls this function and then applies its own confidence/
    severity/headline logic on top, so this DataFrame's shape and values
    must stay exactly what that finding already relied on. ACPL is
    measured over player moves from endgame_ply ONWARD (the actual ending
    itself, not the whole game or just the transition move) -- see
    insights.py's docstring for why that definition was chosen over the
    alternatives that were empirically checked and rejected.

    Returns an empty DataFrame (not None) when there's no structure_ctx
    data, no bishop-ending games, or fewer than 2 buckets present --
    callers should treat `df.empty` as "not enough data", matching this
    module's other get_*_table functions' convention."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)

    ctx = duck_conn.execute("""
        SELECT m.game_id, m.fen_before
        FROM db.structure_ctx_cache sc
        JOIN db.moves m ON m.game_id = sc.game_id AND m.ply = sc.endgame_ply
        WHERE sc.endgame_ply IS NOT NULL AND m.fen_before IS NOT NULL
    """).fetchdf()
    empty = pd.DataFrame(columns=["bucket", "n_moves", "acpl"])
    if ctx.empty:
        return empty
    ctx["bucket"] = ctx.fen_before.apply(chess_utils.classify_bishop_color_ending)
    ctx = ctx.dropna(subset=["bucket"])
    if ctx.bucket.nunique() < 2:
        return empty

    moves = duck_conn.execute("""
        SELECT m.game_id, m.cpl
        FROM db.moves m JOIN db.structure_ctx_cache sc ON sc.game_id = m.game_id
        WHERE m.is_player_move = 1 AND m.cpl IS NOT NULL
          AND sc.endgame_ply IS NOT NULL AND m.ply >= sc.endgame_ply
    """).fetchdf()
    merged = moves.merge(ctx[["game_id", "bucket"]], on="game_id")
    if merged.empty:
        return empty
    return merged.groupby("bucket").agg(
        n_moves=("cpl", "size"), acpl=("cpl", "mean")).reset_index()
