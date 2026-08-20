from unittest.mock import MagicMock
from features.aram_bench_swap import AramBenchSwap
from features.auto_honor import AutoHonor
from features.auto_play_again import AutoPlayAgain
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
