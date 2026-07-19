"""Unit tests for config.py — targeted YAML mutations that preserve comments."""
import pathlib
import pytest

import config


@pytest.mark.unit
class TestSetPlayerName:
    def test_replaces_change_me(self, config_yaml):
        config.set_player_name("DrNykterstein", path=config_yaml)
        text = config_yaml.read_text()
        assert 'name: "DrNykterstein"' in text
        assert "CHANGE_ME" not in text

    def test_replaces_existing_name(self, config_yaml):
        config.set_player_name("PlayerOne", path=config_yaml)
        config.set_player_name("PlayerTwo", path=config_yaml)
        text = config_yaml.read_text()
        assert 'name: "PlayerTwo"' in text
        assert "PlayerOne" not in text

    def test_does_not_corrupt_other_sections(self, config_yaml):
        config.set_player_name("TestUser", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["database"]["path"] == "chess.db"
        assert cfg["engine"]["path"] is None

    def test_raises_on_malformed_config(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("no_player_section: true\n")
        with pytest.raises(ValueError, match="Could not find"):
            config.set_player_name("X", path=bad)


@pytest.mark.unit
class TestSetDatabasePath:
    def test_replaces_database_path(self, config_yaml):
        config.set_database_path("/home/user/.chesswright/chess.db", path=config_yaml)
        text = config_yaml.read_text()
        assert "/home/user/.chesswright/chess.db" in text

    def test_does_not_touch_engine_path(self, config_yaml):
        config.set_database_path("/home/user/.chesswright/chess.db", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["engine"]["path"] is None

    def test_raises_on_missing_database_section(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("player:\n  name: \"X\"\n")
        with pytest.raises(ValueError, match="Could not find"):
            config.set_database_path("/some/path.db", path=bad)


@pytest.mark.unit
class TestSetAnalyticsSetting:
    def test_sets_utc_offset_hours(self, config_yaml):
        config.set_analytics_setting("utc_offset_hours", -5, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["analytics"]["utc_offset_hours"] == -5

    def test_does_not_touch_other_analytics_keys(self, config_yaml):
        config.set_analytics_setting("utc_offset_hours", 3, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["analytics"]["min_sample_size"] == 5


@pytest.mark.unit
class TestLoadConfig:
    def test_loads_all_expected_sections(self, config_yaml):
        cfg = config.load_config(config_yaml)
        assert "player" in cfg
        assert "database" in cfg
        assert "engine" in cfg
        assert "interactive_engine" in cfg

    def test_player_name_default(self, config_yaml):
        cfg = config.load_config(config_yaml)
        assert cfg["player"]["name"] == "CHANGE_ME"

    def test_interactive_engine_defaults(self, config_yaml):
        cfg = config.load_config(config_yaml)
        ie = cfg["interactive_engine"]
        assert ie["threads"] == 1
        assert ie["hash_mb"] == 32
        assert ie["time_sec"] == 0.5
        assert ie["depth"] == 20
        assert ie["store_threshold"] == 20


@pytest.mark.unit
class TestBackfillMissingKeys:
    """config_yaml is a minimal fixture missing most of the real
    config.yaml's keys -- exactly the "user config created before a key
    was added to the template" shape this function exists to fix."""

    def test_backfills_missing_key_in_existing_section(self, config_yaml):
        # NOTE: config_yaml's engine: section was widened (Task 7, Phase 6
        # Settings) to include multipv/threads/hash_mb, so those keys no
        # longer exercise the "missing key" case. Swapped to worker.max_games,
        # which the fixture's worker: section still genuinely omits -- same
        # original intent (a key present in the template but absent from an
        # existing section gets backfilled), different still-missing key.
        cfg = config.load_config(config_yaml)
        assert "max_games" not in cfg["worker"]

        config.backfill_missing_keys(path=config_yaml)

        cfg = config.load_config(config_yaml)
        assert cfg["worker"]["max_games"] == 100

    def test_backfills_worker_max_duration_default(self, config_yaml):
        """worker.max_duration (and other keys added to config.yaml's
        worker: section after a user's install was created) must reach
        existing installs via this same mechanism -- an install missing the
        key gets the template's own default backfilled, not a KeyError
        somewhere deep in a worker.py or dashboard config read.

        NOTE: originally probed engine.threads, but config_yaml's engine:
        section was widened (Task 7, Phase 6 Settings) to include threads
        (and multipv/hash_mb) as part of the Engine Profiles fixture setup,
        so that key is no longer "missing" here. Swapped to
        worker.max_duration, which is still genuinely absent from the
        fixture's worker: section -- same intent, different key."""
        cfg = config.load_config(config_yaml)
        assert "max_duration" not in cfg["worker"]

        config.backfill_missing_keys(path=config_yaml)

        cfg = config.load_config(config_yaml)
        assert cfg["worker"]["max_duration"] is None

    def test_preserves_existing_values(self, config_yaml):
        config.backfill_missing_keys(path=config_yaml)
        cfg = config.load_config(config_yaml)
        # depth was already set in the fixture -- must not be clobbered
        # with the template's own default.
        assert cfg["engine"]["depth"] == 20

    def test_does_not_add_new_top_level_section(self, config_yaml):
        cfg = config.load_config(config_yaml)
        assert "annotation" not in cfg

        config.backfill_missing_keys(path=config_yaml)

        cfg = config.load_config(config_yaml)
        assert "annotation" not in cfg

    def test_idempotent(self, config_yaml):
        config.backfill_missing_keys(path=config_yaml)
        text_once = config_yaml.read_text()
        config.backfill_missing_keys(path=config_yaml)
        text_twice = config_yaml.read_text()
        assert text_once == text_twice

    def test_result_still_parses(self, config_yaml):
        config.backfill_missing_keys(path=config_yaml)
        text = config_yaml.read_text()
        import yaml
        yaml.safe_load(text)  # raises if malformed


@pytest.mark.unit
class TestSetIngestionSetting:
    def test_sets_variant_policy(self, config_yaml):
        config.set_ingestion_setting("variant_policy", "include", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["ingestion"]["variant_policy"] == "include"

    def test_sets_queue_strategy(self, config_yaml):
        config.set_ingestion_setting("queue_strategy", "chronological", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["ingestion"]["queue_strategy"] == "chronological"


@pytest.mark.unit
class TestSetSyncSettings:
    def test_sets_sync_timeout(self, config_yaml):
        config.set_sync_setting("request_timeout_seconds", 60, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["sync"]["request_timeout_seconds"] == 60

    def test_sets_sync_chesscom_timeout(self, config_yaml):
        config.set_sync_chesscom_setting("request_timeout_seconds", 45, path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["sync_chesscom"]["request_timeout_seconds"] == 45


@pytest.mark.unit
class TestPick:
    def test_cli_value_wins_over_config(self):
        assert config.pick("cli_val", "config_val") == "cli_val"

    def test_none_cli_falls_back_to_config(self):
        assert config.pick(None, "config_val") == "config_val"

    def test_falsy_cli_wins_over_config(self):
        # 0 and False are legitimate CLI values, not "not given"
        assert config.pick(0, 99) == 0
        assert config.pick(False, True) is False


@pytest.mark.unit
class TestResetEnginePath:
    def test_clears_back_to_null(self, config_yaml):
        config.set_engine_path("/usr/bin/stockfish", path=config_yaml)
        config.reset_engine_path(path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["engine"]["path"] is None


@pytest.mark.unit
class TestEngineProfiles:
    def test_save_and_list(self, config_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        config.save_engine_profile("Laptop", path=config_yaml)
        assert config.list_engine_profiles() == ["Laptop"]

    def test_apply_writes_back_engine_and_interactive_settings(self, config_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        config.set_engine_setting("depth", 30, path=config_yaml)
        config.save_engine_profile("Deep", path=config_yaml)
        config.set_engine_setting("depth", 14, path=config_yaml)
        config.apply_engine_profile("Deep", path=config_yaml)
        cfg = config.load_config(config_yaml)
        assert cfg["engine"]["depth"] == 30

    def test_delete_removes_profile(self, config_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        config.save_engine_profile("Temp", path=config_yaml)
        config.delete_engine_profile("Temp")
        assert config.list_engine_profiles() == []

    def test_list_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ENGINE_PROFILES_PATH", tmp_path / "engine_profiles.yaml")
        assert config.list_engine_profiles() == []
