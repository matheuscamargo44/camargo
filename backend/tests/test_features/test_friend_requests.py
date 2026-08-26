"""FriendRequestsManager: incoming/outgoing direction filtering."""
from features.friend_requests import FriendRequestsManager


class StubLCUClient:
    def __init__(self, requests):
        self._requests = requests
        self.calls = []

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=None):
        self.calls.append((method, endpoint))
        if method == "GET" and endpoint == "/lol-chat/v2/friend-requests":
            return _Response(200, self._requests)
        return _Response(204, None)


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_feature(requests):
    feature = FriendRequestsManager(StubLCUClient(requests), {})
    return feature


def test_pending_count_only_counts_incoming_requests():
    """The bug: the fallback `len(incoming) if incoming else len(reqs)`
    discarded the direction filter entirely whenever there were 0 incoming
    requests, so 3 purely-outgoing requests misreported as "3 pending"."""
    feature = make_feature([
        {"puuid": "a", "direction": "OUTGOING"},
        {"puuid": "b", "direction": "OUTGOING"},
        {"puuid": "c", "direction": "OUTGOING"},
    ])

    assert feature.get_status()["pending_count"] == 0


def test_pending_count_counts_a_mix_correctly():
    feature = make_feature([
        {"puuid": "a", "direction": "OUTGOING"},
        {"puuid": "b", "direction": "INCOMING"},
    ])

    assert feature.get_status()["pending_count"] == 1


def test_reject_all_never_touches_an_outgoing_request():
    """The bug: reject_all/accept_all applied to every pending request with
    no direction filter, so "Reject all" could withdraw the user's own
    sent invites."""
    feature = make_feature([
        {"puuid": "sent-by-me", "direction": "OUTGOING"},
    ])

    result = feature.reject_all()

    assert result == {"rejected": 0}
    assert ("DELETE", "/lol-chat/v2/friend-requests/sent-by-me") not in feature.lcu.calls


def test_reject_all_rejects_an_incoming_request():
    feature = make_feature([
        {"puuid": "sent-to-me", "direction": "INCOMING"},
    ])

    result = feature.reject_all()

    assert result == {"rejected": 1}
    assert ("DELETE", "/lol-chat/v2/friend-requests/sent-to-me") in feature.lcu.calls


def test_accept_all_never_touches_an_outgoing_request():
    feature = make_feature([
        {"puuid": "sent-by-me", "direction": "OUTGOING"},
    ])

    result = feature.accept_all()

    assert result == {"accepted": 0}
