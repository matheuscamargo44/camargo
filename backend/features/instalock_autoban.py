import random
import threading
import time

from core.config import get_automation_delay, save_config
from features.base import Feature


class InstalockAutoban(Feature):
    key = "instalock_autoban"
    title = "Instalock / AutoBan"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.champ_dict = {}
        self.instalock_enabled = bool(self.config["instalock"].get("enabled"))
        self.instalock_champion = self.config["instalock"].get("champion", "None")
        self.auto_ban_enabled = bool(self.config["autoban"].get("enabled"))
        self.auto_ban_champion = self.config["autoban"].get("champion", "None")
        self._thread = None
        self._running = False

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "instalock_enabled": self.instalock_enabled,
            "instalock_champion": self.instalock_champion,
            "autoban_enabled": self.auto_ban_enabled,
            "autoban_champion": self.auto_ban_champion,
        }

    def _save_settings(self):
        self.config["instalock"]["enabled"] = self.instalock_enabled
        self.config["instalock"]["champion"] = self.instalock_champion
        self.config["autoban"]["enabled"] = self.auto_ban_enabled
        self.config["autoban"]["champion"] = self.auto_ban_champion
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

    def set_instalock_champion(self, champion_name):
        if champion_name.lower() == "none":
            self.instalock_champion = "None"
            self.instalock_enabled = False
        else:
            if not self.champ_dict:
                self.update_champion_list()
            if self.champ_name_to_id(champion_name) == -1:
                raise ValueError(f"Champion '{champion_name}' was not found")
            self.instalock_champion = champion_name
            self.instalock_enabled = True
        self._save_settings()
        self.on_event("success", f"Instalock configured for {self.instalock_champion}")
        return self.instalock_champion

    def set_auto_ban_champion(self, champion_name):
        if champion_name.lower() == "none":
            self.auto_ban_champion = "None"
            self.auto_ban_enabled = False
        else:
            if not self.champ_dict:
                self.update_champion_list()
            if self.champ_name_to_id(champion_name) == -1:
                raise ValueError(f"Champion '{champion_name}' was not found")
            self.auto_ban_champion = champion_name
            self.auto_ban_enabled = True
        self._save_settings()
        self.on_event("success", f"AutoBan configured for {self.auto_ban_champion}")
        return self.auto_ban_champion

    def toggle_instalock(self):
        self.instalock_enabled = not self.instalock_enabled
        self._save_settings()
        self.on_event("info", f"Instalock {'enabled' if self.instalock_enabled else 'disabled'}")
        return self.instalock_enabled

    def toggle_auto_ban(self):
        self.auto_ban_enabled = not self.auto_ban_enabled
        self._save_settings()
        self.on_event("info", f"AutoBan {'enabled' if self.auto_ban_enabled else 'disabled'}")
        return self.auto_ban_enabled

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
                if not self.instalock_enabled and not self.auto_ban_enabled:
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

                for actions in session["actions"]:
                    if not isinstance(actions, list):
                        continue
                    for action in actions:
                        if (
                            self.instalock_enabled
                            and action["actorCellId"] == cell_id
                            and action["type"] == "pick"
                            and not action["completed"]
                        ):
                            self._lock_champion(action)
                        elif (
                            self.auto_ban_enabled
                            and action["actorCellId"] == cell_id
                            and action["type"] == "ban"
                            and not action["completed"]
                        ):
                            self._ban_champion(action)

                time.sleep(0.3)
            except Exception:
                time.sleep(1)

    def _lock_champion(self, action):
        if self.instalock_champion == "None":
            return
        delay = get_automation_delay(self.config, "instalock", 0.3)
        if delay:
            time.sleep(delay)

        champion_id = self.champ_name_to_id(self.instalock_champion)
        if champion_id == -1:
            return

        response = self.lcu.lcu_request(
            "PATCH",
            f"/lol-champ-select/v1/session/actions/{action['id']}",
            {"completed": True, "championId": champion_id},
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not lock champion (HTTP {response.status_code})")
        self.on_event("success", f"Locked {self.instalock_champion}")
        time.sleep(0.3)

    def _ban_champion(self, action):
        if self.auto_ban_champion == "None":
            return
        delay = get_automation_delay(self.config, "autoban", 0.3)
        if delay:
            time.sleep(delay)

        champion_id = self.champ_name_to_id(self.auto_ban_champion)
        if champion_id == -1:
            return

        response = self.lcu.lcu_request(
            "PATCH",
            f"/lol-champ-select/v1/session/actions/{action['id']}",
            {"completed": True, "championId": champion_id},
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not ban champion (HTTP {response.status_code})")
        self.on_event("success", f"Banned {self.auto_ban_champion}")
