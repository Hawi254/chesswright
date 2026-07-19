"""Time-sliced repertoire evolution queries: the Opening Tree's "What
Changed" scan and the Explorer timeline headline -- one of three topic
modules split out of the former dashboard/data/openings.py.

The "What Changed" scan bakes in a total-games floor so the bulk query
returns tens of thousands of rows instead of ~900k. It must stay <=
2 x the What Changed tab's min-games-per-era slider FLOOR (3): a position
with fewer than 6 total games can never satisfy >=3 games on each side of
a split, so pruning at 6 can't hide a result any slider value can reach.
"""
import pandas as pd

from confidence import confidence_tier, default_thresholds

# This is an internal SQL pre-filter, not a per-finding display gate (the
# real confidence judgment happens downstream in
# compute_dominant_move_flips via min_games_each_era) -- kept as a
# derived thresholds dict for consistency/future use, same 3x/8x scheme
# as confidence.py's other call sites.
FLIP_SCAN_MIN_TOTAL_GAMES = 6
FLIP_SCAN_THRESHOLDS = default_thresholds(FLIP_SCAN_MIN_TOTAL_GAMES)

_EMPTY_FLIPS = pd.DataFrame(columns=[
    "ply", "zobrist_hash", "fen", "total_games",
    "before_san", "before_n", "before_total", "before_share", "before_win_pct", "before_cpl",
    "after_san", "after_n", "after_total", "after_share", "after_win_pct", "after_cpl",
])


def get_opening_moves_by_year(sqlite_conn, fen: str, player_color: str) -> pd.DataFrame:
    """Per-year breakdown of every move played from *fen* in games where
    the player had *player_color* ('w'/'b') -- the time-sliced companion to
    get_opening_moves_from_fen, for the Opening Tree's timeline panel.

    Returns one row per (san, year): n_games, n_wins/draws/losses (outcomes
    from the player's perspective), cpl_sum/cpl_n (player moves only --
    callers derive era-weighted avg CPL as cpl_sum/cpl_n, which stays exact
    under any regrouping of years; a pre-averaged avg_cpl column wouldn't).

    Deliberately live, not materialized: measured on the real 2.3M-move DB,
    the worst case (the starting position, ~16k games/color) runs in ~175ms
    via idx_moves_fen_before, a popular ply-6 position in ~20ms, and it only
    gets cheaper deeper. Takes sqlite_conn, not duck_conn -- same
    index-pushdown reasoning as get_opening_moves_from_fen above.
    """
    db_color = "white" if player_color == "w" else "black"
    return pd.read_sql_query("""
        SELECT
            m.san,
            g.year,
            MAX(m.is_player_move)                                                       AS is_player_move,
            COUNT(DISTINCT m.game_id)                                                   AS n_games,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'win'  THEN m.game_id END) AS n_wins,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'draw' THEN m.game_id END) AS n_draws,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'loss' THEN m.game_id END) AS n_losses,
            SUM(CASE WHEN m.is_player_move = 1 THEN m.cpl END)                          AS cpl_sum,
            COUNT(CASE WHEN m.is_player_move = 1 THEN m.cpl END)                        AS cpl_n
        FROM moves m
        JOIN games g ON g.id = m.game_id
        WHERE m.fen_before   = ?
          AND g.player_color = ?
        GROUP BY m.san, g.year
        ORDER BY g.year, n_games DESC
    """, sqlite_conn, params=[fen, db_color])


def get_player_move_year_stats(duck_conn, player_color: str, max_ply: int = 40) -> pd.DataFrame:
    """Per-(position, move, year) aggregates of the PLAYER's own opening
    moves for one color -- the bulk input to compute_dominant_move_flips.

    One grouped scan over analyzed moves (~2-3s on the real DB), keyed by
    color only: the What Changed tab's split-year/min-games sliders are
    applied in pandas on top of this frame, never baked into the scan, so
    slider moves are free (the audit-established rule: don't key a cache on
    args the expensive part ignores). max_ply=40 matches the Opening Tree
    cache's opening-phase boundary. Positions with fewer than
    FLIP_SCAN_MIN_TOTAL_GAMES total player-move games are pruned in SQL --
    see that constant's comment for why this can't hide a reachable result.
    """
    db_color = "white" if player_color == "w" else "black"
    return duck_conn.execute("""
        SELECT ply, zobrist_hash, san, year, n_games, n_wins, cpl_sum, cpl_n, fen_before
        FROM (
            SELECT
                m.ply, m.zobrist_hash, m.san, g.year,
                COUNT(DISTINCT m.game_id)                                                   AS n_games,
                COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'win' THEN m.game_id END)  AS n_wins,
                SUM(m.cpl)                                                                  AS cpl_sum,
                COUNT(m.cpl)                                                                AS cpl_n,
                MIN(m.fen_before)                                                           AS fen_before,
                SUM(COUNT(DISTINCT m.game_id))
                    OVER (PARTITION BY m.ply, m.zobrist_hash)                               AS position_total
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE m.zobrist_hash IS NOT NULL
              AND m.ply <= ?
              AND m.is_player_move = 1
              AND g.player_color = ?
            GROUP BY m.ply, m.zobrist_hash, m.san, g.year
        ) t
        WHERE position_total >= ?
        ORDER BY ply, zobrist_hash, year
    """, [max_ply, db_color, FLIP_SCAN_MIN_TOTAL_GAMES]).fetchdf()


