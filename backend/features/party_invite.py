import logging
from urllib.parse import quote
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class AutoPartyInvite(ThreadedFeature):
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
        self.on_event("success", "Party invite list updated")
        return self.summoners

    def _get_friends_lookup(self):
        lookup = {}
        try:
            res = self.lcu.lcu_request("GET", "/lol-chat/v1/friends")
            if res.status_code == 200:
                for f in res.json():
                    g_name = f.get("gameName", "")
                    g_tag = f.get("gameTag", "")
                    name = f.get("name", "")
                    s_id = f.get("summonerId")
                    puuid = f.get("puuid")

                    if g_name and g_tag:
                        lookup[f"{g_name}#{g_tag}".lower()] = (s_id, puuid)
                    if g_name:
                        lookup[g_name.lower()] = (s_id, puuid)
                    if name:
                        lookup[name.lower()] = (s_id, puuid)
        except Exception:
            logger.exception("AutoPartyInvite._get_friends_lookup failed")
        return lookup

    def invite_now(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        if not self.summoners:
            raise ValueError("No summoners configured in party invite list")

        names = [n.strip() for n in self.summoners.split(",") if n.strip()]
        if not names:
            raise ValueError("No valid summoner names found")

        friends_map = self._get_friends_lookup()
        invitations = []

        for name in names:
            name_lower = name.lower()
            if name_lower in friends_map:
                s_id, puuid = friends_map[name_lower]
                if s_id:
                    invitations.append({"toSummonerId": s_id})
                elif puuid:
                    invitations.append({"toPuuid": puuid})
                continue

            # If not found in friends, try resolving by summoner API
            resolved = False
            try:
                # Riot IDs contain spaces and '#', which would truncate the URL
                res = self.lcu.lcu_request(
                    "GET", f"/lol-summoner/v1/summoners?name={quote(name, safe='')}"
                )
                if res.status_code == 200:
                    data = res.json()
                    s_id = data.get("summonerId")
                    puuid = data.get("puuid")
                    if s_id:
                        invitations.append({"toSummonerId": s_id})
                        resolved = True
                    elif puuid:
                        invitations.append({"toPuuid": puuid})
                        resolved = True
            except Exception:
                logger.exception("AutoPartyInvite.invite_now failed")

            if not resolved:
                invitations.append({"toSummonerName": name})

        res = self.lcu.lcu_request("POST", "/lol-lobby/v2/lobby/invitations", invitations)
        if res.status_code not in (200, 201, 204):
            raise RuntimeError(f"Could not send party invitations (HTTP {res.status_code})")

        self.on_event("success", f"Invited {len(names)} friend(s) to lobby")
        return {"invited": len(names)}

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                self._sleep(2)
                continue

            if not self.enabled or not self.summoners:
                self._sleep(2)
                continue

            try:
                res = self.lcu.lcu_request("GET", "/lol-lobby/v2/lobby")
                if res.status_code == 200:
                    lobby = res.json()
                    party_id = lobby.get("partyId")
                    is_leader = lobby.get("localMember", {}).get("isLeader", False)

                    if is_leader and party_id and party_id != self.last_invited_lobby_id:
                        self.last_invited_lobby_id = party_id
                        self._sleep(1.0)
                        self.invite_now()
                else:
                    self.last_invited_lobby_id = None
            except Exception:
                logger.exception("AutoPartyInvite._loop failed")

            self._sleep(2)
