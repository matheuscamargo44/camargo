import logging
from core.config import get_automation_delay, save_config
from features.base import ThreadedFeature


logger = logging.getLogger(__name__)


class AutoAccept(ThreadedFeature):
    key = "auto_accept"
    title = "Auto Accept"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.enabled = bool(self.config["auto_accept"].get("enabled"))

    def get_status(self) -> dict:
        return {"key": self.key, "enabled": self.enabled}

    def toggle(self):
        self.enabled = not self.enabled
        self.config["auto_accept"]["enabled"] = self.enabled
        save_config(self.config)
        state = "enabled" if self.enabled else "disabled"
        self.on_event("info", f"Auto Accept {state}")
        return self.enabled

    def accept_match(self):
        response = self.lcu.lcu_request("POST", "/lol-matchmaking/v1/ready-check/accept")
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not accept match (HTTP {response.status_code})")
        self.on_event("success", "Match accepted")

    def _loop(self):
        while not self._stop_event.is_set():
            if self.enabled:
                if not self.lcu.is_league_connected():
                    self._sleep(2)
                    continue
                try:
                    response = self.lcu.lcu_request(
                        "GET", "/lol-lobby/v2/lobby/matchmaking/search-state"
                    )

                    if response.status_code == 200 and response.json().get("searchState") == "Found":
                        delay = get_automation_delay(self.config, "auto_accept", 0.0)
                        if delay:
                            self._sleep(delay)
                        self.accept_match()
                except Exception:
                    logger.exception("AutoAccept._loop failed")

            self._sleep(0.5)
