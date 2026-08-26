"""AramAugmentAdvisor: resolving a captured picker into one recommendation.

Screen capture and the icon catalog are monkeypatched out - this covers the
feature's own logic, matching the OP.GG smart-counter-pick test style in
test_champ_select.py.
"""
import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.aram_augment_advisor import (
    CLOSE_DEBOUNCE_TICKS,
    AramAugmentAdvisor,
    augment_justification,
    augment_rank,
)


class StubLCUClient:
    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        raise AssertionError("this test does not expect an LCU call")


def make_feature():
    feature = AramAugmentAdvisor(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.config["aram_augment_advisor"]["enabled"] = True
    feature._sleep = lambda seconds: False
    return feature


# -- ranks: tier -> letter, and carving OP out of S --


@pytest.mark.parametrize(
    "tier,expected", [(0, "S"), (1, "S"), (2, "A"), (3, "A"), (4, "B"), (5, "B")]
)
def test_augment_rank_maps_the_whole_scale_with_no_performance_data(tier, expected):
    """OP.GG's own site tracks six tiers (0 best - 5 worst), not three -
    the MCP tool alone only ever returns 3/4/5, silently omitting the three
    best (see core.opgg_scraper). Two raw tiers are grouped per letter so
    the on-screen vocabulary stays OP/S/A/B. Without a performance score to
    compare within tier 0, nothing can be singled out as OP, so it falls
    back to the plain tier mapping."""
    assert augment_rank(tier, performance=None, best_tier_best=None) == expected


def test_augment_rank_of_an_unrated_augment_is_nothing():
    assert augment_rank(None, performance=None, best_tier_best=None) is None


def test_the_top_tier_0_performer_is_op():
    """Checked live: tier-0 performance genuinely spreads (Viego 76.5-88.7),
    so the very best of it is worth calling out rather than lumping it in
    with the rest of S."""
    assert augment_rank(tier=0, performance=88.7, best_tier_best=88.7) == "OP"


def test_a_tied_top_performer_is_also_op():
    assert augment_rank(tier=0, performance=88.0, best_tier_best=88.7) == "OP"


def test_a_merely_good_tier_0_augment_is_s_not_op():
    assert augment_rank(tier=0, performance=76.5, best_tier_best=88.7) == "S"


def test_performance_never_promotes_across_tiers():
    """Tier 5 (the worst bucket) includes augments scoring well above tier
    0's real range - up to 170 against tier 0's ~89 max, checked live - a
    low-sample-size artifact, not genuine strength. A tier-5 augment must
    never outrank a tier-0 one just because its raw performance number is
    higher.
    """
    assert augment_rank(tier=5, performance=170.0, best_tier_best=88.7) == "B"


def test_lower_tier_numbers_are_better(monkeypatch):
    """Guards the direction of the comparison. OP.GG's numeric tier runs
    best-to-worst (T3 outperforms T5 on their own performance scores), so
    an inverted comparison here would recommend the worst card on offer.
    No performance data is supplied, so the tier-3 candidate reads as
    plain A rather than OP - see
    test_two_tier_0_cards_in_the_same_offer_break_the_tie_by_performance
    for the OP carve-out itself.
    """
    _patch_identification(
        monkeypatch,
        per_slot_candidates=[[1], [2], [3]],
        tier_data={1: {"tier": 5}, 2: {"tier": 3}, 3: {"tier": 4}},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["best_slot"] == 1
    assert recommendation["augments"][1]["rank"] == "A"
    assert [augment["rank"] for augment in recommendation["augments"]] == ["B", "A", "B"]


def test_two_tier_0_cards_in_the_same_offer_break_the_tie_by_performance(monkeypatch):
    """Tier alone can't pick a winner between two tier-0 (the best tier)
    cards offered together - the weaker of the two must not tie for best."""
    _patch_identification(
        monkeypatch,
        per_slot_candidates=[[1], [2], []],
        tier_data={1: {"tier": 0, "performance": 76.5}, 2: {"tier": 0, "performance": 88.7}},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["best_slot"] == 1
    assert recommendation["augments"][0]["rank"] == "S"
    assert recommendation["augments"][1]["rank"] == "OP"


# -- justification text --


def test_justification_cites_the_champion_and_real_score():
    text = augment_justification("Viego", "OP", 88.0)

    assert "Viego" in text
    assert "88" in text


def test_justification_for_each_rank_is_distinct():
    """Each rank should read as a different level of endorsement, not
    interchangeable copy."""
    texts = {rank: augment_justification("Viego", rank, 80.0) for rank in ("OP", "S", "A", "B")}

    assert len(set(texts.values())) == 4


def test_justification_for_an_unrated_augment_says_why_without_a_score():
    text = augment_justification("Viego", None, None)

    assert "Viego" in text


def test_justification_for_an_unrated_augment_names_the_rarity_when_known():
    """Rarity is static game data, present for every augment regardless of
    whether OP.GG has enough samples to rate it - so an unrated card need
    not read as completely blank."""
    text = augment_justification("Viego", None, None, rarity_label="Prismatic")

    assert "Prismatic" in text
    assert "Viego" in text


def test_justification_for_an_unrated_augment_without_a_known_rarity_still_reads_fine():
    text = augment_justification("Viego", None, None, rarity_label=None)

    assert "None" not in text


@pytest.mark.parametrize("raw,expected", [("kSilver", "Silver"), ("kGold", "Gold"), ("kPrismatic", "Prismatic")])
def test_rarity_labels_cover_the_common_rarities(raw, expected):
    from features.aram_augment_advisor import RARITY_LABELS

    assert RARITY_LABELS[raw] == expected


def test_build_recommendation_includes_the_rarity_for_an_unrated_card(monkeypatch):
    """End-to-end: an unrated augment's card still carries its rarity, not
    just a bare 'no data' with nothing else to go on. All 3 slots here
    resolve to the same Prismatic augment id, so the rarity fallback (see
    test_rarity_fallback_* below) also kicks in - the first of the 3
    identical cards becomes the guess."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: [1])
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: "Mystery Pick")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: "http://icon/1")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kPrismatic")
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: {})  # nothing rated

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}
    recommendation = feature._build_recommendation("Ahri")

    augment = recommendation["augments"][0]
    assert augment["rank"] == module.GUESS_RANK
    assert augment["rarity"] == "Prismatic"
    assert "Prismatic" in augment["justification"]


# -- _resolve_candidates: the ambiguity policy --


def test_a_single_rated_candidate_resolves_to_its_tier():
    resolved_id, tier, ambiguous = AramAugmentAdvisor._resolve_candidates(
        [10, 20], {10: {"tier": 3}}
    )

    assert (resolved_id, tier, ambiguous) == (10, 3, False)


def test_tied_candidates_agreeing_on_tier_are_not_ambiguous():
    """Several augments sharing identical art is only a problem if they
    disagree - if the tier is the same either way, the answer is the same
    either way."""
    resolved_id, tier, ambiguous = AramAugmentAdvisor._resolve_candidates(
        [10, 20], {10: {"tier": 4}, 20: {"tier": 4}}
    )

    assert tier == 4
    assert ambiguous is False


def test_tied_candidates_disagreeing_on_tier_drop_the_tier():
    """No honest way to pick between them, so the slot shows but cannot
    win 'best' - never show a tier that might belong to the other twin."""
    _, tier, ambiguous = AramAugmentAdvisor._resolve_candidates(
        [10, 20], {10: {"tier": 3}, 20: {"tier": 5}}
    )

    assert tier is None
    assert ambiguous is True


def test_unrated_candidates_resolve_without_a_tier(monkeypatch):
    """OP.GG only rates tier 3 and above, so an unrated augment is a real
    answer ('worse than the rated cards'), not a lookup failure."""
    import features.aram_augment_advisor as module

    # This branch consults the catalog for names; without this the call
    # would fall through to a live fetch of the whole icon set.
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")

    resolved_id, tier, ambiguous = AramAugmentAdvisor._resolve_candidates([10], {})

    assert (resolved_id, tier, ambiguous) == (10, None, False)


def test_unrated_candidates_sharing_art_are_ambiguous(monkeypatch):
    """Nothing rated and several distinct names behind the same art: the
    icon is right but naming one of them would be a guess."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")

    _, tier, ambiguous = AramAugmentAdvisor._resolve_candidates([10, 20], {})

    assert tier is None
    assert ambiguous is True


# -- _build_recommendation --


def _patch_identification(monkeypatch, per_slot_candidates, tier_data):
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())

    calls = iter(per_slot_candidates)
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: next(calls))
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: f"http://icon/{augment_id}")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kGold")
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: tier_data)


