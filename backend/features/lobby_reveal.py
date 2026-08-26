"""Opens the current champ-select lobby on a third-party scouting site.

This is a deliberately different way of using a third party than the rest
of this app. Everywhere else (see `core.opgg_client`) we call an API and
parse the answer, which means owning a parser that breaks whenever the
other side changes shape - the OP.GG augment scraper was removed partly
for exactly that fragility. Here we build a URL and hand off to the
browser: there is nothing to parse, so there is nothing to break when the
site redesigns, no rate limit to respect, and no cache to keep warm. The
cost is that the answer lands outside the app instead of inside it, which
for "show me who I'm playing with" is where the player wants it anyway.

Ported from tiamat (github.com/gyaaf/tiamat), which solves the same
problem the same way.
"""
import logging
import webbrowser

from core.config import save_config
from features.base import Feature

logger = logging.getLogger(__name__)

#: Provider key -> display name. Each renders a "multisearch" page taking
#: every summoner in one URL, which is what makes the handoff viable at
#: all: one link scouts the whole lobby.
PROVIDERS = {
    "porofessor": "Porofessor",
    "opgg": "OP.GG",
    "ugg": "U.GG",
}

DEFAULT_PROVIDER = "porofessor"

#: U.GG is the odd one out: it wants Riot's platform id (`na1`), while
#: Porofessor and OP.GG take the plain web region (`na`) that the client
#: itself reports. Anything not listed falls through unchanged, so a new
#: region added by Riot degrades to "probably right" rather than raising.
UGG_REGIONS = {
    "br": "br1",
    "eune": "eun1",
    "euw": "euw1",
    "jp": "jp1",
    "kr": "kr",
    "lan": "la1",
    "las": "la2",
    "na": "na1",
    "oce": "oc1",
    "ru": "ru",
    "tr": "tr1",
    "ph": "ph2",
    "sg": "sg2",
    "th": "th2",
    "tw": "tw2",
    "vn": "vn2",
}


def build_reveal_url(provider, region, riot_ids):
    """Pure: no client, no network. The provider matrix (3 providers x 2
    Riot-ID formats x 2 region formats) is the part most likely to be got
    wrong, so it is kept callable with plain strings.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"unknown Lobby Reveal provider: {provider!r}")
    if not riot_ids:
        raise ValueError("no summoners to reveal")

    region = (region or "").lower()
    if not region:
        raise ValueError("no region to reveal for")

    if provider == "ugg":
        # U.GG writes a Riot ID as Name-TAG; the other two take Name#TAG,
        # which `requests`-style quoting has to escape (# would otherwise
        # start a URL fragment and silently truncate the whole list).
        names = [
            f"{game_name}-{tag_line}" if separator else riot_id
            for riot_id, (game_name, separator, tag_line) in (
                (riot_id, riot_id.rpartition("#")) for riot_id in riot_ids
            )
        ]
        return f"https://u.gg/lol/multisearch?summoners={_join(names)}&region={UGG_REGIONS.get(region, region)}"

    if provider == "porofessor":
        return f"https://porofessor.gg/pregame/{region}/{_join(riot_ids)}/soloqueue/season"
    return f"https://www.op.gg/multisearch/{region}?summoners={_join(riot_ids)}"


def _join(names):
    from urllib.parse import quote

    # `safe=","` keeps the separator readable while still escaping the
    # `#` in every Riot ID.
    return quote(",".join(names), safe=",")


class LobbyReveal(Feature):
    key = "lobby_reveal"
    title = "Lobby Reveal"
    category = "Social"

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "provider": self._provider(),
            "providers": PROVIDERS,
        }

    def _provider(self):
        provider = self.config.get("lobby_reveal", {}).get("provider", DEFAULT_PROVIDER)
        # A config hand-edited to a provider we dropped must not make the
        # feature permanently raise - fall back rather than fail.
        return provider if provider in PROVIDERS else DEFAULT_PROVIDER

    def set_provider(self, provider: str) -> dict:
        if provider not in PROVIDERS:
            raise ValueError(f"unknown Lobby Reveal provider: {provider!r}")
        self.config.setdefault("lobby_reveal", {})["provider"] = provider
        save_config(self.config)
        self.on_event("info", f"Lobby Reveal provider set to {PROVIDERS[provider]}")
        return self.get_status()

    # -- reading the lobby --

    def _riot_ids_in_champ_select(self):
        response = self.lcu.lcu_request("GET", "/lol-champ-select/v1/session")
        # The LCU answers a closed champ select with 200 + an RPC_ERROR
        # body rather than a 404, so the status code alone is not enough.
        if response.status_code != 200 or "RPC_ERROR" in response.text:
            raise RuntimeError("Lobby Reveal only works during champion select")

        session = response.json()
        team = session.get("myTeam") or []

        # Riot hides teammate names in champ select for most queues now
        # (`nameVisibilityType == "HIDDEN"`), which is what makes the
        # obvious /lol-summoner lookup below come back empty exactly when
        # the feature is most wanted. The names are still readable from the
        # *Riot Client's* chat service - a different process and a
        # different port than the LCU (see LCUClient.riot_request) - where
        # the champ-select room lists every participant's game name and
        # tag. Credit to tiamat for finding this path.
        if any(player.get("nameVisibilityType") == "HIDDEN" for player in team):
            return self._riot_ids_from_chat()

        riot_ids = []
        for player in team:
            summoner_id = player.get("summonerId")
            if not summoner_id or str(summoner_id) == "0":
                continue
            response = self.lcu.lcu_request("GET", f"/lol-summoner/v1/summoners/{summoner_id}")
            if response.status_code != 200:
                continue
            summoner = response.json()
            game_name, tag_line = summoner.get("gameName"), summoner.get("tagLine")
            if game_name and tag_line:
                riot_ids.append(f"{game_name}#{tag_line}")
        return riot_ids

    def _riot_ids_from_chat(self):
        response = self.lcu.riot_request("GET", "/chat/v5/participants")
        if response.status_code != 200:
            return []
        riot_ids = []
        for participant in response.json().get("participants") or []:
            # The chat service lists every room the client is in; only the
            # champ-select one describes this lobby.
            if "champ-select" not in (participant.get("cid") or ""):
                continue
            game_name, tag = participant.get("game_name"), participant.get("game_tag")
            if game_name and tag:
                riot_ids.append(f"{game_name}#{tag}")
        return riot_ids

    def _region(self):
        response = self.lcu.lcu_request("GET", "/riotclient/region-locale")
        if response.status_code != 200:
            return ""
        return response.json().get("webRegion") or ""

    # -- the action itself --

    def reveal(self) -> dict:
        """Opens the lobby on the configured provider and returns the URL.

        The URL is returned as well as opened so the activity log has
        something concrete to show, and so the whole path stays testable
        without launching a browser.
        """
        riot_ids = self._riot_ids_in_champ_select()
        region = self._region()
        if not riot_ids:
            raise RuntimeError("Could not read any summoner names from this lobby")
        if not region:
            raise RuntimeError("Could not read the client's region")

        provider = self._provider()
        url = build_reveal_url(provider, region, riot_ids)
        webbrowser.open(url)
        self.on_event("info", f"Lobby Reveal: opened {len(riot_ids)} summoners on {PROVIDERS[provider]}")
        return {"url": url, "count": len(riot_ids)}
