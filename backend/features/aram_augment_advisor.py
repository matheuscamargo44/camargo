"""ARAM: Mayhem (ARAM: Desordem, LCU gameMode "KIWI") augment advisor.

No Riot-sanctioned API exposes which augments are offered during the pick
screen (confirmed exhaustively - see `docs/smart-counter-pick-spec.md`,
Part B), so this identifies them the same way Blitz and the OP.GG desktop
app do: screen-capture the 3 card icons and match them against a reference
icon set (`core.augment_catalog`), then look up tier data from OP.GG's MCP.

The picker's presence is *detected* on screen (see
`core.augment_vision.picker_is_open`) rather than inferred from the
player's level, because levels 7/11/15 only grant an augment - the player
opens the picker whenever they choose.

Requires League to run in borderless/windowed mode, at 1920x1080. Both
halves of the feature depend on it: an exclusive-fullscreen game cannot be
captured by a normal desktop grab, and no overlay window can draw above it.
This is the same requirement Blitz and the OP.GG desktop app carry, and it
is an OS-level constraint rather than something to engineer around. Failing
it is harmless - the border probe simply never matches, so the feature sits
idle instead of misfiring.

Every step degrades to "no recommendation" rather than a wrong one.
"""
import logging

from core.aram_augment_regions import AUGMENT_CARD_REGIONS, SUPPORTED_RESOLUTION
from core.augment_catalog import augment_catalog
from core.config import save_config
from core.augment_vision import capture_region, picker_is_open, primary_monitor_resolution
from core.live_client_data import get_all_game_data, local_player
from core.opgg_client import opgg_client
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)

ARAM_MAYHEM_GAME_MODE = "KIWI"

#: OP.GG rates ARAM augments on a numeric tier where **lower is better** -
#: verified against performance scores per champion (Viego: T3 averages
#: 79.5, T4 78.5, T5 76.6) and against the shape of the distribution, where
#: T3 is rare and T5 is the bulk. Only 3/4/5 are ever returned, checked
#: across five champions, so the three of them are the whole scale and the
#: best one earns the top rank.
TIER_RANKS = {3: "S", 4: "A", 5: "B"}


def tier_rank(tier):
    """Letter rank for display. Numeric tier stays the sort key; this is
    presentation only."""
    return TIER_RANKS.get(tier)

#: The gold border is drawn before the icons finish fading in, so give the
#: picker a moment to settle, then confirm it's still open before capturing.
CAPTURE_SETTLE_SECONDS = 0.4

#: How often to probe for the picker while in a Mayhem game. The probe reads
#: 27 pixels, so this is cheap; the pick window is only a few seconds.
PICKER_POLL_SECONDS = 0.5


