"""Persisted configuration for Camargo.

In development, config.json lives next to the backend source. In the
packaged app, it's written under the OS user-data directory instead of the
install folder — the install folder gets wiped and replaced on every
upgrade (NSIS uninstalls the previous version first), so anything stored
there would be lost each time the user updates the app.
"""
import copy
import json
import sys
import threading
from pathlib import Path

from core.paths import is_frozen, user_data_dir


def _config_path():
    if is_frozen():
        return user_data_dir() / "config.json"

    return Path(__file__).resolve().parent.parent / "config.json"


CONFIG_PATH = _config_path()
CONFIG_LOCK = threading.RLock()

DEFAULT_CONFIG = {
    "instalock": {
        "enabled": False,
        "champions": [],
        "delay_seconds": 0.3,
        "modes": [],
        "smart_counter_pick": False,
    },
    "autoban": {
        "enabled": False,
        "champions": [],
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
        "champions": [],
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
    "ranked_presence": {
        "enabled": False,
        "tier": "",
        "division": "I",
    },
    "valorant_instalock": {
        "enabled": False,
        "agent": "None",
        "region": "",
        "modes": [],
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


#: Sections that used to store a single "champion" string before priority
#: lists existed.
_LEGACY_CHAMPION_SECTIONS = ("instalock", "autoban", "aram_bench_swap")


def _migrate_legacy_champion_field(config, merged):
    """Folds a pre-priority-list "champion" string into the new "champions"
    list, so upgrading doesn't silently drop it. Reads from the raw stored
    `config`, since `_merge_defaults` already dropped the now-unknown key.
    """
    for section in _LEGACY_CHAMPION_SECTIONS:
        old_section = config.get(section)
        if not isinstance(old_section, dict):
            continue
        old_value = old_section.get("champion")
        if old_value and old_value not in ("None", "Random") and not merged[section].get("champions"):
            merged[section]["champions"] = [old_value]
    return merged


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

    return _migrate_legacy_champion_field(config, merged)


def load_config():
    with CONFIG_LOCK:
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
                stored = json.load(config_file)
            on_disk = True
        except (FileNotFoundError, json.JSONDecodeError):
            stored = {}
            on_disk = False

        config = _merge_defaults(stored, DEFAULT_CONFIG)

        # Materialize the file on first run or after a schema change, but do
        # not rewrite it on every read.
        if not on_disk or config != stored:
            save_config(config)

        return config


#: Every feature mutates the shared config dict directly from its own
#: thread (setdefault, a plain `config["x"] = ...`) without acquiring
#: CONFIG_LOCK itself - threading the lock through every one of those call
#: sites across every feature would be a much larger change than this fix.
#: deepcopy() below can therefore legitimately race a concurrent in-place
#: mutation and raise "dictionary changed size during iteration" (or, for a
#: mutated list, the far quieter failure of copying a torn snapshot without
#: raising at all). The retry only guards the loud failure: a deepcopy that
#: raises is retried against whatever the dict looks like a moment later,
#: rather than surfacing as a crashed request for what is, from the user's
#: perspective, an ordinary toggle click.
_SAVE_RETRY_ATTEMPTS = 3


def save_config(config):
    with CONFIG_LOCK:
        for attempt in range(_SAVE_RETRY_ATTEMPTS):
            try:
                snapshot = json.dumps(copy.deepcopy(config), indent=4) + "\n"
                break
            except RuntimeError:
                if attempt == _SAVE_RETRY_ATTEMPTS - 1:
                    raise
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CONFIG_PATH.with_suffix(f"{CONFIG_PATH.suffix}.tmp")
        temporary_path.write_text(snapshot, encoding="utf-8")
        temporary_path.replace(CONFIG_PATH)
