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

                # Always sync to exactly what this lobby has now - including
                # empty, when the lobby is solo. Only updating on a non-empty
                # result meant a duo's party ids survived into a later solo
                # lobby forever, so a random future teammate who happened to
                # share one of those stale ids would be auto-honored as if
                # they were still the duo partner. A non-200 (e.g. the lobby
                # endpoint not existing mid-game) still intentionally leaves
                # the last-known lobby's members in place, since that is the
                # data the post-game ballot needs - see pick_honor_target.
                self.party_member_puuids = puuids
                self.party_member_summoner_ids = summoner_ids
        except Exception:
            logger.exception("AutoHonor._update_party_members failed")

    def pick_honor_target(self, eligible_players):
        """The duo/party member to honor, or None if none is eligible.

        Only votes when it's actually your duo/party — /lol-lobby/v2/lobby
        (where that's read from) only exists pre-game, so if the app wasn't
        running yet when the lobby formed, there's no way to know who that
        was. Guessing at a random teammate isn't what "auto" should mean
        here, so it skips the vote instead.

        Lives outside the loop so the choice can be tested without running a
        background thread.
        """
        for player in eligible_players:
            puuid = player.get("puuid")
            summoner_id = player.get("summonerId")
            if (puuid and puuid in self.party_member_puuids) or (
                summoner_id and summoner_id in self.party_member_summoner_ids
            ):
                return player

        return None

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
                        target_player = self.pick_honor_target(eligible_players)

                        if target_player is None:
                            # Mark this game as handled either way, so this
                            # doesn't re-log every 2s until the ballot closes.
                            self.last_honored_game_id = game_id
                            self.on_event(
                                "info", "Auto Honor: No known duo/party member was eligible, skipped voting"
                            )
                        else:
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
                                self.on_event("success", f"Auto Honor: Voted for duo partner ({target_name})")
                                self._sleep(2)
            except Exception:
                logger.exception("AutoHonor._loop failed")

            self._sleep(2)
