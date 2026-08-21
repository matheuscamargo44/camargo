import logging
import time
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class AutoPlayAgain(ThreadedFeature):
    key = "auto_play_again"
    title = "Play Again"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.last_handled_phase = None
        self.last_search_attempt = 0
        self.pending_play_again_search = False

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.config.get("auto_play_again", {}).get("enabled", False),
        }

    def start_search(self) -> bool:
        if not self.lcu.is_league_connected():
            return False

        now = time.time()
        if now - self.last_search_attempt < 3.0:
            return False

        self.last_search_attempt = now
        try:
            search_res = self.lcu.lcu_request("POST", "/lol-lobby/v2/lobby/matchmaking/search")
            if search_res.status_code in (200, 201, 204):
                self.on_event("success", "Play Again: Matchmaking started")
                return True
        except Exception as e:
            logger.debug(f"Search error: {e}")
        return False

    def toggle(self, state: bool = None) -> bool:
        current = self.config.get("auto_play_again", {}).get("enabled", False)
        new_state = (not current) if state is None else state
        self.config.setdefault("auto_play_again", {})["enabled"] = new_state
        save_config(self.config)
        self.on_event("info", f"Play Again {'enabled' if new_state else 'disabled'}")

        if new_state:
            # If already in lobby, trigger search once immediately
            try:
                phase_res = self.lcu.lcu_request("GET", "/lol-gameflow/v1/gameflow-phase")
                if phase_res.status_code == 200 and phase_res.json() == "Lobby":
                    self.start_search()
            except Exception:
                pass

        return new_state

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                self._sleep(2)
                continue

            if not self.config.get("auto_play_again", {}).get("enabled", False):
                self._sleep(2)
                continue

            try:
                res = self.lcu.lcu_request("GET", "/lol-gameflow/v1/gameflow-phase")
                if res.status_code == 200:
                    phase = res.json()

                    if phase in ("EndOfGame", "WaitingForStats"):
                        if self.last_handled_phase != phase:
                            self.last_handled_phase = phase
                            self._sleep(1.0)
                            play_again_res = self.lcu.lcu_request("POST", "/lol-lobby/v2/play-again")
                            if play_again_res.status_code in (200, 201, 204):
                                self.on_event("success", "Play Again: Returned to lobby")
                                self.pending_play_again_search = True
                    elif phase == "Lobby":
                        self.last_handled_phase = "Lobby"
                        if self.pending_play_again_search:
                            self.pending_play_again_search = False
                            self._sleep(1.0)
                            self.start_search()
                    elif phase in ("Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"):
                        self.last_handled_phase = phase
                        self.pending_play_again_search = False
            except Exception as e:
                logger.debug(f"PlayAgain loop error: {e}")

            self._sleep(2)
