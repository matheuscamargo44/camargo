from unittest.mock import MagicMock
from features.friend_requests import FriendRequestsManager
from features.party_invite import AutoPartyInvite
from features.random_skin import RandomSkinPicker
from features.ranked_presence import RankedPresence
from features.titles import ChallengeTitles


def test_party_invite_set_summoners():
    lcu = MagicMock()
    config = {"auto_party_invite": {"enabled": False, "summoners": ""}}
    feature = AutoPartyInvite(lcu, config)

    res = feature.set_summoners("DuoPartner#BR1, SubPlayer#BR1")
    assert res == "DuoPartner#BR1, SubPlayer#BR1"
    assert feature.get_status()["enabled"] is True
    assert "DuoPartner#BR1" in feature.get_status()["summoners"]


def test_random_skin_toggle():
    lcu = MagicMock()
    config = {"random_skin": {"enabled": False}}
    feature = RandomSkinPicker(lcu, config)

    assert feature.get_status()["enabled"] is False
    feature.toggle(True)
    assert feature.get_status()["enabled"] is True


def test_challenge_titles_get_titles_and_set():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"id": "10001", "name": "Flawless", "description": "Win without dying"},
    ]

    feature = ChallengeTitles(lcu, {})
    titles = feature.get_titles()
    assert len(titles) == 1
    assert titles[0]["name"] == "Flawless"

    lcu.lcu_request.return_value.json.return_value = {"topChallenges": [], "bannerId": ""}
    res = feature.set_title("10001")
    assert res["title_id"] == "10001"


def test_ranked_presence_set_tier():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 200

    feature = RankedPresence(lcu, {})
    res = feature.set_tier("CHALLENGER", "I")
    assert res["tier"] == "CHALLENGER"


def test_friend_requests_get_status_and_actions():
    lcu = MagicMock()
    lcu.is_league_connected.return_value = True
    lcu.lcu_request.return_value.status_code = 200
    lcu.lcu_request.return_value.json.return_value = [
        {"id": "req-1", "direction": "in"},
        {"id": "req-2", "direction": "in"},
    ]

    feature = FriendRequestsManager(lcu, {})
    status = feature.get_status()
    assert status["pending_count"] == 2

    acc = feature.accept_all()
    assert acc["accepted"] == 2

    rej = feature.reject_all()
    assert rej["rejected"] == 2
