"""Unit tests for lichess_cloud_eval.py -- perspective flip, UCI->SAN PV
conversion, and fail-quiet handling on a miss/timeout. No real network
calls: requests.get is mocked throughout."""
from unittest.mock import patch, MagicMock

import pytest
import requests

import lichess_cloud_eval

# After 1.e4 -- Black to move. Lichess's cp/mate are documented as
# White's POV, so a Black-to-move position must have its sign flipped
# by fetch_cloud_eval() before it matches this codebase's own
# side-to-move-POV convention.
FEN_BLACK_TO_MOVE = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
FEN_WHITE_TO_MOVE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _mock_response(status_code=200, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    return resp


@pytest.mark.unit
class TestFetchCloudEval:
    def test_flips_white_pov_cp_for_black_to_move(self):
        body = {"fen": FEN_BLACK_TO_MOVE, "depth": 40, "knodes": 500000,
                 "pvs": [{"cp": 25, "moves": "c7c5 g1f3 d7d6"}]}
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(json_body=body)):
            result = lichess_cloud_eval.fetch_cloud_eval(FEN_BLACK_TO_MOVE)

        assert result is not None
        assert result.eval_cp == -25  # White +25 -> Black-to-move POV -25
        assert result.eval_mate is None
        assert result.best_move_san == "c5"
        assert result.engine_version == "Lichess cloud"
        assert result.depth == 40

    def test_does_not_flip_for_white_to_move(self):
        body = {"fen": FEN_WHITE_TO_MOVE, "depth": 45, "knodes": 900000,
                 "pvs": [{"cp": 30, "moves": "e2e4 e7e5"}]}
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(json_body=body)):
            result = lichess_cloud_eval.fetch_cloud_eval(FEN_WHITE_TO_MOVE)

        assert result is not None
        assert result.eval_cp == 30
        assert result.best_move_san == "e4"

    def test_flips_mate_score_too(self):
        body = {"fen": FEN_BLACK_TO_MOVE, "depth": 50, "knodes": 100,
                 "pvs": [{"mate": 3, "moves": "d8h4"}]}
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(json_body=body)):
            result = lichess_cloud_eval.fetch_cloud_eval(FEN_BLACK_TO_MOVE)

        assert result is not None
        assert result.eval_cp is None
        assert result.eval_mate == -3

    def test_converts_uci_pv_to_san_list(self):
        import json
        body = {"fen": FEN_WHITE_TO_MOVE, "depth": 40, "knodes": 100,
                 "pvs": [{"cp": 10, "moves": "e2e4 e7e5 g1f3"}]}
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(json_body=body)):
            result = lichess_cloud_eval.fetch_cloud_eval(FEN_WHITE_TO_MOVE)

        assert json.loads(result.pv_json) == ["e4", "e5", "Nf3"]

    def test_returns_none_on_404_miss(self):
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(status_code=404)):
            assert lichess_cloud_eval.fetch_cloud_eval(FEN_WHITE_TO_MOVE) is None

    def test_returns_none_on_429_rate_limit(self):
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(status_code=429)):
            assert lichess_cloud_eval.fetch_cloud_eval(FEN_WHITE_TO_MOVE) is None

    def test_returns_none_on_timeout(self):
        with patch("lichess_cloud_eval.requests.get", side_effect=requests.exceptions.Timeout):
            assert lichess_cloud_eval.fetch_cloud_eval(FEN_WHITE_TO_MOVE) is None

    def test_returns_none_on_malformed_response(self):
        with patch("lichess_cloud_eval.requests.get", return_value=_mock_response(json_body={"pvs": []})):
            assert lichess_cloud_eval.fetch_cloud_eval(FEN_WHITE_TO_MOVE) is None
