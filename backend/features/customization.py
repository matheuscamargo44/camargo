"""Stateless customization actions: profile icon, client icon, background,
badges, Riot ID and status message. Grouped in one module since each is a
single LCU call with no monitoring loop, unlike the automation features.
"""
from features.base import Feature

BADGE_MODES = {"empty", "copy", "glitched"}


class ProfileIcon(Feature):
    key = "profile_icon"
    title = "Profile Icon"
    category = "Customization"

    def get_status(self) -> dict:
        icon_id = None
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-summoner/v1/current-summoner")
                if res.status_code == 200:
                    icon_id = res.json().get("profileIconId")
            except Exception:
                pass
        return {"key": self.key, "icon_id": icon_id}

    def change(self, icon_id):
        icon_id = int(icon_id)
        if icon_id < 1:
            raise ValueError("Icon ID must be a positive number")

        response = self.lcu.lcu_request(
            "PUT", "/lol-summoner/v1/current-summoner/icon", {"profileIconId": icon_id}
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Could not change profile icon (HTTP {response.status_code})")
        self.on_event("success", f"Profile icon changed to {icon_id}")
        return icon_id


class ClientIcon(Feature):
    key = "client_icon"
    title = "Client Icon"
    category = "Customization"

    def get_status(self) -> dict:
        icon_id = None
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-chat/v1/me")
                if res.status_code == 200:
                    icon_id = res.json().get("icon")
            except Exception:
                pass
        return {"key": self.key, "icon_id": icon_id}

    def change(self, icon_id):
        icon_id = int(icon_id)
        if icon_id < 1:
            raise ValueError("Icon ID must be a positive number")

        response = self.lcu.lcu_request("PUT", "/lol-chat/v1/me", {"icon": icon_id})
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Could not change client icon (HTTP {response.status_code})")
        self.on_event("success", f"Client icon changed to {icon_id}")
        return icon_id


class Background(Feature):
    key = "background"
    title = "Profile Background"
    category = "Customization"

    def get_status(self) -> dict:
        skin_id = None
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-summoner/v1/current-summoner/summoner-profile")
                if res.status_code == 200:
                    skin_id = res.json().get("backgroundSkinId")
            except Exception:
                pass
        return {"key": self.key, "skin_id": skin_id}

    def change(self, skin_id):
        skin_id = int(skin_id)
        response = self.lcu.lcu_request(
            "POST",
            "/lol-summoner/v1/current-summoner/summoner-profile",
            {"key": "backgroundSkinId", "value": skin_id},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Could not change profile background (HTTP {response.status_code})")
        self.on_event("success", f"Profile background changed to skin {skin_id}")
        return skin_id


class Badges(Feature):
    key = "badges"
    title = "Profile Badges"
    category = "Customization"

    def get_status(self) -> dict:
        return {"key": self.key}

    def _get_player_data(self):
        response = self.lcu.lcu_request("GET", "/lol-challenges/v1/summary-player-data/local-player")
        if response.status_code != 200:
            raise RuntimeError(f"Could not read profile badges (HTTP {response.status_code})")
        return response.json()

    def change(self, mode, glitched_id=None):
        if mode not in BADGE_MODES:
            raise ValueError("Unknown badge mode")

        data = self._get_player_data()
        top_challenges = data.get("topChallenges", [])

        if mode == "empty":
            challenge_ids = []
        elif mode == "copy":
            if not top_challenges:
                raise ValueError("There are no badges to copy")
            challenge_ids = [int(top_challenges[0]["id"])] * 3
        else:
            glitched_id = int(glitched_id)
            if not 0 <= glitched_id <= 5:
                raise ValueError("Glitched badge ID must be between 0 and 5")
            challenge_ids = [glitched_id] * 3

        payload = {"challengeIds": challenge_ids}
        title_id = data.get("title", {}).get("itemId", -1)
        banner_id = data.get("bannerId", "")
        if title_id != -1:
            payload["title"] = str(title_id)
        if banner_id:
            payload["bannerAccent"] = banner_id

        response = self.lcu.lcu_request("POST", "/lol-challenges/v1/update-player-preferences/", payload)
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not update profile badges (HTTP {response.status_code})")
        self.on_event("success", f"Profile badges updated ({mode})")
        return challenge_ids


class StatusMessage(Feature):
    key = "status_message"
    title = "Status Message"
    category = "Customization"

    def get_status(self) -> dict:
        return {"key": self.key}

    def change(self, status):
        response = self.lcu.lcu_request("PUT", "/lol-chat/v1/me", {"statusMessage": status})
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not change status message (HTTP {response.status_code})")
        self.on_event("success", "Status message updated")
        return status
