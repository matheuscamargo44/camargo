import logging
import time
from core.config import save_config
from features.base import Feature

logger = logging.getLogger(__name__)


class AutoHonor(Feature):
    key = "auto_honor"
    title = "Auto Honor"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.last_honored_game_id = None

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.config.get("auto_honor", {}).get("enabled", False),
        }

    def toggle(self, state: bool = None) -> bool:
        current = self.config.get("auto_honor", {}).get("enabled", False)
        new_state = (not current) if state is None else state
        self.config.setdefault("auto_honor", {})["enabled"] = new_state
        save_config(self.config)
        self.on_event("info", f"Auto Honor {'enabled' if new_state else 'disabled'}")
        return new_state

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                time.sleep(2)
                continue

            if not self.config.get("auto_honor", {}).get("enabled", False):
                time.sleep(2)
                continue

            try:
                ballot_res = self.lcu.lcu_request("GET", "/lol-honor-v2/v1/ballot")
                if ballot_res.status_code == 200:
                    ballot = ballot_res.json()
                    game_id = ballot.get("gameId")
                    eligible_players = ballot.get("eligiblePlayers", [])

                    if eligible_players and game_id and game_id != self.last_honored_game_id:
                        target_player = eligible_players[0]
                        summoner_id = target_player.get("summonerId")

                        payload = {
                            "honorCategory": "HEART",
                            "summonerId": summoner_id,
                            "gameId": game_id,
                        }

                        honor_res = self.lcu.lcu_request(
                            "POST",
                            "/lol-honor-v2/v1/honor-player",
                            payload,
                        )
                        if honor_res.status_code in (200, 201, 204):
                            self.last_honored_game_id = game_id
                            self.on_event("success", "Auto Honor: Voted for teammate")
                            time.sleep(2)
            except Exception as e:
                logger.debug(f"AutoHonor error: {e}")

            time.sleep(2)
