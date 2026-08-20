from core import config as config_module


def test_load_config_fills_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")

    loaded = config_module.load_config()

    assert loaded["auto_accept"]["enabled"] is False
    assert (tmp_path / "config.json").exists()


def test_load_config_preserves_existing_values(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"auto_accept": {"enabled": true}}', encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    loaded = config_module.load_config()

    assert loaded["auto_accept"]["enabled"] is True
    assert loaded["instalock"]["champion"] == "Random"


def test_get_automation_delay_clamps_range():
    config = {"auto_accept": {"delay_seconds": 99}}
    assert config_module.get_automation_delay(config, "auto_accept", 0.0) == 2.0

    config = {"auto_accept": {"delay_seconds": -5}}
    assert config_module.get_automation_delay(config, "auto_accept", 0.0) == 0.0
