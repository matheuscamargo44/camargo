import logging
from features.base import Feature

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


class RankedPresence(Feature):
    key = "ranked_presence"
    title = "Ranked Presence"
    category = "Social"

    def get_status(self) -> dict:
        current_tier = "Default"
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-chat/v1/me")
                if res.status_code == 200:
                    data = res.json()
                    lol = data.get("lol", {})
                    current_tier = lol.get("rankedLeagueTier", "Default")
            except Exception as e:
                logger.debug(f"Could not fetch ranked presence: {e}")

        return {
            "key": self.key,
            "tier": current_tier.capitalize() if current_tier else "Default",
        }

    def set_tier(self, tier: str, division: str = "I"):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        tier_upper = tier.upper().strip()
        if tier_upper not in VALID_TIERS:
            raise ValueError(f"Invalid ranked tier '{tier}'. Expected one of: {', '.join(sorted(VALID_TIERS))}")

        payload = {
            "lol": {
                "rankedLeagueTier": tier_upper,
                "rankedLeagueDivision": division.upper().strip() if tier_upper not in ("MASTER", "GRANDMASTER", "CHALLENGER", "UNRANKED") else "I",
                "rankedLeagueQueue": "RANKED_SOLO_5x5",
            }
        }

        res = self.lcu.lcu_request("PUT", "/lol-chat/v1/me", payload)
        if res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not set ranked presence (HTTP {res.status_code})")

        self.on_event("success", f"Ranked presence set to {tier_upper}")
        return {"tier": tier_upper}
