"""Thin client for League's Live Client Data API (127.0.0.1:2999).

Only reachable while a match is actually in progress, with a self-signed
certificate. Unlike LCUClient there's no credential discovery here (the
port is fixed and there's no auth) - this is a genuinely different local
API, not another LCU endpoint, so it gets its own module.
"""
import logging

import requests
import urllib3

urllib3.disable_warnings()

logger = logging.getLogger(__name__)

BASE_URL = "https://127.0.0.1:2999/liveclientdata"
REQUEST_TIMEOUT_SECONDS = 2.0


def get_all_game_data(timeout=REQUEST_TIMEOUT_SECONDS):
    """Returns the parsed allgamedata payload, or None if no match is in
    progress right now. A connection refused/timeout here is the normal
    idle state (this API is only up during a live match) - not worth
    logging as an error.
    """
    try:
        response = requests.get(f"{BASE_URL}/allgamedata", verify=False, timeout=timeout)
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        return response.json()
    except ValueError:
        return None


def local_player(data):
    """Given an already-fetched allgamedata payload, returns the
    `allPlayers[]` entry for the local player (matched by riotId against
    `activePlayer`), or None if it can't be resolved.
    """
    active_riot_id = data.get("activePlayer", {}).get("riotId")
    if not active_riot_id:
        return None
    for player in data.get("allPlayers", []):
        if player.get("riotId") == active_riot_id:
            return player
    return None
