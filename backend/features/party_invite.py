import logging
import time
from core.config import save_config
from features.base import Feature

logger = logging.getLogger(__name__)


class AutoPartyInvite(Feature):
    key = "auto_party_invite"
    title = "Auto Party Invite"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        cfg = self.config.get("auto_party_invite", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.summoners = cfg.get("summoners", "")
        self.last_invited_lobby_id = None

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "summoners": self.summoners or "None",
        }

    def _save_settings(self):
        self.config.setdefault("auto_party_invite", {})["enabled"] = self.enabled
        self.config["auto_party_invite"]["summoners"] = self.summoners
        save_config(self.config)

    def toggle(self, state: bool = None) -> bool:
        new_state = (not self.enabled) if state is None else state
        self.enabled = new_state
        self._save_settings()
        self.on_event("info", f"Auto Party Invite {'enabled' if new_state else 'disabled'}")
        return new_state

    def set_summoners(self, summoners: str):
        self.summoners = summoners.strip()
        self.enabled = bool(self.summoners)
        self._save_settings()
        self.on_event("success", f"Party invite list updated")
        return self.summoners

    def invite_now(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        if not self.summoners:
            raise ValueError("No summoners configured in party invite list")

        names = [n.strip() for n in self.summoners.split(",") if n.strip()]
        if not names:
            raise ValueError("No valid summoner names found")

        # Resolve summoner IDs
        invitations = []
        for name in names:
            # Check by summoner name or puuid
            try:
                res = self.lcu.lcu_request("GET", f"/lol-summoner/v1/summoners?name={name}")
                if res.status_code == 200:
                    data = res.json()
                    s_id = data.get("summonerId")
                    if s_id:
                        invitations.append({"toSummonerId": s_id})
            except Exception:
                pass

        if not invitations:
            # Fallback to direct invitation format
            invitations = [{"toSummonerName": n} for n in names]

        res = self.lcu.lcu_request("POST", "/lol-lobby/v2/lobby/invitations", invitations)
        if res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not send party invitations (HTTP {res.status_code})")

        self.on_event("success", f"Invited {len(names)} friend(s) to lobby")
        return {"invited": len(names)}

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                time.sleep(2)
                continue

            if not self.enabled or not self.summoners:
                time.sleep(2)
                continue

            try:
                res = self.lcu.lcu_request("GET", "/lol-lobby/v2/lobby")
                if res.status_code == 200:
                    lobby = res.json()
                    party_id = lobby.get("partyId")
                    is_leader = lobby.get("localMember", {}).get("isLeader", False)

                    if is_leader and party_id and party_id != self.last_invited_lobby_id:
                        self.last_invited_lobby_id = party_id
                        time.sleep(1.0)
                        self.invite_now()
                else:
                    self.last_invited_lobby_id = None
            except Exception as e:
                logger.debug(f"AutoPartyInvite loop error: {e}")

            time.sleep(2)
