"""Unit tests for dashboard/data/evolution.py — the core Repertoire
Evolution page's classification logic. Pure pandas over synthetic
long-form frames (year, quarter, family, n_games, n_wins) shaped like
data.filter_counts output, so no DB fixture is needed.
"""
import pandas as pd
import pytest

from data.evolution import (
    MAJOR_SHARE_PCT, MIN_FAMILY_GAMES,
    classify_evolution, family_win_trend, ledger_period_shares, period_shares,
)


def _rows(entries):
    """entries: (year, quarter, family, n_games, n_wins)."""
    df = pd.DataFrame(entries, columns=["year", "quarter", "family", "n_games", "n_wins"])
    df["n_draws"] = 0
    df["period"] = df["year"] * 4 + (df["quarter"] - 1)
    df["label"] = df["year"].astype(str) + " Q" + df["quarter"].astype(str)
    return df


def _flat_quarters(family, start_year, n_quarters, n_games, n_wins):
    """n_quarters consecutive (year, quarter) rows of constant volume."""
    out = []
    y, q = start_year, 1
    for _ in range(n_quarters):
        out.append((y, q, family, n_games, n_wins))
        q += 1
        if q == 5:
            q = 1
            y += 1
    return out


@pytest.mark.unit
class TestClassifyEvolution:
    def test_adopted(self):
        # Anchor spans the FULL range (2018 through 2022) so both the early
        # and late windows have a real denominator -- New Line is absent
        # early (0 games) and a clear share of a real late window.
        rows = (_flat_quarters("Anchor", 2018, 20, 100, 50)
                + _flat_quarters("New Line", 2022, 4, 60, 30))
        df = _rows(rows)
        out = classify_evolution(df)
        row = out[out.family == "New Line"].iloc[0]
        assert row.status == "adopted"
        assert row.share_early == 0.0
        assert row.share_late > MAJOR_SHARE_PCT

    def test_dropped(self):
        rows = (_flat_quarters("Anchor", 2018, 8, 100, 50)
                + _flat_quarters("Old Line", 2018, 4, 60, 20))
        df = _rows(rows)
        out = classify_evolution(df)
        row = out[out.family == "Old Line"].iloc[0]
        assert row.status == "dropped"
        assert row.share_late == 0.0
        assert pd.isna(row.win_late)

    def test_rising(self):
        rows = (_flat_quarters("Anchor", 2018, 20, 100, 50)
                + _flat_quarters("Grower", 2018, 4, 10, 5)
                + _flat_quarters("Grower", 2022, 4, 40, 20))
        df = _rows(rows)
        out = classify_evolution(df)
        row = out[out.family == "Grower"].iloc[0]
        assert row.status == "rising"

    def test_fading(self):
        rows = (_flat_quarters("Anchor", 2018, 20, 100, 50)
                + _flat_quarters("Shrinker", 2018, 4, 40, 20)
                + _flat_quarters("Shrinker", 2022, 4, 10, 3))
        df = _rows(rows)
        out = classify_evolution(df)
        row = out[out.family == "Shrinker"].iloc[0]
        assert row.status == "fading"

    def test_stable(self):
        rows = (_flat_quarters("Anchor", 2018, 8, 100, 50, )
                + _flat_quarters("Anchor", 2022, 4, 100, 55))
        df = _rows(rows)
        out = classify_evolution(df)
        row = out[out.family == "Anchor"].iloc[0]
        assert row.status == "stable"

    def test_min_games_floor_excludes_anecdote(self):
        rows = (_flat_quarters("Anchor", 2018, 8, 100, 50)
                + [(2022, 1, "OneOff", 3, 1)])
        df = _rows(rows)
        out = classify_evolution(df)
        assert "OneOff" not in set(out.family)
        assert MIN_FAMILY_GAMES > 3  # sanity: the fixture is genuinely below floor

    def test_never_reaches_minor_share_excluded(self):
        # A family present in both windows but always a tiny sliver of a
        # huge total shouldn't appear at all, even with many raw games.
        # Anchor spans the full range so the late window has a real
        # denominator too, not just Sliver's own games.
        rows = (_flat_quarters("Anchor", 2018, 20, 1000, 500)
                + _flat_quarters("Sliver", 2018, 4, 5, 2)
                + _flat_quarters("Sliver", 2022, 4, 5, 2))
        df = _rows(rows)
        out = classify_evolution(df)
        assert "Sliver" not in set(out.family)

    def test_short_history_shrinks_window(self):
        # Only 4 quarters total -- window should shrink to 2, not demand 4.
        rows = (_flat_quarters("Anchor", 2018, 4, 100, 50)
                + [(2018, 1, "Fresh", 0, 0), (2018, 2, "Fresh", 0, 0),
                   (2018, 3, "Fresh", 30, 15), (2018, 4, "Fresh", 30, 15)])
        df = _rows([r for r in rows if r[3] > 0 or r[2] != "Fresh"])
        out = classify_evolution(df)
        row = out[out.family == "Fresh"].iloc[0]
        assert row.status == "adopted"

    def test_status_order_and_ranking(self):
        rows = (_flat_quarters("Anchor", 2018, 20, 100, 50)       # stable, spans full range
                + _flat_quarters("New Line", 2022, 4, 60, 30)     # adopted
                + _flat_quarters("Old Line", 2018, 4, 60, 20))    # dropped, only in early
        df = _rows(rows)
        out = classify_evolution(df)
        statuses = list(out.status)
        assert "stable" in statuses
        assert statuses.index("adopted") < statuses.index("stable")
        assert statuses.index("dropped") < statuses.index("stable")

    def test_empty_input(self):
        out = classify_evolution(_rows([]))
        assert out.empty
        assert "status" in out.columns

    def test_win_pct_math(self):
        rows = (_flat_quarters("Anchor", 2018, 8, 100, 50)
                + _flat_quarters("Tracked", 2018, 4, 40, 10)   # 25% early
                + _flat_quarters("Tracked", 2022, 4, 40, 30))  # 75% late
        df = _rows(rows)
        out = classify_evolution(df)
        row = out[out.family == "Tracked"].iloc[0]
        assert row.win_early == pytest.approx(25.0)
        assert row.win_late == pytest.approx(75.0)


