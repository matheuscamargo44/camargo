import logging
import time

from features.base import Feature

logger = logging.getLogger(__name__)


class RemoveFriends(Feature):
    key = "remove_friends"
    title = "Remove All Friends"
    category = "Social"

    def get_status(self) -> dict:
        return {"key": self.key}

    def get_friends(self):
        response = self.lcu.lcu_request("GET", "/lol-chat/v1/friends")
        if response.status_code != 200:
            raise RuntimeError(f"Could not fetch friends (HTTP {response.status_code})")
        return response.json() or []

    def remove_all(self):
        friends = self.get_friends()
        removed_count = 0
        failed_count = 0

        for friend in friends:
            friend_id = friend.get("pid")
            if not friend_id:
                failed_count += 1
                continue
            try:
                response = self.lcu.lcu_request("DELETE", f"/lol-chat/v1/friends/{friend_id}")
                if response.status_code in (200, 204):
                    removed_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1

        self.on_event("success", f"Removed {removed_count} friends ({failed_count} failed)")
        return removed_count, failed_count


class RestartUX(Feature):
    key = "restart_ux"
    title = "Restart Client UX"
    category = "Social"

    def get_status(self) -> dict:
        return {"key": self.key}

    def restart(self):
        response = self.lcu.lcu_request("POST", "/riotclient/kill-and-restart-ux")
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not restart Client UX (HTTP {response.status_code})")
        self.on_event("info", "Client UX restarted")


class ChatToggle(Feature):
    key = "chat_toggle"
    title = "Chat"
    category = "Social"

    #: How long a read of the real chat state is reused. The UI polls every
    #: 4s and this costs a round trip to the Riot client, so it is throttled.
    STATE_TTL_SECONDS = 5.0

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.disconnected = False
        self._state_read_at = 0.0

    def _refresh_if_stale(self):
        """Read the real state from the client.

        Without this the switch reported whatever the last toggle set, so
        opening the app with chat already disconnected showed "connected"
        until the user clicked once.
        """
        if time.monotonic() - self._state_read_at < self.STATE_TTL_SECONDS:
            return
        if not self.lcu.is_league_connected():
            return  # the client being closed is a normal state, not a failure
        try:
            response = self.lcu.riot_request("GET", "/chat/v1/session")
            if response.status_code == 200:
                self.disconnected = response.json().get("state") == "disconnected"
                self._state_read_at = time.monotonic()
        except Exception:
            logger.exception("ChatToggle._refresh_if_stale failed")

    def get_status(self) -> dict:
        self._refresh_if_stale()
        return {"key": self.key, "disconnected": self.disconnected}

    def toggle(self):
        if self.disconnected:
            response = self.lcu.riot_request("POST", "/chat/v1/resume")
            action = "reconnect"
        else:
            response = self.lcu.riot_request("POST", "/chat/v1/suspend", {"config": "disable"})
            action = "disconnect"

        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not {action} chat (HTTP {response.status_code})")

        self.disconnected = not self.disconnected
        self._state_read_at = time.monotonic()
        self.on_event("info", f"Chat {'disconnected' if self.disconnected else 'reconnected'}")
        return self.disconnected
