from core.config import get_automation_delay, save_config
from features.base import ThreadedFeature

#: /lol-game-queues/v1/queues lists every queue Riot has ever defined -
#: TFT, custom-lobby variants, coop-vs-AI, and rotating modes that are
#: currently toggled off - in the client's own display language. A mode
#: filter only makes sense for queues a player can actually matchmake
#: into, so this is a curated allowlist (English names, matching the
#: fixed VALORANT_QUEUE_LABELS approach) rather than a passthrough of
#: whatever the LCU happens to return. Rotating entries (Nexus Blitz,
#: URF) are still filtered by isEnabled below, so they only show up once
#: Riot actually turns the event on.
#:
#: ARAM and its Chaos/Roots variants are deliberately excluded: your
#: champion is randomly assigned with no pick step at all, so there is
#: nothing for Instalock to hook into (that's what the separate Aram
#: bench-swap automation is for). Swiftplay is excluded too, for a more
#: fundamental reason - it has no live champion-select session whatsoever:
#: champion/loadout is chosen before queueing, so /lol-champ-select/v1/
#: session never exists for it. URF and Nexus Blitz both keep real
#: player-driven pick (and ban) phases, just faster/simultaneous ones, so
#: they stay valid.
LEAGUE_QUEUE_LABELS = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    400: "Normal (Draft Pick)",
    1750: "Arena",
    1300: "Nexus Blitz",
    1900: "URF",
}


