import threading
import time

from core.config import get_automation_delay, save_config
from features.base import Feature


class AutoBan(Feature):
    key = "autoban"
    title = "AutoBan"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.champ_dict = {}
        self.enabled = bool(self.config.get("autoban", {}).get("enabled"))
        self.champion = self.config.get("autoban", {}).get("champion", "None")
        self._thread = None
        self._running = False

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "autoban_champion": self.champion,
        }

    def _save_settings(self):
        if "autoban" not in self.config:
            self.config["autoban"] = {}
        self.config["autoban"]["enabled"] = self.enabled
        self.config["autoban"]["champion"] = self.champion
        save_config(self.config)

    def update_champion_list(self):
        response = self.lcu.lcu_request("GET", "/lol-game-data/assets/v1/champion-summary.json")
        if response.status_code != 200:
            raise RuntimeError(f"Could not fetch champion data (HTTP {response.status_code})")

        for champ in response.json():
            champ_id = champ["id"]
            champ_name = champ["name"]
            if champ_id > 0:
                normalized_name = champ_name.lower()
                current_id = self.champ_dict.get(normalized_name)
                if current_id is None or champ_id < current_id:
                    self.champ_dict[normalized_name] = champ_id
        return sorted(self.champ_dict)

    def champ_name_to_id(self, champ_name):
        return self.champ_dict.get(champ_name.lower(), -1)

    def set_champion(self, champion_name):
        if champion_name.lower() == "none":
            self.champion = "None"
            self.enabled = False
        else:
            if not self.champ_dict:
                self.update_champion_list()
            if self.champ_name_to_id(champion_name) == -1:
                raise ValueError(f"Champion '{champion_name}' was not found")
            self.champion = champion_name
            self.enabled = True
        self._save_settings()
        self.on_event("success", f"AutoBan configured for {self.champion}")
        return self.champion

    def toggle(self, enable=None):
        if enable is None:
            self.enabled = not self.enabled
        else:
            self.enabled = bool(enable)
        self._save_settings()
        self.on_event("info", f"AutoBan {'enabled' if self.enabled else 'disabled'}")
        return self.enabled

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_champ_select, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _monitor_champ_select(self):
        while self._running:
            try:
                if not self.enabled:
                    time.sleep(0.5)
                    continue
                if not self.lcu.is_league_connected():
                    time.sleep(2)
                    continue
                if not self.champ_dict:
                    self.update_champion_list()

                champ_select_resp = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if "RPC_ERROR" in champ_select_resp.text:
                    time.sleep(0.3)
                    continue

                session = champ_select_resp.json()
                cell_id = session.get("localPlayerCellId")
                if cell_id is None:
                    time.sleep(0.3)
                    continue

                for actions in session.get("actions", []):
                    if not isinstance(actions, list):
                        continue
                    for action in actions:
                        if (
                            self.enabled
                            and action.get("actorCellId") == cell_id
                            and action.get("type") == "ban"
                            and not action.get("completed")
                        ):
                            self._ban_champion(action)

                time.sleep(0.3)
            except Exception:
                time.sleep(1)

    def _ban_champion(self, action):
        if self.champion == "None":
            return
        delay = get_automation_delay(self.config, "autoban", 0.3)
        if delay:
            time.sleep(delay)

        champion_id = self.champ_name_to_id(self.champion)
        if champion_id == -1:
            return

        response = self.lcu.lcu_request(
            "PATCH",
            f"/lol-champ-select/v1/session/actions/{action['id']}",
            {"completed": True, "championId": champion_id},
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not ban champion (HTTP {response.status_code})")
        self.on_event("success", f"Banned {self.champion}")
