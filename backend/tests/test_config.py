import pytest
from core import config as config_module
from core import paths as paths_module


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
    assert loaded["instalock"]["champions"] == []


def test_load_config_migrates_a_legacy_single_champion(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"instalock": {"enabled": true, "champion": "Ahri"}, '
        '"autoban": {"champion": "Yasuo"}, '
        '"aram_bench_swap": {"champion": "Teemo"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    loaded = config_module.load_config()

    assert loaded["instalock"]["champions"] == ["Ahri"]
    assert loaded["autoban"]["champions"] == ["Yasuo"]
    assert loaded["aram_bench_swap"]["champions"] == ["Teemo"]


def test_load_config_migration_ignores_none_and_random(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"instalock": {"champion": "None"}, "autoban": {"champion": "Random"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    loaded = config_module.load_config()

    assert loaded["instalock"]["champions"] == []
    assert loaded["autoban"]["champions"] == []


def test_get_automation_delay_clamps_range():
    config = {"auto_accept": {"delay_seconds": 99}}
    assert config_module.get_automation_delay(config, "auto_accept", 0.0) == 2.0

    config = {"auto_accept": {"delay_seconds": -5}}
    assert config_module.get_automation_delay(config, "auto_accept", 0.0) == 0.0


# `sys.frozen` is read by core.paths.is_frozen(), which is what config.py
# actually calls. These used to patch `config_module.sys` - which worked only
# because `sys` is a singleton reachable through any importing module's
# namespace, and read as though config.py decided frozen-ness itself. Patching
# the module that owns the behaviour points the test at the real collaborator,
# and stops it breaking when config.py drops an import it never used.
def test_config_path_uses_appdata_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(paths_module.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    path = config_module._config_path()

    assert path == tmp_path / "camargo" / "config.json"


def test_config_path_next_to_source_in_dev(monkeypatch):
    monkeypatch.setattr(paths_module.sys, "frozen", False, raising=False)

    path = config_module._config_path()
    expected_dir = config_module.Path(config_module.__file__).resolve().parent.parent

    assert path == expected_dir / "config.json"


def test_load_config_does_not_rewrite_an_up_to_date_file(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    config_module.load_config()  # first run writes the defaults
    first_write = config_path.stat().st_mtime_ns

    for _ in range(5):
        config_module.load_config()

    assert config_path.stat().st_mtime_ns == first_write, "reading config must not touch the disk"


def test_save_config_retries_a_deepcopy_that_races_a_concurrent_mutation(tmp_path, monkeypatch):
    """Every feature mutates the shared config dict from its own thread
    without holding CONFIG_LOCK - a deepcopy here can genuinely race one of
    those mutations and raise "dictionary changed size during iteration".
    That must not surface as a crashed save for what is, from the user's
    perspective, an ordinary toggle click."""
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    calls = {"n": 0}
    real_deepcopy = config_module.copy.deepcopy

    def flaky_deepcopy(value):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("dictionary changed size during iteration")
        return real_deepcopy(value)

    monkeypatch.setattr(config_module.copy, "deepcopy", flaky_deepcopy)

    config_module.save_config({"auto_accept": {"enabled": True}})

    assert calls["n"] == 2
    assert config_path.exists()


def test_save_config_gives_up_after_exhausting_retries(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    def always_raises(value):
        raise RuntimeError("dictionary changed size during iteration")

    monkeypatch.setattr(config_module.copy, "deepcopy", always_raises)

    try:
        config_module.save_config({"auto_accept": {"enabled": True}})
        pytest.fail("expected the persistent race to eventually raise")
    except RuntimeError:
        pass

    assert not config_path.exists()
