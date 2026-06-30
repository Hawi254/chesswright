"""Unit tests for ingest.py parsing helpers."""
import pytest

from ingest import parse_game_id, parse_time_control, normalize_opening_family


@pytest.mark.unit
class TestParseGameId:
    def test_standard_lichess_url(self):
        assert parse_game_id("https://lichess.org/aaa00001") == "aaa00001"

    def test_url_with_trailing_slash(self):
        assert parse_game_id("https://lichess.org/aaa00001/") == "aaa00001"

    def test_none_returns_none(self):
        assert parse_game_id(None) is None

    def test_empty_string_returns_none(self):
        assert parse_game_id("") is None

    def test_bare_id(self):
        assert parse_game_id("aaa00001") == "aaa00001"


@pytest.mark.unit
class TestParseTimeControl:
    def test_blitz_300_plus_0(self):
        base, inc, cat = parse_time_control("300+0")
        assert base == 300
        assert inc == 0
        assert cat == "blitz"

    def test_rapid_600_plus_5(self):
        base, inc, cat = parse_time_control("600+5")
        assert base == 600
        assert inc == 5
        assert cat == "rapid"

    def test_bullet_60_plus_0(self):
        base, inc, cat = parse_time_control("60+0")
        assert base == 60
        assert cat == "bullet"

    def test_classical_1800_plus_30(self):
        base, inc, cat = parse_time_control("1800+30")
        assert cat == "classical"

    def test_ultrabullet_15_plus_0(self):
        base, inc, cat = parse_time_control("15+0")
        assert cat == "ultrabullet"

    def test_malformed_returns_nones(self):
        base, inc, cat = parse_time_control("not_a_tc")
        assert base is None and inc is None and cat is None

    def test_none_returns_nones(self):
        base, inc, cat = parse_time_control(None)
        assert base is None and inc is None and cat is None

    def test_empty_string_returns_nones(self):
        base, inc, cat = parse_time_control("")
        assert base is None


@pytest.mark.unit
class TestNormalizeOpeningFamily:
    def test_strips_variation(self):
        result = normalize_opening_family("Italian Game: Evans Gambit")
        assert result == "Italian Game"

    def test_no_colon_returns_as_is(self):
        result = normalize_opening_family("King's Pawn Game")
        assert result == "King's Pawn Game"

    def test_none_returns_none(self):
        assert normalize_opening_family(None) is None

    def test_empty_returns_none(self):
        assert normalize_opening_family("") is None

    def test_multiple_colons_strips_after_first(self):
        result = normalize_opening_family("Sicilian Defense: Najdorf Variation: Adams Attack")
        assert result == "Sicilian Defense"