class AramAugmentAdvisor(ThreadedFeature):
    key = "aram_augment_advisor"
    title = "Aram Augments"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self._champ_name_to_id = {}
        self._reset_game_state()
        self._unsupported_resolution = False
        self._warned_unsupported_resolution = False

    def get_status(self) -> dict:
        return {
            "key": self.key,
            "enabled": self.config.get("aram_augment_advisor", {}).get("enabled", False),
            "unsupported_resolution": self._unsupported_resolution,
            "recommendation": self._recommendation,
        }

    def toggle(self, state: bool = None) -> bool:
        current = self.config.get("aram_augment_advisor", {}).get("enabled", False)
        new_state = (not current) if state is None else state
        self.config.setdefault("aram_augment_advisor", {})["enabled"] = new_state
        save_config(self.config)
        self.on_event("info", f"Aram Augments {'enabled' if new_state else 'disabled'}")
        return new_state

    def _reset_game_state(self):
        self._picker_was_open = False
        self._recommendation = None
        self._champion_augment_data = None
        self._champion_id_this_game = None

    # -- champion id lookup, same source Instalock builds champ_dict from --

    def _ensure_champion_list(self):
        if self._champ_name_to_id:
            return
        try:
            response = self.lcu.lcu_request("GET", "/lol-game-data/assets/v1/champion-summary.json")
            if response.status_code != 200:
                return
            for champ in response.json():
                if champ["id"] > 0:
                    self._champ_name_to_id[champ["name"]] = champ["id"]
        except Exception:
            logger.exception("AramAugmentAdvisor: failed to load champion list")

    def _champion_id_for(self, champion_name):
        self._ensure_champion_list()
        return self._champ_name_to_id.get(champion_name)

    # -- identification + tier lookup --

    def _identify_offered_augments(self):
        results = []
        for region in AUGMENT_CARD_REGIONS:
            image = capture_region((region["x"], region["y"], region["w"], region["h"]))
            if image is None:
                continue
            candidates = augment_catalog.identify(image)
            if candidates:
                results.append({"slot": region["slot"], "candidates": candidates})
        return results

    @staticmethod
    def _resolve_candidates(candidates, tier_data):
        """Turns a tied candidate set into one displayable answer.

        A few genuinely different augments ship identical art, so the
        matcher can only narrow a card down to a set. OP.GG's per-champion
        data covers tier 3 and above, which resolves most of it: usually
        only one candidate is rated at all. When several are rated and they
        disagree, there is no honest way to pick, so the tier is dropped
        rather than guessed - the slot still shows, it just cannot win
        "best". Measured against a real champion pool, that last case hit
        4 of 118 icon groups.
        """
        rated = [augment_id for augment_id in candidates if augment_id in tier_data]
        tiers = {tier_data[augment_id]["tier"] for augment_id in rated}

        if len(tiers) == 1:
            tier = tiers.pop()
            # Prefer naming a rated candidate: it is the one the tier
            # belongs to, and the one actually offered in this mode.
            return rated[0], tier, False
        if len(tiers) > 1:
            return rated[0], None, True

        # Nothing rated. OP.GG omits everything below tier 3, so this
        # reliably means "worse than the rated cards on offer" rather than
        # "unknown" - worth showing, never worth recommending.
        distinct_names = {augment_catalog.name(augment_id) for augment_id in candidates}
        return candidates[0], None, len(distinct_names) > 1

    def _tier_data_for_champion(self, champion_id):
        if self._champion_id_this_game == champion_id and self._champion_augment_data is not None:
            return self._champion_augment_data
        try:
            data = opgg_client.get_aram_augments(champion_id)
        except Exception:
            logger.exception("AramAugmentAdvisor: OP.GG augment tier lookup failed")
            data = {}
        self._champion_id_this_game = champion_id
        self._champion_augment_data = data
        return data

    def _build_recommendation(self, champion_name):
        identified = self._identify_offered_augments()
        if not identified:
            return None

        champion_id = self._champion_id_for(champion_name)
        tier_data = self._tier_data_for_champion(champion_id) if champion_id else {}

        augments = []
        best_slot, best_tier = None, None
        for entry in identified:
            augment_id, tier, ambiguous = self._resolve_candidates(entry["candidates"], tier_data)
            augments.append(
                {
                    "slot": entry["slot"],
                    "augment_id": augment_id,
                    # The matched *art* is always right, so the icon is safe
                    # to show; it is only which augment shares that art that
                    # is uncertain. Naming one of them would be asserting
                    # something we don't know.
                    "name": None if ambiguous else augment_catalog.name(augment_id),
                    "icon_url": augment_catalog.icon_url(augment_id),
                    "tier": tier,
                    "rank": tier_rank(tier),
                    "ambiguous": ambiguous,
                }
            )
            # Lower tier number is better (1 = OP), matching every other
            # OP.GG tier field already used in this codebase.
            if tier is not None and (best_tier is None or tier < best_tier):
                best_slot, best_tier = entry["slot"], tier

        return {
            "active": True,
            "champion": champion_name,
            "regions": AUGMENT_CARD_REGIONS,
            "augments": augments,
            "best_slot": best_slot,
        }

    def _on_picker_opened(self, champion_name):
        if self._sleep(CAPTURE_SETTLE_SECONDS):
            return
        # The player may have picked during the settle delay.
        if not picker_is_open():
            return

        self._recommendation = self._build_recommendation(champion_name)
        if self._recommendation and self._recommendation["best_slot"] is not None:
            self.on_event(
                "info",
                f"Aram Augments: recommending slot {self._recommendation['best_slot'] + 1} for {champion_name}",
            )

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.config.get("aram_augment_advisor", {}).get("enabled", False):
                if self._sleep(1):
                    return
                continue

            if not self.lcu.is_league_connected():
                if self._sleep(2):
                    return
                continue

            if primary_monitor_resolution() != SUPPORTED_RESOLUTION:
                self._unsupported_resolution = True
                if not self._warned_unsupported_resolution:
                    self._warned_unsupported_resolution = True
                    self.on_event("info", "Aram Augments: unsupported display resolution, feature inactive")
                if self._sleep(30):
                    return
                continue
            self._unsupported_resolution = False

            try:
                phase = self.lcu.lcu_request("GET", "/lol-gameflow/v1/gameflow-phase").json()
            except Exception:
                phase = None

            if phase != "InProgress":
                self._reset_game_state()
                if self._sleep(2):
                    return
                continue

            data = get_all_game_data()
            if data is None or data.get("gameData", {}).get("gameMode") != ARAM_MAYHEM_GAME_MODE:
                if self._sleep(1):
                    return
                continue

            player = local_player(data)
            if player is None:
                if self._sleep(1):
                    return
                continue

            is_open = picker_is_open()
            if is_open and not self._picker_was_open:
                self._on_picker_opened(player.get("championName"))
            elif not is_open and self._picker_was_open:
                # Picker closed (picked, rerolled, or timed out): the badges
                # must come down with it.
                self._recommendation = None
            self._picker_was_open = is_open

            if self._sleep(PICKER_POLL_SECONDS):
                return
