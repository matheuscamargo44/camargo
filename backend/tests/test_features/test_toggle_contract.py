"""Every switch the UI draws must actually be wired to something.

`aram_augment_advisor` shipped in v0.10.0 with a switch in the UI and no
`toggle()` on the feature: clicking it POSTed to /features/{key}/toggle,
got HTTP 400 back, and the switch flipped straight back to off. Nothing in
either test suite covered that, because each side was individually
correct - only the contract between them was broken.

This is the same class of bug as test_threaded_lifecycle.py's ("the toggle
turned green and the automation never ran"), so it is checked the same way:
against the real list the frontend renders from.
"""
import copy
import re
from pathlib import Path

import pytest

from core.config import DEFAULT_CONFIG
from features.registry import FEATURE_CLASSES

FORMS_JS = Path(__file__).resolve().parents[3] / "desktop" / "src" / "views" / "forms.js"


def keys_with_a_plain_toggle():
    """Feature keys whose card shows at least one switch with no explicit
    action - those post to /features/{key}/toggle, which requires the
    feature to implement toggle()."""
    source = FORMS_JS.read_text(encoding="utf-8")

    block = re.search(r"export const FEATURE_TOGGLES = \{(.*?)\n\};", source, re.S)
    assert block, f"could not find FEATURE_TOGGLES in {FORMS_JS}"

    keys = []
    for key, entries in re.findall(r"(\w+):\s*\[(.*?)\],?\n", block.group(1), re.S):
        if re.search(r"action:\s*null", entries):
            keys.append(key)
    assert keys, "parsed FEATURE_TOGGLES but found no plain toggles - parser is broken"
    return keys


class StubClient:
    """Disconnected: constructing a feature must not need a live client."""

    def is_league_connected(self):
        return False

    def is_connected(self):
        return False

    def set_region(self, region):
        pass

    def lcu_request(self, method, endpoint, body=""):
        raise AssertionError("construction must not call the client")

    riot_request = lcu_request


@pytest.mark.parametrize("key", keys_with_a_plain_toggle())
def test_every_switch_in_the_ui_has_a_backend_toggle(key):
    feature_class = next((cls for cls in FEATURE_CLASSES if cls.key == key), None)
    assert feature_class is not None, f"forms.js draws a switch for unknown feature '{key}'"

    feature = feature_class(StubClient(), copy.deepcopy(DEFAULT_CONFIG))

    assert hasattr(feature, "toggle"), (
        f"'{key}' has a switch in forms.js but no toggle() - clicking it would return HTTP 400"
    )


#: chat_toggle is deliberately absent: its switch acts on the live client
#: (suspending chat) rather than storing a flag, so there is nothing in
#: config for the test below to check.
CONFIG_BACKED_TOGGLE_KEYS = [
    key
    for key in keys_with_a_plain_toggle()
    if isinstance(DEFAULT_CONFIG.get(key), dict) and "enabled" in DEFAULT_CONFIG[key]
]


@pytest.mark.parametrize("key", CONFIG_BACKED_TOGGLE_KEYS)
def test_toggle_flips_and_persists_the_stored_flag(key, tmp_path, monkeypatch):
    """A toggle that flips in memory but never writes config would look
    fine in the UI until the next restart."""
    import core.config

    config_path = tmp_path / "config.json"
    monkeypatch.setattr(core.config, "CONFIG_PATH", config_path)

    feature_class = next(cls for cls in FEATURE_CLASSES if cls.key == key)
    config = copy.deepcopy(DEFAULT_CONFIG)
    feature = feature_class(StubClient(), config)

    before = feature.get_status()["enabled"]
    feature.toggle()

    assert feature.get_status()["enabled"] != before, f"'{key}'.toggle() did not flip enabled"
    assert config_path.exists(), f"'{key}'.toggle() did not persist to config"