def test_best_slot_is_the_lowest_tier_number(monkeypatch):
    _patch_identification(
        monkeypatch,
        per_slot_candidates=[[1], [2], [3]],
        tier_data={1: {"tier": 4}, 2: {"tier": 3}, 3: {"tier": 5}},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["best_slot"] == 1
    assert recommendation["champion"] == "Ahri"
    assert [augment["tier"] for augment in recommendation["augments"]] == [4, 3, 5]


def test_an_ambiguous_slot_cannot_win_best(monkeypatch):
    """Slot 0 would have the best tier if we trusted one twin, but the
    twins disagree - so slot 1's honest tier wins instead."""
    _patch_identification(
        monkeypatch,
        per_slot_candidates=[[1, 9], [2], [3]],
        tier_data={1: {"tier": 1}, 9: {"tier": 5}, 2: {"tier": 3}, 3: {"tier": 4}},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["augments"][0]["ambiguous"] is True
    assert recommendation["augments"][0]["tier"] is None
    assert recommendation["best_slot"] == 1


def test_an_unmapped_tier_cannot_win_best_even_though_it_has_a_number(monkeypatch):
    """An out-of-range tier value (not in TIER_RANKS) reads as unrated - it
    must not still be eligible to win "best" while its own justification
    text says there's no data for it."""
    _patch_identification(
        monkeypatch,
        per_slot_candidates=[[1], [2], []],
        tier_data={1: {"tier": 99, "performance": 999}, 2: {"tier": 4}},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["augments"][0]["rank"] is None
    assert recommendation["best_slot"] == 1


def test_an_ambiguous_card_does_not_assert_a_specific_rarity(monkeypatch):
    """Mirrors `name` being nulled for the same case: an ambiguous card's
    identity isn't known, so neither is a specific property of it - showing
    a definite rarity here would be a coin flip presented as fact."""
    _patch_identification(
        monkeypatch,
        per_slot_candidates=[[1, 9], [2], []],
        tier_data={1: {"tier": 1}, 9: {"tier": 5}, 2: {"tier": 3}},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["augments"][0]["ambiguous"] is True
    assert recommendation["augments"][0]["name"] is None
    assert recommendation["augments"][0]["rarity"] is None


def test_nothing_identified_yields_no_recommendation(monkeypatch):
    """A capture that matches nothing must produce no badge at all rather
    than a guess."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: [])

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("must not look up tiers with nothing identified")

    monkeypatch.setattr(module.opgg_client, "get_aram_augments", must_not_be_called)

    assert make_feature()._build_recommendation("Ahri") is None


def test_an_opgg_failure_still_shows_the_identified_augments(monkeypatch):
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: [1])
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: "Some Augment")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: "http://icon/1")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kGold")

    def raise_error(champion_id):
        raise RuntimeError("OP.GG unreachable")

    monkeypatch.setattr(module.opgg_client, "get_aram_augments", raise_error)

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}
    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["augments"][0]["tier"] is None
    # No real tier data exists (OP.GG unreachable), so the rarity fallback
    # picks this card as the best guess rather than leaving best_slot empty
    # - see test_rarity_fallback_wins_when_nothing_is_data_backed below.
    assert recommendation["best_slot"] == 0
    assert recommendation["best_slot_is_guess"] is True


def test_tier_data_is_fetched_once_per_champion(monkeypatch):
    import features.aram_augment_advisor as module

    calls = []
    monkeypatch.setattr(module, "capture_region", lambda box: object())
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: [1])
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: "A")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: "u")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kGold")

    def fake_lookup(champion_id):
        calls.append(champion_id)
        return {1: {"tier": 3}}

    monkeypatch.setattr(module.opgg_client, "get_aram_augments", fake_lookup)

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}
    feature._build_recommendation("Ahri")
    feature._build_recommendation("Ahri")

    assert calls == [103]


def test_an_empty_lookup_result_is_not_cached_and_is_retried(monkeypatch):
    """A transient failure (both the scrape and the MCP fallback come back
    empty) must not be trusted as "this champion genuinely has no data" for
    the rest of the match - that would disable augment data for every later
    pick (level 11, 15) from one bad network moment on the first."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: [1])
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: "A")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: "u")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kGold")

    calls = []

    def fake_lookup(champion_id):
        calls.append(champion_id)
        return {} if len(calls) == 1 else {1: {"tier": 3}}

    monkeypatch.setattr(module.opgg_client, "get_aram_augments", fake_lookup)

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}
    first = feature._build_recommendation("Ahri")
    second = feature._build_recommendation("Ahri")

    assert calls == [103, 103]  # retried, not served from a cached {}
    # No real tier data on the first call - the rarity fallback picks a
    # guess rather than leaving it truly unranked.
    assert first["augments"][0]["rank"] == module.GUESS_RANK
    assert second["augments"][0]["rank"] == "A"


# -- rarity fallback: still pointing at *something* when nothing is data-backed --


def _patch_identification_with_rarities(monkeypatch, per_slot_ids, rarities):
    """Like _patch_identification, but each slot resolves to its own
    augment id with its own rarity, and OP.GG has nothing for any of them -
    the exact situation the rarity fallback exists for."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    calls = iter([[augment_id] for augment_id in per_slot_ids])
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: next(calls))
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: f"http://icon/{augment_id}")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: rarities[augment_id])
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: {})


def test_rarity_fallback_picks_the_highest_rarity_when_nothing_has_real_data(monkeypatch):
    _patch_identification_with_rarities(
        monkeypatch,
        per_slot_ids=[1, 2, 3],
        rarities={1: "kSilver", 2: "kPrismatic", 3: "kGold"},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["best_slot"] == 1  # the Prismatic card
    assert recommendation["best_slot_is_guess"] is True
    assert recommendation["augments"][1]["rank"] == "GUESS"
    assert "Prismatic" in recommendation["augments"][1]["justification"]


def test_rarity_fallback_does_not_touch_the_other_cards(monkeypatch):
    _patch_identification_with_rarities(
        monkeypatch,
        per_slot_ids=[1, 2, 3],
        rarities={1: "kSilver", 2: "kPrismatic", 3: "kGold"},
    )
    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["augments"][0]["rank"] is None  # Silver - still a plain "no data" card
    assert recommendation["augments"][2]["rank"] is None  # Gold - still a plain "no data" card


def test_rarity_fallback_never_fires_when_a_real_rank_already_won(monkeypatch):
    """The fallback is a last resort - if even one card has real OP.GG
    data, that's what wins, never a rarity guess."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    calls = iter([[1], [2], []])
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: next(calls))
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: f"http://icon/{augment_id}")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kSilver" if augment_id == 1 else "kPrismatic")
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: {1: {"tier": 4}})

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["best_slot"] == 0  # the real "B" rank, not the Prismatic guess
    assert recommendation["best_slot_is_guess"] is False


