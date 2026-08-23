"""Shared filesystem locations for anything that must survive an app
upgrade or a crash: config (core/config.py) and, since this module, the
persistent activity log (core/activity_log.py).

Both packaged and dev builds need the same split: the install folder gets
wiped and replaced on every upgrade (NSIS uninstalls the previous version
first), so persistent data must live under the OS user-data directory
instead — but only in the packaged build; in dev it's more convenient to
keep everything next to the source.
"""
import os
import sys
from pathlib import Path


def user_data_dir():
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "camargo"
    return Path.home() / ".config" / "camargo"


def is_frozen():
    return bool(getattr(sys, "frozen", False))
