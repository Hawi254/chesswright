"""Integration test for react_desktop_app.py's subprocess lifecycle --
start, serve, clean shutdown, no orphaned process. Mirrors what
api/spike_launcher.py's own manual main() already proved by hand;
this pins it as an automated regression. Does NOT drive pywebview itself
(no automated test framework here does that for the Streamlit build
either -- window creation is verified live/manually, per this project's
existing convention).
"""
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import react_desktop_app


@pytest.mark.integration
def test_api_subprocess_starts_serves_and_shuts_down_cleanly(migrated_db_path, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    _config.set_player_name("react_launcher_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    port = react_desktop_app.desktop_app.free_port()
    proc = react_desktop_app.launch_api_subprocess(port, str(scratch_config))
    try:
        url = f"http://127.0.0.1:{port}"
        assert react_desktop_app.desktop_app.wait_for_server(f"{url}/api/overview/headline-stats"), \
            "API subprocess did not start in time"

        import urllib.request
        resp = urllib.request.urlopen(f"{url}/api/overview/headline-stats", timeout=5)
        assert resp.status == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert proc.poll() is not None, "API subprocess did not exit cleanly"
