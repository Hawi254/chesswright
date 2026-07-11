"""Unit tests for settings_view.py's pure-logic helpers (extracted from
Streamlit UI glue so they're testable without a real Stockfish binary)."""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "dashboard"))
import settings_view


@pytest.mark.unit
class TestInstallEngineBinary:
    def test_copies_chmods_and_validates(self, tmp_path):
        src = tmp_path / "fake_stockfish"
        src.write_text("#!/bin/sh\necho fake\n")
        engines_dir = tmp_path / "engines"

        name = settings_view._install_engine_binary(
            src, engines_dir, validate_fn=lambda p: "Fake Engine 1.0")

        dest = engines_dir / "fake_stockfish"
        assert dest.exists()
        assert os.access(dest, os.X_OK)
        assert name == "Fake Engine 1.0"

    def test_removes_file_on_validation_failure(self, tmp_path):
        src = tmp_path / "not_an_engine"
        src.write_text("garbage")
        engines_dir = tmp_path / "engines"

        def fail(_path):
            raise RuntimeError("not a UCI engine")

        with pytest.raises(RuntimeError, match="not a UCI engine"):
            settings_view._install_engine_binary(src, engines_dir, validate_fn=fail)

        assert not (engines_dir / "not_an_engine").exists()


@pytest.mark.unit
class TestInstallEngineUpload:
    def test_writes_bytes_chmods_and_validates(self, tmp_path):
        class FakeUpload:
            name = "fake_upload_engine"
            def getvalue(self):
                return b"#!/bin/sh\necho fake\n"

        engines_dir = tmp_path / "engines"
        name = settings_view._install_engine_upload(
            FakeUpload(), engines_dir, validate_fn=lambda p: "Fake Engine 2.0")

        dest = engines_dir / "fake_upload_engine"
        assert dest.exists()
        assert os.access(dest, os.X_OK)
        assert name == "Fake Engine 2.0"
