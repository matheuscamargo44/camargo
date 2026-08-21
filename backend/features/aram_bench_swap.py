import logging
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class AramBenchSwap(ThreadedFeature):
    key = "aram_bench_swap"
    title = "ARAM Bench Sniper"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.champ_dict = {}
        cfg = self.config.get("aram_bench_swap", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.target_champion = cfg.get("champion", "None")

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "target_champion": self.target_champion,
        }

    def _save_settings(self):
        self.config.setdefault("aram_bench_swap", {})["enabled"] = self.enabled
        self.config["aram_bench_swap"]["champion"] = self.target_champion
        save_config(self.config)

    def toggle(self, state: bool = None) -> bool:
        new_state = (not self.enabled) if state is None else state
        self.enabled = new_state
        self._save_settings()
        self.on_event("info", f"ARAM Bench Sniper {'enabled' if new_state else 'disabled'}")
        return new_state

    def update_champion_list(self):
        try:
            response = self.lcu.lcu_request("GET", "/lol-game-data/assets/v1/champion-summary.json")
            if response.status_code == 200:
                for champ in response.json():
                    champ_id = champ.get("id")
                    champ_name = champ.get("name")
                    if champ_id and champ_id > 0 and champ_name:
                        self.champ_dict[champ_name.lower()] = champ_id
        except Exception as e:
            logger.debug(f"Could not update champion list: {e}")

    def champ_name_to_id(self, champ_name):
        if not self.champ_dict:
            self.update_champion_list()
        return self.champ_dict.get(champ_name.lower(), -1)

    def set_champion(self, champion_name):
        if champion_name.lower() == "none":
            self.target_champion = "None"
            self.enabled = False
        else:
            if not self.champ_dict:
                self.update_champion_list()
            champ_id = self.champ_name_to_id(champion_name)
            if champ_id == -1:
                raise ValueError(f"Champion '{champion_name}' was not found")
            self.target_champion = champion_name
            self.enabled = True

        self._save_settings()
        self.on_event("success", f"ARAM Bench Sniper target set to {self.target_champion}")
        return self.target_champion

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                self._sleep(1)
                continue

            if not self.enabled or self.target_champion == "None":
                self._sleep(1)
                continue

            try:
                target_id = self.champ_name_to_id(self.target_champion)
                if target_id == -1:
                    self._sleep(1)
                    continue

                session_res = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if session_res.status_code == 200:
                    session = session_res.json()
                    bench = session.get("benchChampions", [])

                    # Check if target champion is currently in the bench
                    for b_champ in bench:
                        if b_champ.get("championId") == target_id:
                            # Attempt swap
                            swap_res = self.lcu.lcu_request(
                                "POST",
                                f"/lol-champ-select/v1/session/bench/swap/{target_id}",
                            )
                            if swap_res.status_code in (200, 201, 204):
                                self.on_event("success", f"ARAM Bench Sniper: Swapped to {self.target_champion}!")
                                self._sleep(2.0)
                            break
            except Exception as e:
                logger.debug(f"AramBenchSwap error: {e}")

            self._sleep(0.5)
