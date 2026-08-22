import logging
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class AramBenchSwap(ThreadedFeature):
    key = "aram_bench_swap"
    title = "Aram"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.champ_dict = {}
        cfg = self.config.get("aram_bench_swap", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.champions = list(cfg.get("champions", []))

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "target_champion": list(self.champions),
        }

    def _save_settings(self):
        self.config.setdefault("aram_bench_swap", {})["enabled"] = self.enabled
        self.config["aram_bench_swap"]["champions"] = self.champions
        save_config(self.config)

    def toggle(self, state: bool = None) -> bool:
        new_state = (not self.enabled) if state is None else state
        self.enabled = new_state
        self._save_settings()
        self.on_event("info", f"Aram {'enabled' if new_state else 'disabled'}")
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
        except Exception:
            logger.exception("AramBenchSwap.update_champion_list failed")

    def champ_name_to_id(self, champ_name):
        if not self.champ_dict:
            self.update_champion_list()
        return self.champ_dict.get(champ_name.lower(), -1)

    def add_champion(self, champion_name):
        """Appends to the priority list (tried in order against the bench)."""
        champ_id = self.champ_name_to_id(champion_name)
        if champ_id == -1:
            raise ValueError(f"Champion '{champion_name}' was not found")

        normalized = champion_name.lower()
        if not any(existing.lower() == normalized for existing in self.champions):
            self.champions.append(champion_name)
        self.enabled = True

        self._save_settings()
        self.on_event("success", f"Aram: added {champion_name} to the priority list")
        return list(self.champions)

    def remove_champion(self, champion_name):
        normalized = champion_name.lower()
        self.champions = [c for c in self.champions if c.lower() != normalized]
        if not self.champions:
            self.enabled = False

        self._save_settings()
        self.on_event("info", f"Aram: removed {champion_name} from the priority list")
        return list(self.champions)

    def resolve_champion(self, bench):
        """First champion in the priority list that's currently on the
        shared bench — so if your top pick isn't there yet, the next one in
        line is swapped to instead.
        """
        bench_ids = {b.get("championId") for b in bench}
        for name in self.champions:
            champ_id = self.champ_name_to_id(name)
            if champ_id != -1 and champ_id in bench_ids:
                return name
        return None

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                self._sleep(1)
                continue

            if not self.enabled or not self.champions:
                self._sleep(1)
                continue

            try:
                session_res = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if session_res.status_code == 200:
                    session = session_res.json()
                    bench = session.get("benchChampions", [])

                    champion_name = self.resolve_champion(bench)
                    if champion_name is not None:
                        champ_id = self.champ_name_to_id(champion_name)
                        swap_res = self.lcu.lcu_request(
                            "POST",
                            f"/lol-champ-select/v1/session/bench/swap/{champ_id}",
                        )
                        if swap_res.status_code in (200, 201, 204):
                            self.on_event("success", f"Aram: Swapped to {champion_name}!")
                            self._sleep(2.0)
            except Exception:
                logger.exception("AramBenchSwap._loop failed")

            self._sleep(0.5)
