"""Unit tests for annotate.py — CPL computation, win probability, classification."""
import math
import pytest

from annotate import cp_equivalent, mover_pov_after, win_prob, classify


@pytest.mark.unit
class TestCpEquivalent:
    def test_normal_cp(self):
        assert cp_equivalent(200, None, 1500) == 200

    def test_positive_mate_returns_cap(self):
        assert cp_equivalent(None, 3, 1500) == 1500

    def test_negative_mate_returns_negative_cap(self):
        assert cp_equivalent(None, -2, 1500) == -1500

    def test_zero_cp(self):
        assert cp_equivalent(0, None, 1500) == 0


@pytest.mark.unit
class TestMoverPovAfter:
    def test_flips_cp_sign(self):
        after_cp, after_mate = mover_pov_after(100, None)
        assert after_cp == -100
        assert after_mate is None

    def test_flips_mate_sign(self):
        after_cp, after_mate = mover_pov_after(None, 3)
        assert after_cp is None
        assert after_mate == -3

    def test_none_inputs(self):
        after_cp, after_mate = mover_pov_after(None, None)
        assert after_cp is None
        assert after_mate is None

    def test_negative_becomes_positive(self):
        after_cp, _ = mover_pov_after(-200, None)
        assert after_cp == 200


@pytest.mark.unit
class TestWinProb:
    def test_equal_position(self):
        p = win_prob(0, None)
        assert abs(p - 0.5) < 0.01

    def test_positive_eval_above_half(self):
        p = win_prob(300, None)
        assert p > 0.5

    def test_negative_eval_below_half(self):
        p = win_prob(-300, None)
        assert p < 0.5

    def test_mate_positive_is_one(self):
        assert win_prob(None, 1) == 1.0

    def test_mate_negative_is_zero(self):
        assert win_prob(None, -1) == 0.0

    def test_very_large_cp_near_one(self):
        p = win_prob(5000, None)
        assert p > 0.99

    def test_symmetry(self):
        p_pos = win_prob(200, None)
        p_neg = win_prob(-200, None)
        assert abs(p_pos + p_neg - 1.0) < 1e-9


@pytest.mark.unit
class TestClassify:
    def setup_method(self):
        self.thresholds = {
            "excellent": 0.02,
            "good": 0.05,
            "inaccuracy": 0.10,
            "mistake": 0.20,
            "blunder": 0.30,
        }

    def test_best_move_overrides_win_drop(self):
        result = classify(0.50, True, self.thresholds)
        assert result == "best"

    def test_zero_drop_is_excellent(self):
        result = classify(0.0, False, self.thresholds)
        assert result == "excellent"

    def test_small_drop_is_good(self):
        result = classify(0.03, False, self.thresholds)
        assert result == "good"

    def test_medium_drop_is_inaccuracy(self):
        result = classify(0.07, False, self.thresholds)
        assert result == "inaccuracy"

    def test_large_drop_is_mistake(self):
        result = classify(0.15, False, self.thresholds)
        assert result == "mistake"

    def test_huge_drop_is_blunder(self):
        result = classify(0.40, False, self.thresholds)
        assert result == "blunder"


@pytest.mark.unit
class TestWorkerHelpers:
    def test_parse_duration_hours(self):
        from worker import parse_duration
        assert parse_duration("2h") == 7200

    def test_parse_duration_minutes(self):
        from worker import parse_duration
        assert parse_duration("90m") == 5400

    def test_parse_duration_seconds_suffix(self):
        from worker import parse_duration
        assert parse_duration("300s") == 300

    def test_parse_duration_bare_int(self):
        from worker import parse_duration
        assert parse_duration("300") == 300

    def test_parse_duration_none(self):
        from worker import parse_duration
        assert parse_duration(None) is None

    def test_configure_supported_drops_unknown_options(self):
        """configure_supported() must silently skip options the engine doesn't advertise."""
        from worker import configure_supported
        import chess.engine

        class FakeEngine:
            options = {"Threads": chess.engine.Option("Threads", "spin", 1, 1, 64, None)}
            def configure(self, opts):
                for k in opts:
                    assert k in self.options, f"Unexpected option: {k}"

        engine = FakeEngine()
        configure_supported(engine, {"Threads": 2, "Hash": 256, "Unknown": "x"})
        # If configure_supported works correctly, FakeEngine.configure is only
        # called with "Threads" (the only known option) and does not raise.