def test_rarity_fallback_has_nothing_to_go_on_when_rarity_is_also_unknown(monkeypatch):
    """An unrecognized rarity string (see RARITY_LABELS) degrades to
    omitting the rarity entirely - if that's true for every card, there is
    truly nothing left to guess with, and best_slot stays honestly empty."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    calls = iter([[1], [2], [3]])
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: next(calls))
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: f"http://icon/{augment_id}")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kUnknownFutureRarity")
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: {})

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}

    recommendation = feature._build_recommendation("Ahri")

    assert recommendation["best_slot"] is None
    assert recommendation["best_slot_is_guess"] is False


# -- _tier_data_for_champion: scraping OP.GG's own site first, MCP as fallback --


def test_scraped_data_is_preferred_and_the_mcp_is_not_called(monkeypatch):
    """core.opgg_scraper covers all six tiers; the MCP tool only 3-5 (see
    module docstring) - so a successful scrape must win outright, with the
    MCP never even called."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "scrape_aram_augments", lambda alias: {1: {"tier": 0, "performance": 88.7}})

    def must_not_be_called(champion_id):
        raise AssertionError("must not fall back to the MCP when the scrape succeeded")

    monkeypatch.setattr(module.opgg_client, "get_aram_augments", must_not_be_called)

    feature = make_feature()
    data = feature._tier_data_for_champion(champion_id=103, champion_alias="ahri")

    assert data == {1: {"tier": 0, "performance": 88.7}}


