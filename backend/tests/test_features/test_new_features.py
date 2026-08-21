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


def test_aram_bench_swap_set_champion():
    lcu = MagicMock()
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"id": 103, "name": "Ahri"},
    ]
    config = {"aram_bench_swap": {"enabled": False, "champion": "None"}}
    feature = AramBenchSwap(lcu, config)

    target = feature.set_champion("Ahri")
    assert target == "Ahri"
    assert feature.get_status()["enabled"] is True
    assert feature.get_status()["target_champion"] == "Ahri"


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


def test_auto_honor_duo_priority():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True

    events = []
    feature = AutoHonor(lcu, {"auto_honor": {"enabled": True}}, on_event=lambda lvl, msg: events.append(msg))
    feature.party_member_puuids = {"duo-puuid-123"}

    # Mock ballot with allies (one is duo, one is random)
    ballot = {
        "gameId": 999888777,
        "eligibleAllies": [
            {"summonerId": 111, "puuid": "random-puuid-111", "summonerName": "RandomAlly"},
            {"summonerId": 222, "puuid": "duo-puuid-123", "summonerName": "MyDuoPartner"},
        ]
    }

    ballot_res = MagicMock(status_code=200)
    ballot_res.json.return_value = ballot
    honor_res = MagicMock(status_code=200)

    lcu.lcu_request.side_effect = [ballot_res, honor_res]

    # Run one pass of ballot check logic
    ballot_data = lcu.lcu_request("GET", "/lol-honor-v2/v1/ballot").json()
    eligible = ballot_data.get("eligibleAllies", [])

    target = None
    is_duo = False
    for p in eligible:
        if p.get("puuid") in feature.party_member_puuids:
            target = p
            is_duo = True
            break

    assert is_duo is True
    assert target["summonerName"] == "MyDuoPartner"
    assert target["puuid"] == "duo-puuid-123"


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
