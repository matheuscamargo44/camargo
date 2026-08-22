from unittest.mock import MagicMock
from features.aram_bench_swap import AramBenchSwap
from features.auto_honor import AutoHonor
from features.auto_play_again import AutoPlayAgain
from features.customization import ClientIcon, ProfileIcon
from features.loot import MassDisenchant
from features.presence_status import PresenceStatus


def test_mass_disenchant_get_status():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"type": "CHAMPION_RENTAL", "lootId": "CHAMPION_RENTAL_1", "count": 2},
        {"type": "SKIN_RENTAL", "lootId": "SKIN_RENTAL_101", "count": 1},
    ]

    feature = MassDisenchant(lcu, {})
    status = feature.get_status()

    assert status["key"] == "mass_disenchant"
    assert status["champion_shards"] == 2
    assert status["skin_shards"] == 1
    assert status["total_shards"] == 3


def test_auto_play_again_toggle():
    lcu = MagicMock()
    config = {"auto_play_again": {"enabled": False}}
    feature = AutoPlayAgain(lcu, config)

    assert feature.get_status()["enabled"] is False
    new_state = feature.toggle(True)
    assert new_state is True
    assert feature.get_status()["enabled"] is True


def test_aram_bench_swap_add_champion():
    lcu = MagicMock()
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"id": 103, "name": "Ahri"},
    ]
    config = {"aram_bench_swap": {"enabled": False, "champions": []}}
    feature = AramBenchSwap(lcu, config)

    target = feature.add_champion("Ahri")
    assert target == ["Ahri"]
    assert feature.get_status()["enabled"] is True
    assert feature.get_status()["target_champion"] == ["Ahri"]


def test_aram_bench_swap_resolve_champion_picks_the_first_one_on_the_bench():
    lcu = MagicMock()
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"id": 103, "name": "Ahri"},
        {"id": 86, "name": "Garen"},
    ]
    config = {"aram_bench_swap": {"enabled": True, "champions": ["Ahri", "Garen"]}}
    feature = AramBenchSwap(lcu, config)

    # Ahri isn't on the bench yet, but Garen is: fall through to Garen.
    bench = [{"championId": 86}]

    assert feature.resolve_champion(bench) == "Garen"


def test_presence_status_set_presence():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 200

    feature = PresenceStatus(lcu, {})
    res = feature.set_presence("mobile")
    assert res == "mobile"


def test_auto_honor_toggle():
    lcu = MagicMock()
    config = {"auto_honor": {"enabled": False}}
    feature = AutoHonor(lcu, config)

    assert feature.get_status()["enabled"] is False
    feature.toggle(True)
    assert feature.get_status()["enabled"] is True


def test_auto_honor_prefers_the_duo_partner():
    """Used to re-implement the choice inside the test: disabling the real
    logic left it green. Now it calls the feature."""
    feature = AutoHonor(MagicMock(), {"auto_honor": {"enabled": True}})
    feature.party_member_puuids = {"duo-puuid-123"}

    eligible = [
        {"summonerId": 111, "puuid": "random-puuid-111", "summonerName": "RandomAlly"},
        {"summonerId": 222, "puuid": "duo-puuid-123", "summonerName": "MyDuoPartner"},
    ]

    target = feature.pick_honor_target(eligible)

    assert target["summonerName"] == "MyDuoPartner"


def test_auto_honor_skips_when_no_known_party_member_is_eligible():
    """Guessing at a random teammate isn't "auto honoring your duo" — if the
    lobby was never seen (e.g. the app started after it formed), there's no
    reliable way to know who that was, so it should vote for no one.
    """
    feature = AutoHonor(MagicMock(), {"auto_honor": {"enabled": True}})

    eligible = [{"summonerId": 111, "summonerName": "RandomAlly"}]
    target = feature.pick_honor_target(eligible)

    assert target is None


def test_auto_honor_matches_a_party_member_by_summoner_id():
    feature = AutoHonor(MagicMock(), {"auto_honor": {"enabled": True}})
    feature.party_member_summoner_ids = {222}

    target = feature.pick_honor_target(
        [{"summonerId": 111, "summonerName": "Random"}, {"summonerId": 222, "summonerName": "Duo"}]
    )

    assert target["summonerName"] == "Duo"


def test_profile_and_client_icon_allow_zero():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 201

    profile_feat = ProfileIcon(lcu, {})
    client_feat = ClientIcon(lcu, {})

    assert profile_feat.change(0) == 0
    assert client_feat.change(0) == 0


def test_profile_icon_get_owned():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"itemId": 500},
        {"itemId": 1200},
    ]

    profile_feat = ProfileIcon(lcu, {})
    owned = profile_feat.get_owned_icons()

    assert 0 in owned
    assert 28 in owned
    assert 500 in owned
    assert 1200 in owned