def test_falls_back_to_the_mcp_when_the_scrape_comes_back_empty(monkeypatch):
    """A scrape failure (network down, or OP.GG's page structure changed)
    must not lose the feature entirely - the narrower MCP data is still
    better than nothing."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "scrape_aram_augments", lambda alias: {})
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: {1: {"tier": 3}})

    feature = make_feature()
    data = feature._tier_data_for_champion(champion_id=103, champion_alias="ahri")

    assert data == {1: {"tier": 3}}


def test_falls_back_to_the_mcp_when_no_alias_is_known(monkeypatch):
    """Some champion lookups may only resolve an id, not an alias (e.g. an
    LCU response missing the field) - the feature must still work off the
    MCP rather than skip tier data entirely."""
    import features.aram_augment_advisor as module

    def must_not_be_called(alias):
        raise AssertionError("must not scrape without an alias")

    monkeypatch.setattr(module, "scrape_aram_augments", must_not_be_called)
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: {1: {"tier": 3}})

    feature = make_feature()
    data = feature._tier_data_for_champion(champion_id=103, champion_alias=None)

    assert data == {1: {"tier": 3}}


def test_champion_alias_is_read_from_the_champion_list():
    """OP.GG's URL slug is the champion's DataDragon alias lowercased -
    see core.opgg_scraper."""
    feature = make_feature()
    feature._champ_name_to_alias = {"Kai'Sa": "kaisa"}

    assert feature._champion_alias_for("Kai'Sa") == "kaisa"
    assert feature._champion_alias_for("Unknown Champion") is None


# -- picker open/close drives the badge lifecycle --


def test_a_sustained_closed_reading_clears_the_recommendation():
    """The badges must come down once the picker genuinely closes - the
    player has picked, rerolled, or the window timed out."""
    feature = make_feature()
    feature._recommendation = {"active": True}
    feature._picker_was_open = True

    from features.aram_augment_advisor import CLOSE_DEBOUNCE_TICKS

    for _ in range(CLOSE_DEBOUNCE_TICKS):
        feature._handle_picker_state(False, "Ahri")

    assert feature.get_status()["recommendation"] is None
    assert feature._picker_was_open is False


def test_a_single_bad_frame_does_not_clear_the_recommendation():
    """Hovering a card to compare it enlarges it, which can make a single
    frame read as 'closed' even though the picker is still up (confirmed
    live: a real session re-triggered a capture 4 times in 6s for what was
    one continuous pick). One bad reading must not wipe the badges the
    player is actively looking at.
    """
    feature = make_feature()
    feature._recommendation = {"active": True}
    feature._picker_was_open = True

    feature._handle_picker_state(False, "Ahri")  # one bad frame
    assert feature.get_status()["recommendation"] == {"active": True}

    feature._handle_picker_state(True, "Ahri")  # picker still open really

    assert feature.get_status()["recommendation"] == {"active": True}
    assert feature._closed_streak == 0


def test_a_new_open_edge_is_not_re_captured_while_already_open(monkeypatch):
    """A momentary bad frame must not make the picker look like it closed
    and reopened - that would recapture (and, before this, log a second
    'recommending' event) for what the player experiences as one
    continuous pick."""
    import features.aram_augment_advisor as module

    calls = []
    monkeypatch.setattr(module.AramAugmentAdvisor, "_on_picker_opened", lambda self, name: calls.append(name))

    feature = make_feature()
    feature._handle_picker_state(True, "Ahri")
    feature._handle_picker_state(False, "Ahri")  # one bad frame, below the debounce threshold
    feature._handle_picker_state(True, "Ahri")

    assert calls == ["Ahri"]


def test_capture_is_abandoned_if_the_picker_closes_during_settle(monkeypatch):
    """The settle delay gives the picker time to finish drawing, but the
    player may pick during it - capturing then would grab the wrong
    screen."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: False)

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("must not capture after the picker closed")

    monkeypatch.setattr(module, "capture_region", must_not_be_called)

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert feature._recommendation is None


