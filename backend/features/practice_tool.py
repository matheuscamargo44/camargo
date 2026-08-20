import logging
import time
from features.base import Feature

logger = logging.getLogger(__name__)

DEFAULT_BOT_CHAMPION_IDS = [86, 22, 11, 51, 89]  # Garen, Ashe, Master Yi, Caitlyn, Leona


class PracticeTool5v5(Feature):
    key = "practice_tool"
    title = "Practice Tool 5v5"
    category = "Automation"

    def get_status(self) -> dict:
        return {"key": self.key}

    def create_lobby(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        # Delete any existing lobby first
        try:
            self.lcu.lcu_request("DELETE", "/lol-lobby/v2/lobby")
            time.sleep(0.5)
        except Exception:
            pass

        lobby_payload = {
            "customGameLobby": {
                "configuration": {
                    "gameMode": "PRACTICETOOL",
                    "gameMutator": "",
                    "gameServerRegion": "",
                    "gameTypeConfig": {"id": 1},
                    "mapId": 11,
                    "mutators": {"id": 1},
                    "spectatorPolicy": "AllAllowed",
                    "teamSize": 5,
                },
                "lobbyName": "Practice Tool 5v5",
                "lobbyPassword": "",
            },
            "isCustom": True,
        }

        res = self.lcu.lcu_request("POST", "/lol-lobby/v2/lobby", lobby_payload)
        if res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not create practice tool lobby (HTTP {res.status_code})")

        time.sleep(1.0)

        # Add 5 bots to enemy team (team 200)
        bots_added = 0
        for champ_id in DEFAULT_BOT_CHAMPION_IDS:
            bot_payload = {
                "botDifficulty": "MEDIUM",
                "championId": champ_id,
                "teamId": "200",
            }
            bot_res = self.lcu.lcu_request("POST", "/lol-lobby/v1/lobby/custom/bots", bot_payload)
            if bot_res.status_code in (200, 201, 204):
                bots_added += 1
            time.sleep(0.15)

        self.on_event("success", f"Practice Tool 5v5 created with {bots_added} bot(s)")
        return {"bots_added": bots_added}
