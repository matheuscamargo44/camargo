"""AutoPlayAgain._handle_phase: the gameflow-phase state machine that
drives play-again, extracted from _loop() for direct testing."""
import copy

from core.config import DEFAULT_CONFIG
from features.auto_play_again import AutoPlayAgain


class StubLCUClient:
    def __init__(self):
        self.requests = []
        self.play_again_status = 200

    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        self.requests.append((method, endpoint))
        if endpoint == "/lol-lobby/v2/play-again":
            return _Response(self.play_again_status)
        return _Response(200)


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def make_feature():
    feature = AutoPlayAgain(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature._sleep = lambda seconds: False
    return feature


def _play_again_calls(feature):
    return [r for r in feature.lcu.requests if r == ("POST", "/lol-lobby/v2/play-again")]


def test_the_gameflow_sequence_only_fires_play_again_once():
    """The bug: WaitingForStats and EndOfGame both trigger a POST, so the
    normal end-of-game sequence (WaitingForStats -> EndOfGame) fired it
    twice - and the first one raced AutoHonor's ballot, which only appears
    after the client actually leaves the post-game screen."""
    feature = make_feature()

    feature._handle_phase("WaitingForStats")
    feature._handle_phase("EndOfGame")

    assert len(_play_again_calls(feature)) == 1


def test_a_new_game_cycle_can_fire_play_again_again():
    feature = make_feature()
    feature._handle_phase("WaitingForStats")
    feature._handle_phase("EndOfGame")
    feature._handle_phase("Lobby")  # back in lobby - a genuinely new cycle

    feature._handle_phase("WaitingForStats")

    assert len(_play_again_calls(feature)) == 2


def test_repeated_reads_of_the_same_phase_do_not_refire():
    feature = make_feature()

    feature._handle_phase("WaitingForStats")
    feature._handle_phase("WaitingForStats")
    feature._handle_phase("WaitingForStats")

    assert len(_play_again_calls(feature)) == 1


def test_a_fresh_champ_select_resets_the_sent_flag_for_the_next_game():
    feature = make_feature()
    feature._handle_phase("WaitingForStats")
    feature._handle_phase("EndOfGame")

    feature._handle_phase("ChampSelect")
    feature._handle_phase("InProgress")
    feature._handle_phase("WaitingForStats")

    assert len(_play_again_calls(feature)) == 2