def test_game_state_reset_clears_everything():
    feature = make_feature()
    feature._recommendation = {"active": True}
    feature._picker_was_open = True
    feature._closed_streak = 2
    feature._champion_augment_data = {1: {"tier": 3}}

    feature._reset_game_state()

    assert feature._recommendation is None
    assert feature._picker_was_open is False
    assert feature._closed_streak == 0
    assert feature._champion_augment_data is None
    assert feature._offer_signature is None
    assert feature._pending_offer_signature is None


# -- reroll: the offer changing under a picker that never reads as closed --


def _patch_reads(monkeypatch, reads, tier_data):
    """Scripts successive whole-screen reads. Each entry in `reads` is one
    call to _identify_offered_augments(), given as the candidate list per
    slot - an empty list being a slot that identified as nothing, which is
    what a hovered (enlarged) card really looks like.
    """
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "capture_region", lambda box: object())
    per_slot = iter([candidates for read in reads for candidates in read])
    monkeypatch.setattr(module.augment_catalog, "identify", lambda image: next(per_slot))
    monkeypatch.setattr(module.augment_catalog, "name", lambda augment_id: f"Augment {augment_id}")
    monkeypatch.setattr(module.augment_catalog, "icon_url", lambda augment_id: f"http://icon/{augment_id}")
    monkeypatch.setattr(module.augment_catalog, "rarity", lambda augment_id: "kGold")
    monkeypatch.setattr(module.opgg_client, "get_aram_augments", lambda champion_id: tier_data)


