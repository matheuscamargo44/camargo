"""Read-only competitive rank/RR + recent form. No monitoring loop — the
status is only as fresh as the next poll, same as League's rank badge.
"""
import logging

from features.base import Feature

logger = logging.getLogger(__name__)


class ValorantRank(Feature):
    key = "valorant_rank"
    title = "Rank"
    category = "Valorant"
    game = "valorant"

    def __init__(self, valorant_client, config, on_event=None):
        super().__init__(valorant_client, config, on_event)
        self.valorant = valorant_client

    def get_status(self) -> dict:
        if not self.valorant.is_connected():
            return {"key": self.key, "tier": None, "rr": None}

        try:
            mmr = self.valorant.fetch_mmr()
        except Exception:
            logger.exception("ValorantRank.get_status failed")
            return {"key": self.key, "tier": None, "rr": None}

        latest = (mmr or {}).get("LatestCompetitiveUpdate") or {}
        return {
            "key": self.key,
            "tier": latest.get("TierAfterUpdate"),
            "rr": latest.get("RankedRatingAfterUpdate"),
        }

    def get_recent_form(self, count=5) -> list:
        """Last `count` competitive games, most recent first.

        Only the raw RR delta is reported — not a derived win/loss label.
        RR can rise on a loss (derank protection) or fall on a win (a bad
        performance bonus), so guessing W/L from the sign would sometimes
        just be wrong; the RR change itself is not.
        """
        count = max(1, min(int(count), 20))
        updates = self.valorant.fetch_competitive_updates(start_index=0, end_index=count)
        matches = (updates or {}).get("Matches") or []
        return [
            {
                "match_id": match.get("MatchID"),
                "map_id": match.get("MapID"),
                "tier_after": match.get("TierAfterUpdate"),
                "rr_after": match.get("RankedRatingAfterUpdate"),
                "rr_change": match.get("RankedRatingEarned"),
            }
            for match in matches
        ]
