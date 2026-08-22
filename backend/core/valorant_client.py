"""Thin wrapper around valclient's Client for the Riot local API and VALORANT's
remote pregame (glz) endpoints.

Feature/business logic does not live here — this only owns activating the
underlying valclient session and re-activating it when it goes stale (game
restarted, region changed). Mirrors the role LCUClient plays for League.
"""
import json
import logging
import os
import threading
import time

import psutil
import requests
from valclient.client import Client as ValClient
from valclient.exceptions import HandshakeError, PhaseError

logger = logging.getLogger(__name__)

VALORANT_PROCESS_NAMES = {
    "valorant.exe",
    "valorant-win64-shipping.exe",
    "valorant-win32-shipping.exe",
}

VALID_REGIONS = tuple(ValClient.fetch_regions())

AGENTS_ENDPOINT = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"

#: Re-activating means a fresh handshake with the local Riot client (lockfile
#: read + entitlements token + a client-version lookup). The instalock loop
#: plus the /health poll would otherwise pay that cost several times a second.
ACTIVATION_TTL_SECONDS = 5.0


def is_valorant_running():
    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() in VALORANT_PROCESS_NAMES:
                return True
    except Exception:
        logger.exception("is_valorant_running failed")
    return False


def detect_region():
    """Best-effort region guess read out of VALORANT's own log file.

    Returns None if it can't be determined (game never launched this
    machine, log rotated, or Riot changed the log's format).
    """
    log_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "VALORANT", "Saved", "Logs", "ShooterGame.log"
    )
    try:
        with open(log_path, "rb") as log_file:
            lines = log_file.readlines()
    except OSError:
        return None

    for marker in (b"regions/", b"config/"):
        for line in lines:
            if marker in line:
                try:
                    region = line.split(marker)[1].split(b"]")[0].decode().strip().lower()
                except (IndexError, UnicodeDecodeError):
                    continue
                if region in VALID_REGIONS:
                    return region
    return None


class ValorantClient:
    """Single shared connection to the Riot/VALORANT local + glz APIs.

    Meant to be instantiated once and injected into every Valorant feature,
    instead of each feature activating its own valclient session.
    """

    def __init__(self, region=None):
        self._lock = threading.RLock()
        self._region_override = region
        self._client = None
        self._activated_at = 0.0

    def set_region(self, region):
        """Pins a specific region, or clears the override (None) to fall
        back to auto-detection from the game's log file.
        """
        with self._lock:
            if region != self._region_override:
                self._region_override = region
                self._client = None  # force re-activation under the new region

    def _ensure_activated(self, force=False):
        with self._lock:
            if self._client is not None and not force:
                if time.monotonic() - self._activated_at < ACTIVATION_TTL_SECONDS:
                    return self._client

            region = self._region_override or detect_region()
            if not region:
                raise HandshakeError("Could not determine VALORANT's region")

            try:
                client = ValClient(region=region)
                client.activate()
            except HandshakeError:
                raise
            except Exception as exc:
                raise HandshakeError(str(exc)) from exc

            self._client = client
            self._activated_at = time.monotonic()
            return client

    def is_connected(self):
        if not is_valorant_running():
            return False
        try:
            self._ensure_activated()
            return True
        except HandshakeError:
            return False

    @property
    def player_name(self):
        return self._client.player_name if self._client else ""

    @property
    def player_tag(self):
        return self._client.player_tag if self._client else ""

    def _call(self, method_name, *args, **kwargs):
        """Runs a valclient method, retrying once after a forced
        re-activation if the session looks stale (game restarted, the local
        port changed). `PhaseError` is not stale-session territory — it just
        means "not in this game phase right now" — so it passes straight
        through instead of triggering a pointless reactivation.
        """
        client = self._ensure_activated()
        try:
            return getattr(client, method_name)(*args, **kwargs)
        except PhaseError:
            raise
        except Exception:
            client = self._ensure_activated(force=True)
            return getattr(client, method_name)(*args, **kwargs)

    def fetch_presence(self):
        return self._call("fetch_presence")

    def pregame_fetch_match(self):
        return self._call("pregame_fetch_match")

    def pregame_select_character(self, agent_id):
        return self._call("pregame_select_character", agent_id)

    def pregame_lock_character(self, agent_id):
        return self._call("pregame_lock_character", agent_id)

    def pregame_quit_match(self):
        return self._call("pregame_quit_match")

    def local_request(self, method, endpoint, body=None):
        """Raw call to the Riot Client's local API (not VALORANT-specific —
        e.g. `/chat/v1/*` is the same chat session League's LCUClient talks
        to, just reached here via the lockfile instead of the League process).
        """
        client = self._ensure_activated()
        payload = None if body is None else json.dumps(body)
        return requests.request(
            method,
            f"https://127.0.0.1:{client.lockfile['port']}{endpoint}",
            headers=client.local_headers,
            data=payload,
            verify=False,
            timeout=10,
        )

    def fetch_player_loadout(self):
        return self._call("fetch_player_loadout")

    def put_player_loadout(self, loadout):
        return self._call("put_player_loadout", loadout)

    def fetch_entitlements(self, item_type):
        """Owned items of one item-type UUID (player cards, sprays, etc)."""
        return self._call("store_fetch_entitlements", item_type)

    def fetch_mmr(self):
        return self._call("fetch_mmr")

    def fetch_competitive_updates(self, start_index=0, end_index=5):
        return self._call(
            "fetch_competitive_updates", start_index=start_index, end_index=end_index, queue_id="competitive"
        )

    def fetch_player_restrictions(self):
        return self._call("fetch_player_restrictions")

    def fetch_agent_directory(self):
        """Public, unauthenticated agent list (name -> uuid, icons, etc).
        Not part of valclient/the Riot API: VALORANT has no local equivalent
        of League's champion-summary endpoint, so this is the same
        community API (valorant-api.com) the two reference tools use.
        """
        return requests.get(AGENTS_ENDPOINT, timeout=10)