def _feature_showing(monkeypatch, reads, tier_data):
    """A feature mid-pick: the picker is open and a recommendation built
    from the first scripted read is already on screen."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: True)
    _patch_reads(monkeypatch, reads, tier_data)

    events = []
    feature = make_feature()
    feature.on_event = lambda level, message: events.append(message)
    feature._champ_name_to_id = {"Ahri": 103}
    feature._handle_picker_state(True, "Ahri")  # the opening capture
    return feature, events


OFFER = [[1], [2], [3]]
REROLLED = [[4], [5], [6]]
TIERS = {1: {"tier": 4}, 2: {"tier": 3}, 3: {"tier": 5}, 4: {"tier": 5}, 5: {"tier": 4}, 6: {"tier": 0}}


def test_a_reroll_replaces_the_stale_recommendation(monkeypatch):
    """The bug this exists for: rerolling swaps all 3 cards, but the picker
    never reads as closed for the 3 straight ticks CLOSE_DEBOUNCE_TICKS
    needs - so the pre-reroll badges used to sit there over cards that were
    no longer on screen, for the rest of the pick.
    """
    feature, events = _feature_showing(monkeypatch, [OFFER, REROLLED, REROLLED], TIERS)
    assert feature._recommendation["best_slot"] == 1  # tier 3 wins the first offer

    feature._handle_picker_state(True, "Ahri")
    feature._handle_picker_state(True, "Ahri")

    assert [a["augment_id"] for a in feature._recommendation["augments"]] == [4, 5, 6]
    assert feature._recommendation["best_slot"] == 2  # augment 6, tier 0
    assert events[-1] == "Aram Augments: offer changed, now recommending slot 3 for Ahri"


def test_a_reroll_is_not_acted_on_until_it_repeats(monkeypatch):
    """One frame showing something new is not yet a reroll - see
    REOFFER_CONFIRM_TICKS. Acting on a single frame is what reintroduces
    the re-trigger the close debounce exists to prevent."""
    feature, _ = _feature_showing(monkeypatch, [OFFER, REROLLED], TIERS)

    feature._handle_picker_state(True, "Ahri")

    assert [a["augment_id"] for a in feature._recommendation["augments"]] == [1, 2, 3]


def test_a_steady_picker_never_rebuilds_the_same_offer(monkeypatch):
    """The common case by far: the player is just looking at the cards.
    Re-reading the screen must be a no-op, not a rebuild - a rebuild would
    re-log a 'recommending' event every tick."""
    feature, events = _feature_showing(monkeypatch, [OFFER, OFFER, OFFER], TIERS)
    before = feature._recommendation

    feature._handle_picker_state(True, "Ahri")
    feature._handle_picker_state(True, "Ahri")

    assert feature._recommendation is before
    assert len(events) == 1  # only the original capture's


def test_a_hovered_card_is_not_mistaken_for_a_new_offer(monkeypatch):
    """Hovering a card to compare it draws it enlarged, so its glyph no
    longer lines up with the fixed crop and identifies as nothing. That
    partial read must never look like the offer changed."""
    hovering = [[1], [], [3]]
    feature, events = _feature_showing(monkeypatch, [OFFER, hovering, hovering], TIERS)

    feature._handle_picker_state(True, "Ahri")
    feature._handle_picker_state(True, "Ahri")

    assert [a["augment_id"] for a in feature._recommendation["augments"]] == [1, 2, 3]
    assert len(events) == 1


def test_a_reroll_is_still_caught_across_its_own_fade_in(monkeypatch):
    """The two confirming reads are not necessarily adjacent: a reroll's
    own fade-in produces partial frames between them. A partial read must
    not reset the streak, or a slow fade would keep the stale badges up."""
    fading = [[4], [], [6]]
    feature, _ = _feature_showing(monkeypatch, [OFFER, REROLLED, fading, REROLLED], TIERS)

    feature._handle_picker_state(True, "Ahri")  # new offer, first sighting
    feature._handle_picker_state(True, "Ahri")  # mid-fade, inconclusive
    feature._handle_picker_state(True, "Ahri")  # confirmed

    assert [a["augment_id"] for a in feature._recommendation["augments"]] == [4, 5, 6]


def test_a_closed_picker_forgets_the_offer_it_was_showing(monkeypatch):
    """Otherwise the next picker to open would be diffed against a dead
    offer's identity rather than captured fresh."""
    feature, _ = _feature_showing(monkeypatch, [OFFER], TIERS)
    assert feature._offer_signature is not None

    for _ in range(CLOSE_DEBOUNCE_TICKS):
        feature._handle_picker_state(False, "Ahri")

    assert feature._offer_signature is None


