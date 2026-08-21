import logging
from core.config import save_config
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class AutoHonor(ThreadedFeature):
    key = "auto_honor"
    title = "Auto Honor"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.last_honored_game_id = None
        self.party_member_puuids = set()
        self.party_member_summoner_ids = set()

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.config.get("auto_honor", {}).get("enabled", False),
        }

    def toggle(self, state: bool = None) -> bool:
        current = self.config.get("auto_honor", {}).get("enabled", False)
        new_state = (not current) if state is None else state
        self.config.setdefault("auto_honor", {})["enabled"] = new_state
        save_config(self.config)
        self.on_event("info", f"Auto Honor {'enabled' if new_state else 'disabled'}")
        return new_state

    def _update_party_members(self):
        try:
            lobby_res = self.lcu.lcu_request("GET", "/lol-lobby/v2/lobby")
            if lobby_res.status_code == 200:
                lobby = lobby_res.json()
                members = lobby.get("members", [])
                local_member = lobby.get("localMember", {})
                local_puuid = local_member.get("puuid")
                local_summoner_id = local_member.get("summonerId")

                puuids = set()
                summoner_ids = set()
                for m in members:
                    m_puuid = m.get("puuid")
                    m_summoner_id = m.get("summonerId")
                    if m_puuid and m_puuid != local_puuid:
                        puuids.add(m_puuid)
                    if m_summoner_id and m_summoner_id != local_summoner_id:
                        summoner_ids.add(m_summoner_id)

                if puuids or summoner_ids:
                    self.party_member_puuids = puuids
                    self.party_member_summoner_ids = summoner_ids
        except Exception:
            logger.exception("AutoHonor._update_party_members failed")

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.lcu.is_league_connected():
                self._sleep(2)
                continue

            # Track party/duo members when in lobby
            self._update_party_members()

            if not self.config.get("auto_honor", {}).get("enabled", False):
                self._sleep(2)
                continue

            try:
                ballot_res = self.lcu.lcu_request("GET", "/lol-honor-v2/v1/ballot")
                if ballot_res.status_code == 200:
                    ballot = ballot_res.json()
                    game_id = ballot.get("gameId")
                    eligible_players = (
                        ballot.get("eligibleAllies")
                        or ballot.get("eligiblePlayers")
                        or []
                    )

                    if eligible_players and game_id and game_id != self.last_honored_game_id:
                        # Prioritize duo / party member if present
                        target_player = None
                        is_duo = False

                        for p in eligible_players:
                            p_puuid = p.get("puuid")
                            p_summoner_id = p.get("summonerId")
                            if (p_puuid and p_puuid in self.party_member_puuids) or (
                                p_summoner_id and p_summoner_id in self.party_member_summoner_ids
                            ):
                                target_player = p
                                is_duo = True
                                break

                        if not target_player:
                            target_player = eligible_players[0]

                        summoner_id = target_player.get("summonerId")
                        puuid = target_player.get("puuid")
                        target_name = (
                            target_player.get("summonerName")
                            or target_player.get("gameName")
                            or target_player.get("championName")
                            or "Teammate"
                        )

                        payload = {
                            "honorType": "HEART",
                            "honorCategory": "HEART",
                            "summonerId": summoner_id,
                            "gameId": game_id,
                        }
                        if puuid:
                            payload["puuid"] = puuid

                        honor_res = self.lcu.lcu_request(
                            "POST",
                            "/lol-honor-v2/v1/honor-player",
                            payload,
                        )
                        if honor_res.status_code in (200, 201, 204):
                            self.last_honored_game_id = game_id
                            role_str = "duo partner" if is_duo else "teammate"
                            self.on_event("success", f"Auto Honor: Voted for {role_str} ({target_name})")
                            self._sleep(2)
            except Exception:
                logger.exception("AutoHonor._loop failed")

            self._sleep(2)
