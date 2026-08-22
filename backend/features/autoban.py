from core.config import get_automation_delay, save_config
from features.base import ThreadedFeature


class AutoBan(ThreadedFeature):
    key = "autoban"
    title = "AutoBan"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.champ_dict = {}
        settings = self.config.get("autoban", {})
        self.enabled = bool(settings.get("enabled"))
        self.champions = list(settings.get("champions", []))

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "autoban_champion": list(self.champions),
        }

    def _save_settings(self):
        if "autoban" not in self.config:
            self.config["autoban"] = {}
        self.config["autoban"]["enabled"] = self.enabled
        self.config["autoban"]["champions"] = self.champions
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

    def add_champion(self, champion_name):
        """Appends to the priority list (tried in order at ban time)."""
        if not self.champ_dict:
            self.update_champion_list()
        if self.champ_name_to_id(champion_name) == -1:
            raise ValueError(f"Champion '{champion_name}' was not found")

        normalized = champion_name.lower()
        if not any(existing.lower() == normalized for existing in self.champions):
            self.champions.append(champion_name)
        self.enabled = True

        self._save_settings()
        self.on_event("success", f"AutoBan: added {champion_name} to the priority list")
        return list(self.champions)

    def remove_champion(self, champion_name):
        normalized = champion_name.lower()
        self.champions = [c for c in self.champions if c.lower() != normalized]
        if not self.champions:
            self.enabled = False

        self._save_settings()
        self.on_event("info", f"AutoBan: removed {champion_name} from the priority list")
        return list(self.champions)

    def toggle(self, enable=None):
        if enable is None:
            self.enabled = not self.enabled
        else:
            self.enabled = bool(enable)
        self._save_settings()
        self.on_event("info", f"AutoBan {'enabled' if self.enabled else 'disabled'}")
        return self.enabled

    def find_pending_action(self, session, cell_id):
        """The champ select action this feature should act on, if any.

        Champ select nests actions in phases; only the local player's own
        unfinished "ban" counts. Extracted from the loop so the
        matching can be tested without a live client.
        """
        if not self.enabled or cell_id is None:
            return None

        for phase in session.get("actions", []):
            if not isinstance(phase, list):
                continue
            for action in phase:
                if (
                    action.get("actorCellId") == cell_id
                    and action.get("type") == "ban"
                    and not action.get("completed")
                ):
                    return action
        return None

    def resolve_champion(self, session):
        """First champion in the priority list not already banned by either
        team — so a champion someone else already banned falls through to
        the next one instead of wasting the ban.
        """
        bans = session.get("bans") or {}
        unavailable_ids = set()
        for ban_list in (bans.get("myTeamBans"), bans.get("theirTeamBans")):
            for champ_id in ban_list or []:
                unavailable_ids.add(champ_id)

        for name in self.champions:
            champ_id = self.champ_name_to_id(name)
            if champ_id != -1 and champ_id not in unavailable_ids:
                return name
        return None

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                if not self.enabled:
                    self._sleep(0.5)
                    continue
                if not self.lcu.is_league_connected():
                    self._sleep(2)
                    continue
                if not self.champ_dict:
                    self.update_champion_list()

                champ_select_resp = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if "RPC_ERROR" in champ_select_resp.text:
                    self._sleep(0.3)
                    continue

                session = champ_select_resp.json()
                cell_id = session.get("localPlayerCellId")
                if cell_id is None:
                    self._sleep(0.3)
                    continue

                pending = self.find_pending_action(session, cell_id)
                if pending is not None:
                    champion_name = self.resolve_champion(session)
                    if champion_name is not None:
                        self._ban_champion(pending, champion_name)

                self._sleep(0.3)
            except Exception:
                self._sleep(1)

    def _ban_champion(self, action, champion_name):
        delay = get_automation_delay(self.config, "autoban", 0.3)
        if delay:
            self._sleep(delay)

        champion_id = self.champ_name_to_id(champion_name)
        if champion_id == -1:
            return

        response = self.lcu.lcu_request(
            "PATCH",
            f"/lol-champ-select/v1/session/actions/{action['id']}",
            {"completed": True, "championId": champion_id},
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not ban champion (HTTP {response.status_code})")
        self.on_event("success", f"Banned {champion_name}")