def test_the_reroll_check_is_skipped_entirely_with_nothing_on_screen(monkeypatch):
    """No recommendation means nothing to compare against - and, more to
    the point, no reason to pay for a screen capture every tick."""
    import features.aram_augment_advisor as module

    def must_not_capture(box):
        raise AssertionError("must not capture with no recommendation showing")

    feature = make_feature()
    feature._picker_was_open = True
    monkeypatch.setattr(module, "capture_region", must_not_capture)

    feature._handle_picker_state(True, "Ahri")


# -- _on_picker_opened: retrying a bad capture --


def test_a_failed_capture_is_retried_before_giving_up(monkeypatch):
    """A capture that lands on a half-drawn frame (fade-in, or right after
    a reroll) can legitimately identify nothing even with the picker
    genuinely open - worth trying again, not giving up on the whole pick.
    """
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: True)
    attempts = {"n": 0}

    def fake_build_recommendation(self, champion_name):
        attempts["n"] += 1
        return None if attempts["n"] < 3 else {"active": True, "best_slot": None, "augments": [1, 2, 3]}

    monkeypatch.setattr(module.AramAugmentAdvisor, "_build_recommendation", fake_build_recommendation)

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert attempts["n"] == 3
    assert feature._recommendation == {"active": True, "best_slot": None, "augments": [1, 2, 3]}


