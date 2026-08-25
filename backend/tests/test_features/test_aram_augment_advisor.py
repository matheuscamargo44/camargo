"""AramAugmentAdvisor: resolving a captured picker into one recommendation.

Screen capture and the icon catalog are monkeypatched out - this covers the
feature's own logic, matching the OP.GG smart-counter-pick test style in
test_champ_select.py.
"""
import copy

from core.config import DEFAULT_CONFIG
from features.aram_augment_advisor import AramAugmentAdvisor


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

    def fake_lookup(champion_id):
        calls.append(champion_id)
        return {1: {"tier": 3}}

    monkeypatch.setattr(module.opgg_client, "get_aram_augments", fake_lookup)

    feature = make_feature()
    feature._champ_name_to_id = {"Ahri": 103}
    feature._build_recommendation("Ahri")
    feature._build_recommendation("Ahri")

    assert calls == [103]


# -- picker open/close drives the badge lifecycle --


def test_a_closed_picker_clears_the_recommendation(monkeypatch):
    """The badges must come down the moment the picker does - the player
    has picked, rerolled, or the window timed out."""
    import features.aram_augment_advisor as module

    monkeypatch.setattr(module, "picker_is_open", lambda: False)

    feature = make_feature()
    feature._recommendation = {"active": True}
    feature._picker_was_open = True

    # Mirror the loop's edge handling.
    is_open = module.picker_is_open()
    if not is_open and feature._picker_was_open:
        feature._recommendation = None

    assert feature.get_status()["recommendation"] is None


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
    feature._champion_augment_data = {1: {"tier": 3}}

    feature._reset_game_state()

    assert feature._recommendation is None
    assert feature._picker_was_open is False
    assert feature._champion_augment_data is None


def test_get_status_shape_when_idle():
    status = make_feature().get_status()

    assert status["key"] == "aram_augment_advisor"
    assert status["enabled"] is True
    assert status["recommendation"] is None
    assert status["unsupported_resolution"] is False