@pytest.mark.unit
class TestPeriodShares:
    def test_zero_fills_gaps_and_sums_to_100(self):
        rows = [(2018, 1, "A", 8, 4), (2018, 1, "B", 2, 1),
                (2018, 3, "A", 5, 2)]  # 2018 Q2 is a gap
        df = _rows(rows)
        shares, top = period_shares(df, top_n=4)
        assert set(shares.label) == {"2018 Q1", "2018 Q2", "2018 Q3"}
        gap = shares[shares.label == "2018 Q2"]
        assert (gap.n_games == 0).all()
        for label, grp in shares.groupby("label"):
            total = grp.share.sum()
            assert total == pytest.approx(0.0) or total == pytest.approx(100.0)

    def test_overflow_folds_into_other(self):
        rows = [(2018, 1, fam, 10, 5) for fam in ["A", "B", "C", "D", "E", "F"]]
        df = _rows(rows)
        shares, top = period_shares(df, top_n=4)
        assert len(top) == 4
        assert "Other" in set(shares.family)
        other_share = shares[shares.family == "Other"]["share"].iloc[0]
        assert other_share == pytest.approx(100.0 * 20 / 60)


@pytest.mark.unit
class TestFamilyWinTrend:
    def test_drops_thin_quarters(self):
        rows = [(2018, 1, "X", 10, 6), (2018, 2, "X", 2, 1)]
        df = _rows(rows)
        out = family_win_trend(df, "X", min_games_per_quarter=5)
        assert len(out) == 1
        assert out.iloc[0].label == "2018 Q1"

    def test_unknown_family_returns_empty(self):
        df = _rows([(2018, 1, "X", 10, 6)])
        out = family_win_trend(df, "Nonexistent")
        assert out.empty

    def test_uses_config_min_sample_size_when_not_passed(self, monkeypatch):
        from data import evolution as evolution_module
        monkeypatch.setattr(
            evolution_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 2}})
        df = _rows([(2018, 1, "X", 3, 2)])  # 3 games >= min_sample_size=2
        out = family_win_trend(df, "X")
        assert len(out) == 1
        assert out.iloc[0].label == "2018 Q1"

    def test_explicit_override_still_wins(self, monkeypatch):
        from data import evolution as evolution_module
        monkeypatch.setattr(
            evolution_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 100}})
        df = _rows([(2018, 1, "X", 3, 2)])
        out = family_win_trend(df, "X", min_games_per_quarter=2)  # explicit 2 overrides config's 100
        assert len(out) == 1
        assert out.iloc[0].label == "2018 Q1"


@pytest.mark.unit
class TestLedgerPeriodShares:
    def test_zero_fills_gaps_for_each_family(self):
        rows = [(2018, 1, "A", 8, 4), (2018, 3, "A", 5, 2)]  # 2018 Q2 is a gap
        df = _rows(rows)
        out = ledger_period_shares(df, ["A"])
        assert set(out.label) == {"2018 Q1", "2018 Q2", "2018 Q3"}
        gap = out[out.label == "2018 Q2"]
        assert (gap.n_games == 0).all()
        assert (gap.share == 0.0).all()

    def test_includes_families_outside_top_n(self):
        # period_shares only tracks a top_n cutoff (default 4); this
        # function must return shares for ANY family list passed in, even
        # a 5th one that period_shares would have folded into "Other".
        rows = [(2018, 1, fam, 10, 5) for fam in ["A", "B", "C", "D", "E"]]
        df = _rows(rows)
        out = ledger_period_shares(df, ["E"])
        assert set(out.family) == {"E"}
        assert out.iloc[0].share == pytest.approx(100.0 * 10 / 50)

    def test_share_denominator_is_the_full_period_total(self):
        # E's share denominator must be ALL families' games that quarter,
        # not just the games among the requested `families` list.
        rows = [(2018, 1, "A", 40, 20), (2018, 1, "E", 10, 5)]
        df = _rows(rows)
        out = ledger_period_shares(df, ["E"])
        assert out.iloc[0].share == pytest.approx(100.0 * 10 / 50)

    def test_empty_filtered_returns_empty_with_columns(self):
        out = ledger_period_shares(_rows([]), ["A"])
        assert out.empty
        assert list(out.columns) == ["period", "label", "family", "n_games", "share"]

    def test_empty_families_list_returns_empty(self):
        df = _rows([(2018, 1, "A", 10, 5)])
        out = ledger_period_shares(df, [])
        assert out.empty
