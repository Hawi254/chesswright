"""Unit tests for onboarding's first-run timing capture (Phase D go/no-go
signal #5 -- estimate must land within 2x of actual measured time)."""
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def test_record_first_run_timing_writes_json_next_to_db(tmp_path):
    import onboarding_view
    db = tmp_path / "chess.db"
    db.write_bytes(b"")  # helper only uses the parent dir, not the db itself
    record = {
        "estimate_minutes": 20.0,
        "actual_minutes": 24.5,
        "batch_size": 30,
        "ratio_actual_over_estimate": 1.23,
    }
    onboarding_view._record_first_run_timing(str(db), record)

    out = tmp_path / "first_run_timing.json"
    assert out.exists()
    assert json.loads(out.read_text()) == record


def test_record_first_run_timing_is_best_effort_and_never_raises():
    import onboarding_view
    # Parent directory does not exist: must swallow the write error rather
    # than crash the onboarding flow over a telemetry-ish side file.
    onboarding_view._record_first_run_timing(
        "/nonexistent/dir/deep/chess.db", {"anything": 1})
