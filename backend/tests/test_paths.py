import core.paths as paths_module


def test_user_data_dir_uses_appdata_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths_module.user_data_dir() == tmp_path / "camargo"


def test_user_data_dir_falls_back_to_home_without_appdata(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    assert paths_module.user_data_dir() == paths_module.Path.home() / ".config" / "camargo"


def test_is_frozen_reflects_sys_frozen(monkeypatch):
    monkeypatch.setattr(paths_module.sys, "frozen", True, raising=False)
    assert paths_module.is_frozen() is True

    monkeypatch.setattr(paths_module.sys, "frozen", False, raising=False)
    assert paths_module.is_frozen() is False
