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
    assert loaded["instalock"]["champion"] == "None"


def test_get_automation_delay_clamps_range():
    config = {"auto_accept": {"delay_seconds": 99}}
    assert config_module.get_automation_delay(config, "auto_accept", 0.0) == 2.0

    config = {"auto_accept": {"delay_seconds": -5}}
    assert config_module.get_automation_delay(config, "auto_accept", 0.0) == 0.0


def test_config_path_uses_appdata_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    path = config_module._config_path()

    assert path == tmp_path / "camargo" / "config.json"


def test_config_path_next_to_source_in_dev(monkeypatch):
    monkeypatch.setattr(config_module.sys, "frozen", False, raising=False)

    path = config_module._config_path()
    expected_dir = config_module.Path(config_module.__file__).resolve().parent.parent

    assert path == expected_dir / "config.json"
