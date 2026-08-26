"""AramAugmentAdvisor: resolving a captured picker into one recommendation.

Screen capture and the icon catalog are monkeypatched out - this covers the
feature's own logic, matching the OP.GG smart-counter-pick test style in
test_champ_select.py.
"""
import copy

import pytest

from core.config import DEFAULT_CONFIG
from features.aram_augment_advisor import AramAugmentAdvisor, augment_justification, augment_rank


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
    just a bare 'no data' with nothing else to go on."""
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
    assert augment["rank"] is None
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
    assert recommendation["best_slot"] is None


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
        return None if attempts["n"] < 3 else {"active": True, "best_slot": None}

    monkeypatch.setattr(module.AramAugmentAdvisor, "_build_recommendation", fake_build_recommendation)

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert attempts["n"] == 3
    assert feature._recommendation == {"active": True, "best_slot": None}


def test_gives_up_after_exhausting_capture_attempts(monkeypatch):
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: True)
    monkeypatch.setattr(module.AramAugmentAdvisor, "_build_recommendation", lambda self, name: None)

    feature = make_feature()
    feature._on_picker_opened("Ahri")

    assert feature._recommendation is None


def test_get_status_shape_when_idle():
    status = make_feature().get_status()

    assert status["key"] == "aram_augment_advisor"
    assert status["enabled"] is True
    assert status["recommendation"] is None
    assert status["unsupported_resolution"] is False
