import logging
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)

VALID_TIERS = {
    "CHALLENGER",
    "GRANDMASTER",
    "MASTER",
    "DIAMOND",
    "EMERALD",
    "PLATINUM",
    "GOLD",
    "SILVER",
    "BRONZE",
    "IRON",
    "UNRANKED",
}

#: The League client republishes the real ranked tier to /lol-chat/v1/me on
#: its own (e.g. whenever chat/presence resyncs), silently overwriting a
#: one-shot spoof within seconds to minutes. Reapplying periodically is the
#: only way the fake tier actually sticks instead of drifting back.
REAPPLY_INTERVAL_SECONDS = 15


class RankedPresence(ThreadedFeature):
    key = "ranked_presence"
    title = "Ranked Presence"
    category = "Social"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        section = self.config.get("ranked_presence", {})
        self.enabled = bool(section.get("enabled", False))
        self.tier = section.get("tier", "")
        self.division = section.get("division", "I")

    def get_status(self) -> dict:
        current_tier = "Default"
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-chat/v1/me")
                if res.status_code == 200:
                    data = res.json()
                    lol = data.get("lol", {})
                    current_tier = lol.get("rankedLeagueTier", "Default")
            except Exception:
                logger.exception("RankedPresence.get_status failed")

        return {
            "key": self.key,
            "enabled": self.enabled,
            "tier": current_tier.capitalize() if current_tier else "Default",
        }

    def _save_settings(self):
        self.config.setdefault("ranked_presence", {})
        self.config["ranked_presence"]["enabled"] = self.enabled
        self.config["ranked_presence"]["tier"] = self.tier
        self.config["ranked_presence"]["division"] = self.division
        save_config(self.config)

    def _apply(self):
        payload = {
            "lol": {
                "rankedLeagueTier": self.tier,
                "rankedLeagueDivision": self.division,
                "rankedLeagueQueue": "RANKED_SOLO_5x5",
            }
        }
        res = self.lcu.lcu_request("PUT", "/lol-chat/v1/me", payload)
        if res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not set ranked presence (HTTP {res.status_code})")

    def set_tier(self, tier: str, division: str = "I"):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        tier_upper = tier.upper().strip()
        if tier_upper not in VALID_TIERS:
            raise ValueError(f"Invalid ranked tier '{tier}'. Expected one of: {', '.join(sorted(VALID_TIERS))}")

        if tier_upper == "UNRANKED":
            # Not a spoofable value on its own - treat it as "stop faking a
            # rank", the same way the other automations treat "None".
            self.enabled = False
            self.tier = ""
            self.division = "I"
            self._save_settings()
            self.on_event("info", "Ranked presence disabled")
            return {"tier": "UNRANKED"}

        self.tier = tier_upper
        self.division = (
            division.upper().strip() if tier_upper not in ("MASTER", "GRANDMASTER", "CHALLENGER") else "I"
        )
        self.enabled = True
        self._save_settings()

        self._apply()
        self.on_event("success", f"Ranked presence set to {self.tier}")
        return {"tier": self.tier}

    def _loop(self):
        while not self._stop_event.is_set():
            if not (self.enabled and self.lcu.is_league_connected()):
                self._sleep(2)
                continue

            try:
                self._apply()
            except Exception:
                logger.exception("RankedPresence reapply failed")

            self._sleep(REAPPLY_INTERVAL_SECONDS)
