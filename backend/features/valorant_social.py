import logging
import time

from features.base import Feature

logger = logging.getLogger(__name__)


class ValorantChatToggle(Feature):
    """Suspends/resumes the Riot Client's chat session — the same
    `/chat/v1/*` endpoints features.social.ChatToggle uses for League, just
    reached through the VALORANT client's own lockfile instead of requiring
    League to be running too.
    """

    key = "valorant_chat_toggle"
    title = "Chat"
    category = "Valorant"
    game = "valorant"

    #: How long a read of the real chat state is reused; the UI polls every
    #: 4s and this costs a round trip to the Riot client, so it's throttled.
    STATE_TTL_SECONDS = 5.0

    def __init__(self, valorant_client, config, on_event=None):
        super().__init__(valorant_client, config, on_event)
        self.valorant = valorant_client
        self.disconnected = False
        self._state_read_at = 0.0

    def _refresh_if_stale(self):
        if time.monotonic() - self._state_read_at < self.STATE_TTL_SECONDS:
            return
        if not self.valorant.is_connected():
            return  # the client being closed is a normal state, not a failure
        try:
            response = self.valorant.local_request("GET", "/chat/v1/session")
            if response.status_code == 200:
                self.disconnected = response.json().get("state") == "disconnected"
                self._state_read_at = time.monotonic()
        except Exception:
            logger.exception("ValorantChatToggle._refresh_if_stale failed")

    def get_status(self) -> dict:
        self._refresh_if_stale()
        return {"key": self.key, "disconnected": self.disconnected}

    def toggle(self):
        if self.disconnected:
            response = self.valorant.local_request("POST", "/chat/v1/resume")
            action = "reconnect"
        else:
            response = self.valorant.local_request("POST", "/chat/v1/suspend", {"config": "disable"})
            action = "disconnect"

        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not {action} chat (HTTP {response.status_code})")

        self.disconnected = not self.disconnected
        self._state_read_at = time.monotonic()
        self.on_event("info", f"Chat {'disconnected' if self.disconnected else 'reconnected'}")
        return self.disconnected