def _era_dominants(df: pd.DataFrame, split_year: int) -> pd.DataFrame:
    """Collapse a per-(position, san, year) frame into one row per
    (position, era) holding that era's dominant (most-played) move plus the
    era's total game count. Ties break to SAN alphabetical order so results
    are deterministic run to run."""
    df = df.assign(era=df["year"].lt(split_year).map({True: "before", False: "after"}))
    era = (df.groupby(["ply", "zobrist_hash", "era", "san"], as_index=False)
             .agg(n_games=("n_games", "sum"), n_wins=("n_wins", "sum"),
                  cpl_sum=("cpl_sum", "sum"), cpl_n=("cpl_n", "sum"),
                  fen=("fen_before", "min")))
    totals = era.groupby(["ply", "zobrist_hash", "era"], as_index=False)["n_games"] \
                .sum().rename(columns={"n_games": "era_total"})
    # mergesort = stable, so the (n_games desc, san asc) order survives the
    # drop_duplicates pick of each group's first (= dominant) row.
    era = era.sort_values(["n_games", "san"], ascending=[False, True], kind="mergesort")
    dom = era.drop_duplicates(["ply", "zobrist_hash", "era"])
    return dom.merge(totals, on=["ply", "zobrist_hash", "era"])


def compute_dominant_move_flips(year_stats: pd.DataFrame, split_year: int,
                                min_games_each_era: int = 5) -> pd.DataFrame:
    """Positions whose dominant (most-played) player move DIFFERS between
    the games before *split_year* and the games from *split_year* on.

    Pure pandas over get_player_move_year_stats output -- unit-testable and
    cheap enough to re-run on every slider move. A position qualifies only
    when both eras have >= min_games_each_era player-move games, so a
    three-game "era" can't masquerade as a repertoire change.

    Returns _EMPTY_FLIPS's columns, sorted by total_games descending.
    share/win_pct are percentages of the era's games; *_cpl is the era's
    weighted avg CPL for the dominant move (NaN when unanalyzed).
    """
    if year_stats.empty:
        return _EMPTY_FLIPS.copy()

    dom = _era_dominants(year_stats, split_year)
    before = dom[dom["era"] == "before"].drop(columns="era")
    after = dom[dom["era"] == "after"].drop(columns="era")
    m = before.merge(after, on=["ply", "zobrist_hash"], suffixes=("_b", "_a"))
    # min_games_each_era is the hard gate (unchanged); doubles as
    # confidence.py's "low" tier threshold via default_thresholds().
    era_thresholds = default_thresholds(min_games_each_era)
    m = m[(m["era_total_b"].map(lambda n: confidence_tier(n, era_thresholds) != "insufficient"))
          & (m["era_total_a"].map(lambda n: confidence_tier(n, era_thresholds) != "insufficient"))
          & (m["san_b"] != m["san_a"])]
    if m.empty:
        return _EMPTY_FLIPS.copy()

    out = pd.DataFrame({
        "ply": m["ply"], "zobrist_hash": m["zobrist_hash"], "fen": m["fen_b"],
        "total_games": m["era_total_b"] + m["era_total_a"],
        "before_san": m["san_b"], "before_n": m["n_games_b"],
        "before_total": m["era_total_b"],
        "before_share": 100.0 * m["n_games_b"] / m["era_total_b"],
        "before_win_pct": 100.0 * m["n_wins_b"] / m["n_games_b"],
        "before_cpl": m["cpl_sum_b"] / m["cpl_n_b"].where(m["cpl_n_b"] > 0),
        "after_san": m["san_a"], "after_n": m["n_games_a"],
        "after_total": m["era_total_a"],
        "after_share": 100.0 * m["n_games_a"] / m["era_total_a"],
        "after_win_pct": 100.0 * m["n_wins_a"] / m["n_games_a"],
        "after_cpl": m["cpl_sum_a"] / m["cpl_n_a"].where(m["cpl_n_a"] > 0),
    })
    return out.sort_values("total_games", ascending=False).reset_index(drop=True)


def summarize_position_timeline(year_df: pd.DataFrame,
                                min_games_each_era: int = 5) -> dict | None:
    """Detect the single clearest move switch at ONE position, for the
    Explorer timeline panel's plain-language headline.

    Tries every candidate split year present in the data and keeps the one
    where the dominant move genuinely differs on both sides (each side
    >= min_games_each_era games), preferring the split with the largest
    smaller-era -- i.e. the most evenly evidenced switch, not the one that
    shaves off a single noisy year. Returns None when no split qualifies
    (the common case: a stable repertoire).

    year_df is get_opening_moves_by_year output (single position, one side
    to move throughout, so no is_player_move filtering is needed here).
    """
    if year_df.empty:
        return None
    df = year_df.assign(ply=0, zobrist_hash=0, fen_before="")
    years = sorted(df["year"].unique())
    best, best_evidence = None, -1
    for split in years[1:]:
        flips = compute_dominant_move_flips(df, int(split), min_games_each_era)
        if flips.empty:
            continue
        row = flips.iloc[0]
        evidence = min(int(row["before_total"]), int(row["after_total"]))
        if evidence > best_evidence:
            best_evidence = evidence
            best = {"split_year": int(split)}
            best.update({k: row[k] for k in (
                "before_san", "before_n", "before_total", "before_share",
                "before_win_pct", "before_cpl",
                "after_san", "after_n", "after_total", "after_share",
                "after_win_pct", "after_cpl")})
    return best