class Instalock(ThreadedFeature):
    key = "instalock"
    title = "Instalock"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self.champ_dict = {}
        settings = self.config.get("instalock", {})
        self.enabled = bool(settings.get("enabled"))
        self.champions = list(settings.get("champions", []))
        #: Allowed queue IDs (from /lol-game-queues/v1/queues); empty = all.
        self.modes = list(settings.get("modes", []))

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "instalock_champion": list(self.champions),
            "modes": list(self.modes),
        }

    def _save_settings(self):
        if "instalock" not in self.config:
            self.config["instalock"] = {}
        self.config["instalock"]["enabled"] = self.enabled
        self.config["instalock"]["champions"] = self.champions
        self.config["instalock"]["modes"] = self.modes
        save_config(self.config)

    def get_available_queues(self) -> list:
        """Real matchmade PvP queues currently enabled, limited to the
        curated LEAGUE_QUEUE_LABELS allowlist.
        """
        response = self.lcu.lcu_request("GET", "/lol-game-queues/v1/queues")
        if response.status_code != 200:
            raise RuntimeError(f"Could not fetch queue list (HTTP {response.status_code})")

        queues = [
            {"id": queue["id"], "name": LEAGUE_QUEUE_LABELS[queue["id"]], "is_ranked": bool(queue.get("isRanked"))}
            for queue in response.json()
            if queue.get("id") in LEAGUE_QUEUE_LABELS and queue.get("isVisible") and queue.get("isEnabled")
        ]
        return sorted(queues, key=lambda queue: queue["name"])

    def toggle_mode(self, queue_id):
        queue_id = int(queue_id)
        if queue_id in self.modes:
            self.modes.remove(queue_id)
        else:
            self.modes.append(queue_id)
        self._save_settings()
        self.on_event("info", f"Instalock modes: {self.modes or 'all'}")
        return list(self.modes)

    def current_queue_id(self):
        """The queue ID for whatever's active right now (lobby, champ
        select, in-game), or None if that can't be determined — e.g. no
        active gameflow session. A miss here doesn't block locking: with no
        signal either way, the mode filter should fail open, not silently
        stop working.
        """
        response = self.lcu.lcu_request("GET", "/lol-gameflow/v1/session")
        if response.status_code != 200:
            return None
        try:
            return response.json().get("gameData", {}).get("queue", {}).get("id")
        except (AttributeError, TypeError):
            return None

    def update_champion_list(self):
        response = self.lcu.lcu_request("GET", "/lol-game-data/assets/v1/champion-summary.json")
        if response.status_code != 200:
            raise RuntimeError(f"Could not fetch champion data (HTTP {response.status_code})")

        for champ in response.json():
            champ_id = champ["id"]
            champ_name = champ["name"]
            if champ_id > 0:
                normalized_name = champ_name.lower()
                current_id = self.champ_dict.get(normalized_name)
                if current_id is None or champ_id < current_id:
                    self.champ_dict[normalized_name] = champ_id
        return sorted(self.champ_dict)

    def champ_name_to_id(self, champ_name):
        return self.champ_dict.get(champ_name.lower(), -1)

    def add_champion(self, champion_name):
        """Appends to the priority list (tried in order at lock time)."""
        if not self.champ_dict:
            self.update_champion_list()
        if self.champ_name_to_id(champion_name) == -1:
            raise ValueError(f"Champion '{champion_name}' was not found")

        normalized = champion_name.lower()
        if not any(existing.lower() == normalized for existing in self.champions):
            self.champions.append(champion_name)
        self.enabled = True

        self._save_settings()
        self.on_event("success", f"Instalock: added {champion_name} to the priority list")
        return list(self.champions)

    def remove_champion(self, champion_name):
        normalized = champion_name.lower()
        self.champions = [c for c in self.champions if c.lower() != normalized]
        if not self.champions:
            self.enabled = False

        self._save_settings()
        self.on_event("info", f"Instalock: removed {champion_name} from the priority list")
        return list(self.champions)

    def toggle(self, enable=None):
        if enable is None:
            self.enabled = not self.enabled
        else:
            self.enabled = bool(enable)
        self._save_settings()
        self.on_event("info", f"Instalock {'enabled' if self.enabled else 'disabled'}")
        return self.enabled

    def find_pending_action(self, session, cell_id):
        """The champ select action this feature should act on, if any.

        Champ select nests actions in phases; only the local player's own
        unfinished "pick" counts. Extracted from the loop so the
        matching can be tested without a live client.
        """
        if not self.enabled or cell_id is None:
            return None

        for phase in session.get("actions", []):
            if not isinstance(phase, list):
                continue
            for action in phase:
                if (
                    action.get("actorCellId") == cell_id
                    and action.get("type") == "pick"
                    and not action.get("completed")
                ):
                    return action
        return None

    def resolve_champion(self, session, cell_id):
        """First champion in the priority list that's neither already locked
        by a teammate nor banned by either team — so a teammate taking your
        first pick, or it getting banned, falls through to the next one.
        """
        unavailable_ids = set()
        for player in session.get("myTeam", []):
            if player.get("cellId") == cell_id:
                continue
            champ_id = player.get("championId")
            if champ_id:
                unavailable_ids.add(champ_id)

        bans = session.get("bans") or {}
        for ban_list in (bans.get("myTeamBans"), bans.get("theirTeamBans")):
            for champ_id in ban_list or []:
                unavailable_ids.add(champ_id)

        for name in self.champions:
            champ_id = self.champ_name_to_id(name)
            if champ_id != -1 and champ_id not in unavailable_ids:
                return name
        return None

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                if not self.enabled:
                    self._sleep(0.5)
                    continue
                if not self.lcu.is_league_connected():
                    self._sleep(2)
                    continue
                if not self.champ_dict:
                    self.update_champion_list()

                champ_select_resp = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
                if "RPC_ERROR" in champ_select_resp.text:
                    self._sleep(0.3)
                    continue

                session = champ_select_resp.json()
                cell_id = session.get("localPlayerCellId")
                if cell_id is None:
                    self._sleep(0.3)
                    continue

                if self.modes:
                    queue_id = self.current_queue_id()
                    if queue_id is not None and queue_id not in self.modes:
                        self._sleep(0.5)
                        continue

                pending = self.find_pending_action(session, cell_id)
                if pending is not None:
                    champion_name = self.resolve_champion(session, cell_id)
                    if champion_name is not None:
                        self._lock_champion(pending, champion_name)

                self._sleep(0.3)
            except Exception:
                self._sleep(1)

    def _lock_champion(self, action, champion_name):
        delay = get_automation_delay(self.config, "instalock", 0.3)
        if delay:
            self._sleep(delay)

        champion_id = self.champ_name_to_id(champion_name)
        if champion_id == -1:
            return

        response = self.lcu.lcu_request(
            "PATCH",
            f"/lol-champ-select/v1/session/actions/{action['id']}",
            {"completed": True, "championId": champion_id},
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Could not lock champion (HTTP {response.status_code})")
        self.on_event("success", f"Locked {champion_name}")
        self._sleep(0.3)
