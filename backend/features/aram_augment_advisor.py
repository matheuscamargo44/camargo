"""ARAM: Mayhem (ARAM: Desordem, LCU gameMode "KIWI") augment advisor.

No Riot-sanctioned API exposes which augments are offered during the pick
screen (confirmed exhaustively - see `docs/smart-counter-pick-spec.md`,
Part B), so this identifies them the same way Blitz and the OP.GG desktop
app do: screen-capture the 3 card icons and match them against a reference
icon set (`core.augment_catalog`), then look up tier/performance data by
reading OP.GG's own ARAM: Mayhem page for the champion (`core.opgg_scraper`),
falling back to OP.GG's official but narrower MCP tool (`core.opgg_client`)
if that scrape fails.

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
from core.opgg_scraper import scrape_aram_augments
from features.base import ThreadedFeature

logger = logging.getLogger(__name__)

ARAM_MAYHEM_GAME_MODE = "KIWI"

#: OP.GG rates ARAM augments on a numeric tier where **lower is better**,
#: across six tiers (0-5), not three. Confirmed live by diffing a full page
#: scrape against the MCP tool's own output for Viego: every entry the MCP
#: returns matches the scrape exactly (id 1103 "Bread And Butter": tier 3,
#: performance 72.1 in both) - but the MCP only ever hands back tiers 3-5,
#: silently omitting 0-2, the champion's three *best* bands (65 of Viego's
#: 200 augments). `core.opgg_scraper` reads the site directly to recover
#: those; the MCP is only a fallback if that scrape fails. Two raw tiers
#: are grouped per letter (their performance averages sit close enough in
#: pairs - Viego: T0 82.5/T1 82.7, T2 78.2/T3 79.5, T4 78.5/T5 76.6 - to
#: read as one band each) so the on-screen rank vocabulary (OP/S/A/B)
#: doesn't have to grow just because the data got deeper.
TIER_RANKS = {0: "S", 1: "S", 2: "A", 3: "A", 4: "B", 5: "B"}

#: The best of the six tiers - carved into its own OP rank below.
BEST_TIER = 0

#: Within the best tier there is real spread - checked live, Viego's tier-0
#: performance runs 76.5 to 88.7 - so the very best of it earns its own
#: rank rather than being lumped in with the rest of S. A candidate within
#: this many performance points of the champion's best tier-0 score counts
#: as tied for OP.
OP_PERFORMANCE_MARGIN = 1.0


def _best_tier_performance(tier_data):
    scores = [
        entry.get("performance")
        for entry in tier_data.values()
        if entry.get("tier") == BEST_TIER and entry.get("performance") is not None
    ]
    return max(scores) if scores else None


def augment_rank(tier, performance, best_tier_best):
    """Letter rank for display. `performance` only ever breaks a tie
    *within* the best tier, to carve OP out of S - never compared across
    tiers.

    Checked live: tier 5 (the worst bucket) includes augments scoring well
    above the best tier's real range (up to 170, against tier 0's max of
    ~89) - a low-sample-size artifact, not genuine strength. OP.GG's own
    tier already accounts for that (verified: mean performance is flat to
    slightly declining from tier 0 to 5, with tier 5 just far noisier), so
    it stays the primary signal and performance is only trusted to compare
    augments the tier already agrees are the best.
    """
    if (
        tier == BEST_TIER
        and performance is not None
        and best_tier_best is not None
        and best_tier_best - performance <= OP_PERFORMANCE_MARGIN
    ):
        return "OP"
    return TIER_RANKS.get(tier)


_RANK_JUSTIFICATIONS = {
    "OP": "The best augment for {champion}.",
    "S": "A top-tier augment for {champion}.",
    "A": "A solid augment for {champion}.",
    "B": "Below the stronger options for {champion}.",
}

#: Community Dragon's raw rarity string -> a human label. Researched live
#: (2026-08-25): the full catalog has 5 values; kBronze/kEventChoice may not
#: even be offered in ARAM Mayhem specifically (never seen live), kept here
#: so an unrecognized value degrades to omitting the rarity rather than
#: crashing or showing a raw "kBronze"-style string.
RARITY_LABELS = {
    "kSilver": "Silver",
    "kGold": "Gold",
    "kPrismatic": "Prismatic",
    "kBronze": "Bronze",
    "kEventChoice": "Event",
}


#: Riot's own documented design intent for rarity (not a community guess -
#: see docs/smart-counter-pick-spec.md for the research): Prismatic
#: augments carry "the most powerful, game-changing effects", Gold "strong
#: effects", Silver "basic stat boosts and utility". Used only as a
#: last-resort tiebreaker in _build_recommendation, when none of the 3
#: offered cards has real OP.GG performance data at all - never mixed with,
#: and never allowed to override, a real tier/performance-backed rank.
#: Bronze/Event are deliberately absent: never confirmed live in ARAM
#: Mayhem (see RARITY_LABELS), so there is no basis to rank them at all.
RARITY_FALLBACK_RANK = {"Prismatic": 0, "Gold": 1, "Silver": 2}

#: The rank value used to flag the rarity-fallback pick specifically -
#: distinct from a real OP/S/A/B (see augment_rank), which is why it isn't
#: a key in RANK_JUSTIFICATIONS: its text is generated separately, in
#: _build_recommendation, always naming the rarity it was picked on.
GUESS_RANK = "GUESS"


def augment_justification(champion_name, rank, performance, rarity_label=None):
    """Short, honest reasoning grounded in OP.GG's real per-champion data.

    There is no textual "why" from OP.GG for augments - `desc` is just the
    augment's own generic description, the same text already on the card,
    not champion-specific reasoning. So this sticks to what's actually
    known: the tier grade and the real performance score. No invented
    flavor text about synergy or mechanics we have no data for.

    The score is only ever appended for OP/S (tier 0-1): that is the band
    where performance is trusted at all (see augment_rank), so it is the
    only place where the number means what it looks like it means. Showing
    it next to an A/B card would be actively misleading - checked live, a
    tier-5 "B" augment can score 170, well above a tier-0 "OP" at ~89,
    since performance is not comparable across tiers.

    An unrated augment (`rank is None`) is *not* the same claim as "this is
    weak" - it means neither `core.opgg_scraper` (the full-pool source read
    from OP.GG's own site) nor the MCP fallback returned this augment id at
    all for this champion, which happens for genuinely obscure pairings
    OP.GG has too few match samples for. This is now rare rather than the
    common case it was before the scraper existed: the MCP tool alone
    covered only tiers 3-5 (135 of Viego's 200 augments, and none of his
    three *best* bands), so most 3-card offers used to show at least one
    "no data" card purely from that gap. The scraper closes it - see
    `core.opgg_scraper` for how, and for the live diff that proved the MCP
    was silently dropping tiers 0-2 rather than the pool genuinely lacking
    data for them.

    `rarity_label` (Silver/Gold/Prismatic/...) is the one thing still known
    about a genuinely unrated augment: it's static game data, not a
    statistic, so it's never missing the way a tier can be. Naming it at
    least keeps a "no data" card from reading as completely blank.
    """
    if rank is None:
        pick = f"this {rarity_label} pick" if rarity_label else "this pick"
        return f"No OP.GG performance data for {pick} with {champion_name}."
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
#:
#: Known gap, deliberately not fixed here (2026-08-26 audit): a reroll
#: closes and reopens the picker with 3 different augments, and if that
#: happens faster than CLOSE_DEBOUNCE_TICKS * PICKER_POLL_SECONDS,
#: _picker_was_open never drops to False, so the new offer is never
#: re-captured and the stale pre-reroll badges keep showing. Fixing that
#: by re-capturing on any partial closed-streak was tried and reverted: it
#: reintroduces exactly the hover-flicker re-trigger this constant exists
#: to prevent (see test_a_new_open_edge_is_not_re_captured_while_already_open),
#: since a flicker and a reroll look identical from picker_is_open() alone.
#: A real fix needs to compare newly-identified augment ids against the
#: current recommendation's, not just picker presence.
CLOSE_DEBOUNCE_TICKS = 3


class AramAugmentAdvisor(ThreadedFeature):
    key = "aram_augment_advisor"
    title = "Aram Augments"
    category = "Automation"

    def __init__(self, lcu_client, config, on_event=None):
        super().__init__(lcu_client, config, on_event)
        self._champ_name_to_id = {}
        self._champ_name_to_alias = {}
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
                    # OP.GG's own site URL slug is exactly this alias
                    # lowercased (verified live against the whole roster:
                    # MonkeyKing -> monkeyking, DrMundo -> drmundo,
                    # KaiSa -> kaisa, RekSai -> reksai) - see
                    # core.opgg_scraper.
                    alias = champ.get("alias")
                    if alias:
                        self._champ_name_to_alias[champ["name"]] = alias.lower()
        except Exception:
            logger.exception("AramAugmentAdvisor: failed to load champion list")

    def _champion_id_for(self, champion_name):
        self._ensure_champion_list()
        return self._champ_name_to_id.get(champion_name)

    def _champion_alias_for(self, champion_name):
        self._ensure_champion_list()
        return self._champ_name_to_alias.get(champion_name)

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
        data (via `core.opgg_scraper`, covering its full 0-5 tier range)
        resolves most of it: usually only one candidate has data at all.
        When several do and they disagree, there is no honest way to pick,
        so the tier is dropped rather than guessed - the slot still shows,
        it just cannot win "best". Measured against a real champion pool,
        that last case hit 4 of 118 icon groups.
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

        # Nothing rated by either data source (see _tier_data_for_champion)
        # - a genuinely obscure champion+augment pairing OP.GG has too few
        # match samples for. Still worth showing (the icon match itself is
        # trustworthy), never worth recommending (there is nothing to
        # recommend it on).
        distinct_names = {augment_catalog.name(augment_id) for augment_id in candidates}
        return candidates[0], None, len(distinct_names) > 1

    def _tier_data_for_champion(self, champion_id, champion_alias):
        # Only an actually-populated result is trusted as cached - caching
        # `{}` from a transient failure (network blip, OP.GG down for a
        # moment) would otherwise mean one bad lookup on the first pick
        # disables augment data for every later pick (11, 15) the rest of
        # the game, long after the network recovered.
        if self._champion_id_this_game == champion_id and self._champion_augment_data:
            return self._champion_augment_data

        # Scraping OP.GG's own site first: it covers all 6 tiers (0-5),
        # where the MCP tool only ever returns 3-5 - see core.opgg_scraper
        # for the live diff that proved this. The MCP is a fallback for
        # when the scrape comes back empty (network down, or OP.GG changed
        # the page's internal structure), not a second opinion: both read
        # the same underlying OP.GG numbers, just with different coverage.
        data = {}
        if champion_alias:
            try:
                data = scrape_aram_augments(champion_alias)
            except Exception:
                logger.exception("AramAugmentAdvisor: OP.GG augment page scrape failed")
                data = {}
        if not data and champion_id:
            try:
                data = opgg_client.get_aram_augments(champion_id)
            except Exception:
                logger.exception("AramAugmentAdvisor: OP.GG MCP augment tier lookup failed")
                data = {}

        self._champion_id_this_game = champion_id
        self._champion_augment_data = data
        return data

    @staticmethod
    def _apply_rarity_fallback(augments, champion_name):
        """Only called when nothing on offer has a real OP.GG rank - the
        player still wants an answer, and rarity is the one signal left
        that's never missing (see RARITY_FALLBACK_RANK for why it's a
        legitimate, Riot-documented one, not an invented heuristic).

        Mutates the winning card's `rank`/`justification` in place to
        GUESS_RANK and a justification that names the rarity it was picked
        on, so it can never be mistaken for a real, data-backed pick.
        Returns whether a fallback pick was actually made - false when even
        rarity is unknown for every card (an ambiguous icon has no known
        rarity either, so it's excluded the same as everywhere else here).
        """
        candidates = [a for a in augments if not a["ambiguous"] and a["rarity"] in RARITY_FALLBACK_RANK]
        if not candidates:
            return False

        best = min(candidates, key=lambda a: RARITY_FALLBACK_RANK[a["rarity"]])
        best["rank"] = GUESS_RANK
        best["justification"] = (
            f"No OP.GG performance data for any of the 3 cards this game - picked as the best guess "
            f"since {best['rarity']} tends to be the strongest of the three ARAM Mayhem rarities. "
            f"Not a data-backed pick for {champion_name}."
        )
        return True

    def _build_recommendation(self, champion_name):
        identified = self._identify_offered_augments()
        if not identified:
            return None

        champion_id = self._champion_id_for(champion_name)
        champion_alias = self._champion_alias_for(champion_name)
        tier_data = self._tier_data_for_champion(champion_id, champion_alias) if (champion_id or champion_alias) else {}
        best_tier_best = _best_tier_performance(tier_data)

        augments = []
        best_slot, best_key = None, None
        for entry in identified:
            augment_id, tier, ambiguous = self._resolve_candidates(entry["candidates"], tier_data)
            performance = tier_data.get(augment_id, {}).get("performance") if tier is not None else None
            rank = None if ambiguous else augment_rank(tier, performance, best_tier_best)
            # Same reasoning as `name` above: an ambiguous card's identity
            # (candidates[0], picked arbitrarily) is not known, so a
            # specific rarity read off of it would be asserting a property
            # of an augment the code just declared it can't identify.
            rarity_label = None if ambiguous else RARITY_LABELS.get(augment_catalog.rarity(augment_id))
            justification = (
                "Several augments share this exact icon, so which one this is can't be told for sure."
                if ambiguous
                else augment_justification(champion_name, rank, performance, rarity_label)
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
                    "rarity": rarity_label,
                    "justification": justification,
                    "ambiguous": ambiguous,
                }
            )
            # Lower tier number is better, matching every other OP.GG tier
            # field already used in this codebase; performance only breaks
            # a tie within the same tier (e.g. OP vs a plain S offered
            # together), never crosses tiers - see augment_rank().
            #
            # Requiring `rank is not None` (not just `tier is not None`)
            # matters: a tier value TIER_RANKS doesn't map (an unexpected
            # scraper/MCP value) would otherwise still be eligible to win
            # "best" while its own justification text says there's no data
            # for it - contradicting the card in front of the player.
            if tier is not None and rank is not None:
                key = (tier, -(performance or 0))
                if best_key is None or key < best_key:
                    best_slot, best_key = entry["slot"], key

        best_slot_is_guess = False
        if best_slot is None:
            best_slot_is_guess = self._apply_rarity_fallback(augments, champion_name)
            if best_slot_is_guess:
                best_slot = next(a["slot"] for a in augments if a["rank"] == GUESS_RANK)

        return {
            "active": True,
            "champion": champion_name,
            "regions": AUGMENT_CARD_REGIONS,
            "augments": augments,
            "best_slot": best_slot,
            "best_slot_is_guess": best_slot_is_guess,
        }

    def _on_picker_opened(self, champion_name):
        best_partial = None
        for _attempt in range(CAPTURE_ATTEMPTS):
            if self._sleep(CAPTURE_SETTLE_SECONDS):
                return
            # The player may have picked (or this may be a transient bad
            # read - see CARD_BORDER_REQUIRED_COUNT) since the last check.
            # Treated as a failed attempt rather than an immediate bail: a
            # single False reading here used to end the whole pick with no
            # recommendation and no further retry, even though the picker
            # was still genuinely open and CAPTURE_ATTEMPTS budget remained.
            if not picker_is_open():
                continue

            recommendation = self._build_recommendation(champion_name)
            if recommendation is None:
                continue
            if len(recommendation.get("augments") or []) == len(AUGMENT_CARD_REGIONS):
                self._recommendation = recommendation
                if recommendation["best_slot"] is not None:
                    self.on_event(
                        "info",
                        f"Aram Augments: recommending slot {recommendation['best_slot'] + 1} for {champion_name}",
                    )
                return
            # A partial read (a card still fading in) used to be accepted
            # immediately, on the first attempt - potentially confidently
            # recommending the second-best of only 2 seen cards while a
            # third, unread card was actually the best. Worth trying again
            # for a complete read, but kept as a fallback in case every
            # remaining attempt does no better.
            best_partial = recommendation

        if best_partial is not None:
            self._recommendation = best_partial
            if best_partial["best_slot"] is not None:
                self.on_event(
                    "info",
                    f"Aram Augments: recommending slot {best_partial['best_slot'] + 1} for {champion_name}",
                )
        # Every attempt identified nothing at all - leave _recommendation at
        # None (its default) rather than show badges for a guess.

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

            if not self._handle_gameflow_phase(phase):
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

    def _handle_gameflow_phase(self, phase):
        """True if the rest of this tick's loop body should still run.

        A confirmed different phase (Lobby, ChampSelect, ...) really does
        mean the game ended, so it resets state. `phase is None` only means
        the LCU request itself failed (a transient hiccup) - not
        confirmation of anything - so it must not wipe a live
        recommendation the player is actively looking at mid-pick, which a
        bare `phase != "InProgress"` reset used to do on this path.
        """
        if phase != "InProgress":
            if phase is not None:
                self._reset_game_state()
            return False
        return True

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