def test_gives_up_after_exhausting_capture_attempts(monkeypatch):
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: True)
    monkeypatch.setattr(module.AramAugmentAdvisor, "_build_recommendation", lambda self, name: None)

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert feature._recommendation is None


def test_a_single_false_picker_reading_during_settle_does_not_abandon_the_whole_pick(monkeypatch):
    """picker_is_open() reading False on one settle check used to return
    from the whole function immediately, permanently skipping this pick -
    even though the picker was still genuinely open a moment later. It must
    be treated as one failed attempt, not a final answer."""
    import features.aram_augment_advisor as module

    reads = iter([False, True, True])
    monkeypatch.setattr(module, "picker_is_open", lambda: next(reads))
    monkeypatch.setattr(
        module.AramAugmentAdvisor,
        "_build_recommendation",
        lambda self, name: {"active": True, "best_slot": None, "augments": [1, 2, 3]},
    )

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert feature._recommendation == {"active": True, "best_slot": None, "augments": [1, 2, 3]}


def test_a_partial_capture_keeps_trying_for_a_complete_one(monkeypatch):
    """A capture that only identified 2 of 3 cards (one still fading in)
    used to be accepted immediately - potentially confidently recommending
    the second-best of only 2 seen cards while the unread third was
    actually the best. It should try again for a complete read first."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: True)
    attempts = {"n": 0}

    def fake_build_recommendation(self, champion_name):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return {"active": True, "best_slot": 1, "augments": [1, 2]}  # partial
        return {"active": True, "best_slot": 0, "augments": [1, 2, 3]}  # complete

    monkeypatch.setattr(module.AramAugmentAdvisor, "_build_recommendation", fake_build_recommendation)

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert attempts["n"] == 2  # stopped retrying once a complete read landed
    assert feature._recommendation == {"active": True, "best_slot": 0, "augments": [1, 2, 3]}


def test_a_partial_capture_is_used_as_a_fallback_if_never_completed(monkeypatch):
    """Better than nothing: if every attempt only ever sees a partial
    offer, the last one is still shown rather than no recommendation at
    all."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: True)
    monkeypatch.setattr(
        module.AramAugmentAdvisor,
        "_build_recommendation",
        lambda self, name: {"active": True, "best_slot": 1, "augments": [1, 2]},
    )

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert feature._recommendation == {"active": True, "best_slot": 1, "augments": [1, 2]}


# -- _handle_gameflow_phase: only a confirmed phase change resets state --


def test_a_confirmed_different_phase_resets_state():
    feature = make_feature()
    feature._recommendation = {"active": True}
    feature._picker_was_open = True

    still_relevant = feature._handle_gameflow_phase("Lobby")

    assert still_relevant is False
    assert feature._recommendation is None
    assert feature._picker_was_open is False


def test_a_failed_phase_read_does_not_reset_a_live_recommendation():
    """phase is None only when the LCU request itself failed - a transient
    hiccup, not confirmation the game ended - so it must not wipe a
    recommendation the player is actively looking at mid-pick."""
    feature = make_feature()
    feature._recommendation = {"active": True}
    feature._picker_was_open = True

    still_relevant = feature._handle_gameflow_phase(None)

    assert still_relevant is False  # still skips the rest of this tick
    assert feature._recommendation == {"active": True}  # but doesn't wipe it
    assert feature._picker_was_open is True


def test_in_progress_phase_lets_the_tick_continue():
    feature = make_feature()

    assert feature._handle_gameflow_phase("InProgress") is True


def test_get_status_shape_when_idle():
    status = make_feature().get_status()

    assert status["key"] == "aram_augment_advisor"
    assert status["enabled"] is True
    assert status["recommendation"] is None
    assert status["unsupported_resolution"] is False
