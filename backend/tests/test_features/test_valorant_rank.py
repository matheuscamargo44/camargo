from features.valorant_rank import ValorantRank

MMR = {
    "LatestCompetitiveUpdate": {
        "MatchID": "match-1",
        "MapID": "/Game/Maps/Ascent/Ascent",
        "TierAfterUpdate": 19,
        "RankedRatingAfterUpdate": 11,
        "RankedRatingEarned": -17,
    }
}

COMPETITIVE_UPDATES = {
    "Matches": [
        {
            "MatchID": "match-1",
            "MapID": "/Game/Maps/Ascent/Ascent",
            "TierAfterUpdate": 19,
            "RankedRatingAfterUpdate": 11,
            "RankedRatingEarned": -17,
        },
        {
            "MatchID": "match-2",
            "MapID": "/Game/Maps/Juliett/Juliett",
            "TierAfterUpdate": 19,
            "RankedRatingAfterUpdate": 28,
            "RankedRatingEarned": 18,
        },
    ]
}


class FakeValorantClient:
    def __init__(self, connected=True):
        self.connected = connected
        self.mmr = MMR
        self.competitive_updates = COMPETITIVE_UPDATES
        self.calls = []
        self.player_name = "camargo"
        self.player_tag = "amor"

    def is_connected(self):
        return self.connected

    def fetch_mmr(self):
        return self.mmr

    def fetch_competitive_updates(self, start_index=0, end_index=5):
        self.calls.append((start_index, end_index))
        return self.competitive_updates


def make_feature(connected=True):
    valorant = FakeValorantClient(connected=connected)
    feature = ValorantRank(valorant, {})
    return feature, valorant


def test_get_status_reports_current_tier_rr_and_player_identity():
    feature, _ = make_feature()

    assert feature.get_status() == {
        "key": "valorant_rank",
        "tier": 19,
        "rr": 11,
        "player_name": "camargo",
        "player_tag": "amor",
    }


def test_get_status_reports_nothing_when_disconnected():
    feature, _ = make_feature(connected=False)

    assert feature.get_status() == {
        "key": "valorant_rank",
        "tier": None,
        "rr": None,
        "player_name": "",
        "player_tag": "",
    }


def test_get_status_survives_a_fetch_error():
    feature, valorant = make_feature()
    valorant.fetch_mmr = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

    assert feature.get_status() == {
        "key": "valorant_rank",
        "tier": None,
        "rr": None,
        "player_name": "",
        "player_tag": "",
    }


def test_get_recent_form_maps_the_raw_rr_deltas():
    feature, valorant = make_feature()

    form = feature.get_recent_form(count=2)

    assert valorant.calls == [(0, 2)]
    assert form == [
        {"match_id": "match-1", "map_id": "/Game/Maps/Ascent/Ascent", "tier_after": 19, "rr_after": 11, "rr_change": -17},
        {"match_id": "match-2", "map_id": "/Game/Maps/Juliett/Juliett", "tier_after": 19, "rr_after": 28, "rr_change": 18},
    ]


def test_get_recent_form_clamps_the_count():
    feature, valorant = make_feature()

    feature.get_recent_form(count=999)

    assert valorant.calls == [(0, 20)]
