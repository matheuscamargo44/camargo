import logging
import random
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class RandomSkinPicker(ThreadedFeature):
    key = "random_skin"
    title = "Random Skin Picker"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.enabled = bool(self.config.get("random_skin", {}).get("enabled", False))
        self.last_randomized_session = None

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
        }

    def toggle(self, state: bool = None) -> bool:
        new_state = (not self.enabled) if state is None else state
        self.enabled = new_state
        self.config.setdefault("random_skin", {})["enabled"] = self.enabled
        save_config(self.config)
        self.on_event("info", f"Random Skin Picker {'enabled' if new_state else 'disabled'}")
        return new_state

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                self._sleep(2)
                continue

            if not self.enabled:
                self._sleep(2)
                continue

            try:
                res = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if res.status_code == 200:
                    session = res.json()
                    local_cell_id = session.get("localPlayerCellId")
                    game_id = session.get("gameId") or session.get("chatDetails", {}).get("chatRoomName")

                    # Find my player entry
                    my_entry = None
                    for player in session.get("myTeam", []):
                        if player.get("cellId") == local_cell_id:
                            my_entry = player
                            break

                    if my_entry and game_id != self.last_randomized_session:
                        champ_id = my_entry.get("championId", 0)
                        # Check if locked in (champ_id > 0 and pick phase completed for local player)
                        if champ_id > 0:
                            # Fetch pickable skins
                            skins_res = self.lcu.lcu_request("GET", "/lol-champ-select/v1/pickable-skins")
                            if skins_res.status_code == 200:
                                skins_data = skins_res.json()
                                # skins_data is either a list or dict with pickableSkinIds / skins
                                pickable_ids = []
                                if isinstance(skins_data, list):
                                    pickable_ids = [s.get("id") for s in skins_data if s.get("id")]
                                elif isinstance(skins_data, dict):
                                    pickable_ids = skins_data.get("pickableSkinIds", [])

                                if pickable_ids:
                                    chosen_skin_id = random.choice(pickable_ids)
                                    patch_res = self.lcu.lcu_request(
                                        "PATCH",
                                        "/lol-champ-select/v1/session/my-selection",
                                        {"selectedSkinId": chosen_skin_id},
                                    )
                                    if patch_res.status_code in (200, 201, 204):
                                        self.last_randomized_session = game_id
                                        self.on_event("success", f"Random Skin Picker: Selected skin ID {chosen_skin_id}")
                                        self._sleep(2.0)
                else:
                    self.last_randomized_session = None
            except Exception:
                logger.exception("RandomSkinPicker._loop failed")

            self._sleep(1.0)
