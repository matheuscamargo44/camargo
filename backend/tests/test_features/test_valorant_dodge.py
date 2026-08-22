import pytest
from valclient.exceptions import PhaseError

from features.valorant_dodge import ValorantDodge


class FakeValorantClient:
    def __init__(self, quit_error=None):
        self.quit_calls = 0
        self.quit_error = quit_error

    def pregame_quit_match(self):
        self.quit_calls += 1
        if self.quit_error:
            raise self.quit_error


def make_feature(quit_error=None):
    valorant = FakeValorantClient(quit_error=quit_error)
    events = []
    feature = ValorantDodge(valorant, {}, on_event=lambda level, message: events.append((level, message)))
    return feature, valorant, events


def test_dodge_quits_the_pregame_match_and_emits_success():
    feature, valorant, events = make_feature()

    feature.dodge()

    assert valorant.quit_calls == 1
    assert events[-1] == ("success", "Left agent select")


def test_dodge_outside_pregame_raises_a_clear_runtime_error():
    feature, _, _ = make_feature(quit_error=PhaseError("You are not in a pre-game"))

    with pytest.raises(RuntimeError, match="not in agent select"):
        feature.dodge()
