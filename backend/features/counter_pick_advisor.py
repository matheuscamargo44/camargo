"""Shows who beats the enemy laner, for the player to decide with.

Deliberately advisory, not automatic: Instalock's `smart_counter_pick`
already *acts* on matchup data by reordering the priority list, and this
does the opposite - it always shows the answer and never picks anything.

Scoped to one lane on purpose. OP.GG's counter data is per-lane matchup
data and does not compose across roles: checked live, Darius (top) is
beaten by Jayce/Camille/Ambessa, Viego (jungle) by Nidalee/Kayn/Naafiri -
every list is same-role. Scoring candidates by "how many of the enemy team
they counter" therefore gives every candidate exactly 1, which is noise
dressed as a ranking. The enemy laner is the only opponent this data
actually speaks to, so it is the only one used.

Cost is why it is cached per matchup and only ever asked once: a live
`lol_get_champion_analysis` call measures ~3s, against a pick window of
roughly 30s.
"""
import logging

from core.config import save_config
from core.opgg_client import opgg_client
from features.base import ThreadedFeature
from features.instalock import POSITION_MAP

logger = logging.getLogger(__name__)

#: OP.GG returns at most 3 counters per champion; kept as a named cap so
#: the UI and the tests agree on what "all of them" means.
MAX_COUNTERS_SHOWN = 3

#: The pick window is short and the lookup is ~3s, so a slow poll would
#: waste most of it. Cheap: it only reads champ select, and the OP.GG call
#: behind it happens once per matchup thanks to _cache.
POLL_SECONDS = 1.0


class CounterPickAdvisor(ThreadedFeature):
    key = "counter_pick_advisor"
    title = "Counter Picks"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self._champ_id_to_name = {}
        self._cache = {}
        self._reset()

    def _reset(self):
        self._recommendation = None
        self._last_matchup = None

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.config.get("counter_pick_advisor", {}).get("enabled", False),
            "recommendation": self._recommendation,
        }

    def toggle(self, state: bool = None) -> bool:
        current = self.config.get("counter_pick_advisor", {}).get("enabled", False)
        new_state = (not current) if state is None else state
        self.config.setdefault("counter_pick_advisor", {})["enabled"] = new_state
        save_config(self.config)
        self.on_event("info", f"Counter Picks {'enabled' if new_state else 'disabled'}")
        return new_state

    # -- champion list, same source Instalock builds champ_dict from --

    def _ensure_champion_list(self):
        if self._champ_id_to_name:
            return
        try:
            response = self.lcu.lcu_request("GET", "/lol-game-data/assets/v1/champion-summary.json")
            if response.status_code != 200:
                return
            for champ in response.json():
                if champ["id"] > 0:
                    self._champ_id_to_name[champ["id"]] = champ["name"]
        except Exception:
            logger.exception("CounterPickAdvisor: failed to load champion list")

    # -- reading champ select --

    @staticmethod
    def _my_position(session, cell_id):
        for player in session.get("myTeam") or []:
            if player.get("cellId") == cell_id:
                return POSITION_MAP.get(player.get("assignedPosition"))
        return None

    @staticmethod
    def _enemy_in_my_lane(session, position):
        """The enemy assigned to the same lane. Blind pick and ARAM have no
        `assignedPosition` at all, so this correctly finds nobody there
        rather than guessing from pick order."""
        for player in session.get("theirTeam") or []:
            if POSITION_MAP.get(player.get("assignedPosition")) != position:
                continue
            champion_id = player.get("championId") or 0
            return champion_id if champion_id > 0 else None
        return None

    def _counters_for(self, enemy_name, position):
        cached = self._cache.get((enemy_name, position))
        if cached is not None:
            return cached
        try:
            data = opgg_client.get_champion_counters(enemy_name, position)
        except Exception:
            logger.exception("CounterPickAdvisor: OP.GG counter lookup failed")
            # Not cached: a network blip on the first pick must not disable
            # the advisor for every later pick in the same session.
            return None
        self._cache[(enemy_name, position)] = data
        return data

    def _build(self, session, cell_id):
        position = self._my_position(session, cell_id)
        if position is None:
            return None
        enemy_id = self._enemy_in_my_lane(session, position)
        if enemy_id is None:
            return None

        self._ensure_champion_list()
        enemy_name = self._champ_id_to_name.get(enemy_id)
        if enemy_name is None:
            return None

        counters = self._counters_for(enemy_name, position)
        if not counters:
            return None

        # Flagging what the player already queued up turns the list from
        # trivia into something actionable without picking for them.
        my_list = {name.lower() for name in self.config.get("instalock", {}).get("champions", [])}
        return {
            "enemy": enemy_name,
            "position": position,
            "counters": [
                {
                    "name": entry["name"],
                    "win_rate": entry["win_rate"],
                    "in_my_list": entry["name"].lower() in my_list,
                }
                for entry in counters[:MAX_COUNTERS_SHOWN]
            ],
        }

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.config.get("counter_pick_advisor", {}).get("enabled", False):
                if self._sleep(1):
                    return
                continue
            if not self.lcu.is_league_connected():
                self._reset()
                if self._sleep(2):
                    return
                continue

            try:
                response = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if response.status_code != 200 or "RPC_ERROR" in response.text:
                    # Champ select is over - the advice goes with it rather
                    # than lingering into the next lobby.
                    self._reset()
                else:
                    session = response.json()
                    cell_id = session.get("localPlayerCellId")
                    if cell_id is not None:
                        self._update(session, cell_id)
            except Exception:
                logger.exception("CounterPickAdvisor._loop failed")

            if self._sleep(POLL_SECONDS):
                return

    def _update(self, session, cell_id):
        """Split out of `_loop` so the announce-once behaviour is testable
        without faking a poll tick."""
        recommendation = self._build(session, cell_id)
        if recommendation is None:
            return
        matchup = (recommendation["enemy"], recommendation["position"])
        self._recommendation = recommendation
        # The loop re-reads champ select every second; announcing on every
        # tick would bury the log. Only a genuinely new matchup is news.
        if matchup != self._last_matchup:
            self._last_matchup = matchup
            best = recommendation["counters"][0]
            self.on_event(
                "info",
                f"Counter Picks: vs {recommendation['enemy']} try {best['name']} ({best['win_rate']:.0%})",
            )
