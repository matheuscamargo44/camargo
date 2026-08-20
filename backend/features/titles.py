import logging
from features.base import Feature

logger = logging.getLogger(__name__)


class ChallengeTitles(Feature):
    key = "challenge_titles"
    title = "Challenge Titles"
    category = "Customization"

    def get_status(self) -> dict:
        current_title = "None"

        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-challenges/v1/summary-player-data/local-player")
                if res.status_code == 200:
                    data = res.json()
                    title_obj = data.get("title", {})
                    current_title = title_obj.get("name", "None") or "None"
            except Exception as e:
                logger.debug(f"Could not fetch challenge titles: {e}")

        return {
            "key": self.key,
            "current_title": current_title,
        }

    def get_titles(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        unlocked = []

        # 1. Try /lol-challenges/v2/titles/local-player
        try:
            res = self.lcu.lcu_request("GET", "/lol-challenges/v2/titles/local-player")
            if res.status_code == 200:
                titles = res.json()
                if isinstance(titles, list):
                    for t in titles:
                        t_id = t.get("itemId") or t.get("id")
                        t_name = t.get("name") or t.get("titleName")
                        t_desc = t.get("description", "")
                        if t_id and t_name:
                            unlocked.append({"id": t_id, "name": t_name, "desc": t_desc})
        except Exception:
            pass

        # 2. If empty, try /lol-challenges/v1/summary-player-data/local-player
        if not unlocked:
            try:
                res = self.lcu.lcu_request("GET", "/lol-challenges/v1/summary-player-data/local-player")
                if res.status_code == 200:
                    data = res.json()
                    titles = data.get("titles", []) or data.get("unlockedTitles", [])
                    for t in titles:
                        t_id = t.get("itemId") or t.get("id")
                        t_name = t.get("name")
                        t_desc = t.get("description", "")
                        if t_id and t_name:
                            unlocked.append({"id": t_id, "name": t_name, "desc": t_desc})
            except Exception:
                pass

        # 3. If still empty, try /lol-challenges/v1/titles
        if not unlocked:
            try:
                res = self.lcu.lcu_request("GET", "/lol-challenges/v1/titles")
                if res.status_code == 200:
                    titles = res.json()
                    if isinstance(titles, list):
                        for t in titles:
                            if t.get("isAcquired") or t.get("unlockedTimestamp", 0) > 0 or t.get("isUnlocked"):
                                t_id = t.get("itemId") or t.get("id")
                                t_name = t.get("name")
                                t_desc = t.get("description", "")
                                if t_id and t_name:
                                    unlocked.append({"id": t_id, "name": t_name, "desc": t_desc})
            except Exception:
                pass

        # Deduplicate and sort alphabetically
        seen = set()
        deduped = []
        for t in unlocked:
            if t["id"] not in seen:
                seen.add(t["id"])
                deduped.append(t)

        deduped.sort(key=lambda x: x["name"].lower())
        return deduped

    def set_title(self, title_id):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        # Fetch current player preferences
        res = self.lcu.lcu_request("GET", "/lol-challenges/v1/summary-player-data/local-player")
        if res.status_code != 200:
            raise RuntimeError(f"Could not read player data (HTTP {res.status_code})")

        data = res.json()
        payload = {}

        # Preserve existing banner and challengeIds
        challenge_ids = data.get("topChallenges", [])
        if challenge_ids:
            payload["challengeIds"] = [int(c.get("id")) for c in challenge_ids if c.get("id")]
        banner_id = data.get("bannerId", "")
        if banner_id:
            payload["bannerAccent"] = banner_id

        if str(title_id).lower() in ("-1", "none", "", "0"):
            payload["title"] = ""
            action_desc = "cleared"
        else:
            payload["title"] = str(title_id)
            action_desc = f"updated"

        update_res = self.lcu.lcu_request("POST", "/lol-challenges/v1/update-player-preferences/", payload)
        if update_res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not update title (HTTP {update_res.status_code})")

        self.on_event("success", f"Challenge title {action_desc}")
        return {"title_id": title_id}
