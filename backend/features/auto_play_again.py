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
        #: Set once play-again is actually POSTed for a given end-of-game
        #: sequence. Distinct from last_handled_phase: the gameflow sequence
        #: is WaitingForStats -> EndOfGame, both of which are handled here,
        #: and last_handled_phase alone re-fires on that second phase change
        #: even though the same end-of-game event was already acted on.
        self._play_again_sent = False

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
        except Exception:
            logger.exception("AutoPlayAgain.start_search failed")
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
                logger.exception("AutoPlayAgain.toggle failed")

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
                    self._handle_phase(res.json())
            except Exception:
                logger.exception("AutoPlayAgain._loop failed")

            self._sleep(2)

    def _handle_phase(self, phase):
        """The gameflow-phase state machine, pulled out of `_loop()` so it's
        directly testable without a live client or the sleeps in between.
        """
        if phase in ("EndOfGame", "WaitingForStats"):
            if self.last_handled_phase != phase and not self._play_again_sent:
                self.last_handled_phase = phase
                self._sleep(1.0)
                play_again_res = self.lcu.lcu_request("POST", "/lol-lobby/v2/play-again")
                if play_again_res.status_code in (200, 201, 204):
                    self._play_again_sent = True
                    self.on_event("success", "Play Again: Returned to lobby")
                    self.pending_play_again_search = True
            else:
                self.last_handled_phase = phase
        elif phase == "Lobby":
            self.last_handled_phase = "Lobby"
            self._play_again_sent = False
            if self.pending_play_again_search:
                self.pending_play_again_search = False
                self._sleep(1.0)
                self.start_search()
        elif phase in ("Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"):
            self.last_handled_phase = phase
            self._play_again_sent = False
            self.pending_play_again_search = False
