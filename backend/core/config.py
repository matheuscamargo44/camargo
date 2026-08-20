"""Persisted configuration for Camargo.

In development, config.json lives next to the backend source. In the
packaged app, it's written under the OS user-data directory instead of the
install folder — the install folder gets wiped and replaced on every
upgrade (NSIS uninstalls the previous version first), so anything stored
there would be lost each time the user updates the app.
"""
import copy
import json
import os
import sys
import threading
from pathlib import Path


def _user_data_dir():
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "camargo"
    return Path.home() / ".config" / "camargo"


def _config_path():
    if getattr(sys, "frozen", False):
        return _user_data_dir() / "config.json"

    return Path(__file__).resolve().parent.parent / "config.json"


CONFIG_PATH = _config_path()
CONFIG_LOCK = threading.RLock()

DEFAULT_CONFIG = {
    "instalock": {
        "enabled": False,
        "champion": "None",
        "delay_seconds": 0.3,
    },
    "autoban": {
        "enabled": False,
        "champion": "None",
        "delay_seconds": 0.3,
    },
    "auto_accept": {
        "enabled": False,
        "delay_seconds": 0.0,
    },
    "auto_play_again": {
        "enabled": False,
    },
    "aram_bench_swap": {
        "enabled": False,
        "champion": "None",
    },
    "auto_honor": {
        "enabled": False,
    },
    "auto_party_invite": {
        "enabled": False,
        "summoners": "",
    },
    "random_skin": {
        "enabled": False,
    },
}

MIN_AUTOMATION_DELAY = 0.0
MAX_AUTOMATION_DELAY = 2.0


def get_automation_delay(config, section, default):
    try:
        value = float(config.get(section, {}).get("delay_seconds", default))
    except (TypeError, ValueError):
        value = default
    return round(min(MAX_AUTOMATION_DELAY, max(MIN_AUTOMATION_DELAY, value)), 1)


def _merge_defaults(config, defaults):
    merged = copy.deepcopy(defaults)

    if not isinstance(config, dict):
        return merged

    for key, value in config.items():
        if key not in defaults:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(value, merged[key])
        else:
            merged[key] = value

    # Migrate any legacy "Random" setting to "None"
    if merged.get("instalock", {}).get("champion") == "Random":
        merged["instalock"]["champion"] = "None"

    return merged


def load_config():
    with CONFIG_LOCK:
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
                config = json.load(config_file)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        config = _merge_defaults(config, DEFAULT_CONFIG)
        save_config(config)
        return config


def save_config(config):
    with CONFIG_LOCK:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CONFIG_PATH.with_suffix(f"{CONFIG_PATH.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(config, indent=4) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(CONFIG_PATH)
