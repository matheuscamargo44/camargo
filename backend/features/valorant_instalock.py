import logging

from valclient.exceptions import HandshakeError, PhaseError

from core.config import save_config
from core.valorant_client import VALID_REGIONS
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)


class ValorantInstalock(ThreadedFeature):
    key = "valorant_instalock"
    title = "Instalock"
    category = "Valorant"
    #: Which shared client the registry should inject (see FeatureRegistry).
    game = "valorant"

    def __init__(self, valorant_client, config, on_event=None):
        super().__init__(valorant_client, config, on_event)
        self.valorant = valorant_client
        self.agent_dict = {}
        settings = self.config.get("valorant_instalock", {})
        self.enabled = bool(settings.get("enabled"))
        self.agent = settings.get("agent", "None")
        self.region_override = settings.get("region", "")
        self.valorant.set_region(self.region_override or None)
        #: Match IDs already locked this run, so a match isn't re-locked every
        #: poll while its pregame phase is still active. Not persisted: a
        #: restart re-locking an in-progress match is an acceptable edge case.
        self._seen_matches = set()

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.enabled,
            "instalock_agent": self.agent,
            "region": self.region_override or "auto",
        }

    def _save_settings(self):
        self.config.setdefault("valorant_instalock", {})
        self.config["valorant_instalock"]["enabled"] = self.enabled
        self.config["valorant_instalock"]["agent"] = self.agent
        self.config["valorant_instalock"]["region"] = self.region_override
        save_config(self.config)

    def update_agent_list(self):
        response = self.valorant.fetch_agent_directory()
        if response.status_code != 200:
            raise RuntimeError(f"Could not fetch agent data (HTTP {response.status_code})")

        for agent in response.json().get("data", []):
            name = agent.get("displayName")
            uuid = agent.get("uuid")
            if name and uuid:
                self.agent_dict[name.lower()] = uuid
        return sorted(self.agent_dict)

    def agent_name_to_uuid(self, agent_name):
        return self.agent_dict.get(agent_name.lower())

    def set_agent(self, agent_name):
        if agent_name.lower() == "none":
            self.agent = "None"
            self.enabled = False
        else:
            if not self.agent_dict:
                self.update_agent_list()
            if self.agent_name_to_uuid(agent_name) is None:
                raise ValueError(f"Agent '{agent_name}' was not found")
            self.agent = agent_name
            self.enabled = True
        self._save_settings()
        self.on_event("success", f"Valorant Instalock configured for {self.agent}")
        return self.agent

    def toggle(self, enable=None):
        if enable is None:
            self.enabled = not self.enabled
        else:
            self.enabled = bool(enable)
        self._save_settings()
        self.on_event("info", f"Valorant Instalock {'enabled' if self.enabled else 'disabled'}")
        return self.enabled

    def set_region(self, region_code):
        """Pins the region used for VALORANT's remote pregame endpoints, or
        clears it ("" / "auto") to fall back to reading it from the game's
        own log file every time the client (re)activates.
        """
        region_code = (region_code or "").strip().lower()
        if region_code == "auto":
            region_code = ""
        if region_code and region_code not in VALID_REGIONS:
            raise ValueError(f"Unknown region '{region_code}', expected one of {VALID_REGIONS}")

        self.region_override = region_code
        self.valorant.set_region(region_code or None)
        self._save_settings()
        self.on_event("info", f"VALORANT region set to {region_code or 'auto-detect'}")
        return self.region_override or "auto"

    def find_pending_match(self, presence):
        """The pregame match ID this feature should lock into, if any.

        None covers every "nothing to do" case: not in champ select's
        VALORANT equivalent (agent select), or already locked for this
        particular match.
        """
        if not presence:
            return None
        match_data = presence.get("matchPresenceData") or {}
        if match_data.get("sessionLoopState") != "PREGAME":
            return None

        match = self.valorant.pregame_fetch_match()
        match_id = match.get("ID") or match.get("MatchID")
        if match_id is None or match_id in self._seen_matches:
            return None
        return match_id

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                if not self.enabled:
                    self._sleep(0.5)
                    continue
                if not self.valorant.is_connected():
                    self._sleep(2)
                    continue
                if not self.agent_dict:
                    self.update_agent_list()

                presence = self.valorant.fetch_presence()
                match_id = self.find_pending_match(presence)
                if match_id is not None:
                    self._lock_agent(match_id)

                self._sleep(0.5)
            except PhaseError:
                self._sleep(0.5)
            except HandshakeError:
                self._sleep(2)
            except Exception:
                logger.exception("ValorantInstalock loop failed")
                self._sleep(1)

    def _lock_agent(self, match_id):
        if self.agent == "None":
            return
        agent_uuid = self.agent_name_to_uuid(self.agent)
        if agent_uuid is None:
            return

        self.valorant.pregame_select_character(agent_uuid)
        self.valorant.pregame_lock_character(agent_uuid)
        self._seen_matches.add(match_id)
        self.on_event("success", f"Locked {self.agent}")
