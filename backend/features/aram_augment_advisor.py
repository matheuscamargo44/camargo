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
#: across five champions, so the three of them are the whole scale.
TIER_RANKS = {3: "S", 4: "A", 5: "B"}

#: Within tier 3 there is real spread - checked live, Viego's tier-3
#: performance runs 72.1 to 88.0, Garen's 63.2 to 81.8 - so the very best
#: of it earns its own rank rather than being lumped in with the rest of S.
#: A candidate within this many performance points of the champion's best
#: tier-3 score counts as tied for OP.
OP_PERFORMANCE_MARGIN = 1.0


def _tier3_best_performance(tier_data):
    scores = [
        entry.get("performance")
        for entry in tier_data.values()
        if entry.get("tier") == 3 and entry.get("performance") is not None
    ]
    return max(scores) if scores else None


def augment_rank(tier, performance, tier3_best):
    """Letter rank for display. `performance` only ever breaks a tie
    *within* tier 3, to carve OP out of S - never compared across tiers.

    Checked live: tier 5 (the worst bucket) includes augments scoring well
    above tier 3's real range (up to 170, against tier 3's max of ~88) -
    a low-sample-size artifact, not genuine strength. OP.GG's own tier
    already accounts for that (verified: mean performance drops cleanly
    from tier 3 to 5), so it stays the primary signal and performance is
    only trusted to compare augments the tier already agrees are the best.
    """
    if tier == 3 and performance is not None and tier3_best is not None and tier3_best - performance <= OP_PERFORMANCE_MARGIN:
        return "OP"
    return TIER_RANKS.get(tier)


_RANK_JUSTIFICATIONS = {
    "OP": "The best tier-3 augment for {champion}.",
    "S": "A top-tier augment for {champion}.",
    "A": "A solid augment for {champion}.",
    "B": "Below the stronger options for {champion}.",
}


def augment_justification(champion_name, rank, performance):
    """Short, honest reasoning grounded in OP.GG's real per-champion data.

    There is no textual "why" from OP.GG for augments - `desc` is just the
    augment's own generic description, the same text already on the card,
    not champion-specific reasoning. So this sticks to what's actually
    known: the tier grade and the real performance score. No invented
    flavor text about synergy or mechanics we have no data for.

    The score is only ever appended for OP/S (tier 3): that is the one
    tier where performance is trusted at all (see augment_rank), so it is
    the only place where the number means what it looks like it means.
    Showing it next to an A/B card would be actively misleading - checked
    live, a tier-5 "B" augment can score 170, well above a tier-3 "OP" at
    88, since performance is not comparable across tiers.
    """
    if rank is None:
        return f"Not among the stronger augments for {champion_name} in this data."
    text = _RANK_JUSTIFICATIONS[rank].format(champion=champion_name)
    if rank in ("OP", "S") and performance is not None:
        text += f" (score {performance:.0f})"
    return text

#: The gold border is drawn before the icons finish fading in, so give the
#: picker a moment to settle, then confirm it's still open before capturing.
#: Also doubles as the spacing between retry attempts (see
#: CAPTURE_ATTEMPTS): a capture that lands on a half-drawn frame is worth
#: trying again a moment later, not giving up on for the rest of the pick.
CAPTURE_SETTLE_SECONDS = 0.4

#: A capture landing during a transition (fade-in, or the frame right after
#: a reroll) can legitimately identify nothing even with the picker
#: genuinely open. Retried rather than given up on after one miss.
CAPTURE_ATTEMPTS = 3

#: How often to probe for the picker while in a Mayhem game. The probe reads
#: 27 pixels, so this is cheap; the pick window is only a few seconds.
PICKER_POLL_SECONDS = 0.5

#: Hovering a card to compare it enlarges it (see
#: core.aram_augment_regions.CARD_BORDER_REQUIRED_COUNT for the matching
#: fix on the read side), and every so often the single-frame read still
#: comes back closed even with the 2-of-3 tolerance. Confirmed live: a real
#: session's log showed one pick moment re-triggering 4 times in 6s. This
#: requires the closed reading to repeat before believing it, rather than
#: dropping the recommendation on one bad frame - the badge may linger up
#: to this long after a real close, which is a much smaller cost than
#: flickering while the player is still deciding.
CLOSE_DEBOUNCE_TICKS = 3


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
        self._closed_streak = 0
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
        tier3_best = _tier3_best_performance(tier_data)

        augments = []
        best_slot, best_key = None, None
        for entry in identified:
            augment_id, tier, ambiguous = self._resolve_candidates(entry["candidates"], tier_data)
            performance = tier_data.get(augment_id, {}).get("performance") if tier is not None else None
            rank = None if ambiguous else augment_rank(tier, performance, tier3_best)
            justification = (
                "Several augments share this exact icon, so which one this is can't be told for sure."
                if ambiguous
                else augment_justification(champion_name, rank, performance)
            )
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
                    "rank": rank,
                    "justification": justification,
                    "ambiguous": ambiguous,
                }
            )
            # Lower tier number is better, matching every other OP.GG tier
            # field already used in this codebase; performance only breaks
            # a tie within the same tier (e.g. OP vs a plain S offered
            # together), never crosses tiers - see augment_rank().
            if tier is not None:
                key = (tier, -(performance or 0))
                if best_key is None or key < best_key:
                    best_slot, best_key = entry["slot"], key

        return {
            "active": True,
            "champion": champion_name,
            "regions": AUGMENT_CARD_REGIONS,
            "augments": augments,
            "best_slot": best_slot,
        }

    def _on_picker_opened(self, champion_name):
        for _attempt in range(CAPTURE_ATTEMPTS):
            if self._sleep(CAPTURE_SETTLE_SECONDS):
                return
            # The player may have picked (or this may be a transient bad
            # read - see CARD_BORDER_REQUIRED_COUNT) since the last check.
            if not picker_is_open():
                return

            recommendation = self._build_recommendation(champion_name)
            if recommendation is not None:
                self._recommendation = recommendation
                if recommendation["best_slot"] is not None:
                    self.on_event(
                        "info",
                        f"Aram Augments: recommending slot {recommendation['best_slot'] + 1} for {champion_name}",
                    )
                return
        # Every attempt identified nothing - leave _recommendation at None
        # (its default) rather than show badges for a guess.

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

            self._handle_picker_state(picker_is_open(), player.get("championName"))

            if self._sleep(PICKER_POLL_SECONDS):
                return

    def _handle_picker_state(self, is_open, champion_name):
        """The open/closed edge handling, pulled out of `_loop()` so it's
        directly testable without monkeypatching module globals to fake a
        poll tick."""
        if is_open:
            self._closed_streak = 0
            if not self._picker_was_open:
                self._on_picker_opened(champion_name)
                self._picker_was_open = True
        elif self._picker_was_open:
            self._closed_streak += 1
            if self._closed_streak >= CLOSE_DEBOUNCE_TICKS:
                # Picker closed (picked, rerolled, or timed out): the
                # badges come down with it.
                self._recommendation = None
                self._picker_was_open = False
