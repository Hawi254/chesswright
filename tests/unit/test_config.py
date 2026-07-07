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
        cfg = config.load_config(config_yaml)
        assert "multipv" not in cfg["engine"]

        config.backfill_missing_keys(path=config_yaml)

        cfg = config.load_config(config_yaml)
        assert cfg["engine"]["multipv"] == 3

    def test_preserves_existing_values(self, config_yaml):
        config.backfill_missing_keys(path=config_yaml)
        cfg = config.load_config(config_yaml)
        # depth was already set in the fixture -- must not be clobbered
        # with the template's own default.
        assert cfg["engine"]["depth"] == 20

    def test_does_not_add_new_top_level_section(self, config_yaml):
        cfg = config.load_config(config_yaml)
        assert "analytics" not in cfg

        config.backfill_missing_keys(path=config_yaml)

        cfg = config.load_config(config_yaml)
        assert "analytics" not in cfg

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
class TestPick:
    def test_cli_value_wins_over_config(self):
        assert config.pick("cli_val", "config_val") == "cli_val"

    def test_none_cli_falls_back_to_config(self):
        assert config.pick(None, "config_val") == "config_val"

    def test_falsy_cli_wins_over_config(self):
        # 0 and False are legitimate CLI values, not "not given"
        assert config.pick(0, 99) == 0
        assert config.pick(False, True) is False
