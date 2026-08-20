import logging
from features.base import Feature

logger = logging.getLogger(__name__)

VALID_AVAILABILITIES = {"mobile", "chat", "away", "dnd", "offline"}
AVAILABILITY_DISPLAY = {
    "chat": "Online",
    "mobile": "Mobile",
    "away": "Away",
    "dnd": "Do Not Disturb",
    "offline": "Offline",
}


class PresenceStatus(Feature):
    key = "presence_status"
    title = "Presence Status"
    category = "Social"

    def get_status(self) -> dict:
        availability = "chat"
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-chat/v1/me")
                if res.status_code == 200:
                    data = res.json()
                    availability = data.get("availability", "chat")
            except Exception as e:
                logger.debug(f"Could not fetch presence: {e}")

        return {
            "key": self.key,
            "availability": AVAILABILITY_DISPLAY.get(availability, "Online"),
        }

    def set_presence(self, availability: str):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        availability = availability.lower().strip()
        if availability not in VALID_AVAILABILITIES:
            raise ValueError(f"Invalid availability '{availability}'. Expected one of: {', '.join(VALID_AVAILABILITIES)}")

        res = self.lcu.lcu_request("PUT", "/lol-chat/v1/me", {"availability": availability})
        if res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not update presence (HTTP {res.status_code})")

        self.on_event("success", f"Presence status updated to {availability}")
        return availability
