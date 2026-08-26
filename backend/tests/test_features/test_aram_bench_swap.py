"""AramBenchSwap: resolving the priority list against the shared bench."""
import copy

from core.config import DEFAULT_CONFIG
from features.aram_bench_swap import AramBenchSwap


class StubLCUClient:
    def is_league_connected(self):
        return True

    def lcu_request(self, method, endpoint, body=""):
        raise AssertionError("this test does not expect an LCU call")


def make_feature(champions=None):
    feature = AramBenchSwap(StubLCUClient(), copy.deepcopy(DEFAULT_CONFIG))
    feature.champ_dict = {"lux": 99, "ziggs": 115, "garen": 86}
    feature.champions = champions if champions is not None else ["Lux", "Ziggs"]
    return feature


def _bench(*champion_ids):
    return [{"championId": cid} for cid in champion_ids]


def test_swaps_to_the_highest_priority_champion_on_the_bench():
    feature = make_feature()

    assert feature.resolve_champion(_bench(99, 115), current_champion_id=None) == "Lux"


def test_does_not_downgrade_once_the_top_priority_champion_is_already_held():
    """The bug this guards: after swapping to Lux, Lux's own old champion
    (say Garen) lands back on the bench alongside Ziggs, which was on the
    bench the whole time too. A bench-only search matches Ziggs (priority
    2) and swaps away from Lux (priority 1) - a downgrade, and then swaps
    right back the moment Lux reappears on the bench, forever."""
    feature = make_feature()  # priority ["Lux", "Ziggs"]

    # Already holding Lux (id 99); Ziggs (115) is also sitting on the bench.
    resolved = feature.resolve_champion(_bench(115, 86), current_champion_id=99)

    assert resolved is None


def test_still_swaps_to_something_strictly_better_than_what_is_held():
    feature = make_feature()  # priority ["Lux", "Ziggs"]

    # Currently holding Ziggs (priority 2); Lux (priority 1) is on the bench.
    resolved = feature.resolve_champion(_bench(99), current_champion_id=115)

    assert resolved == "Lux"


def test_ignores_a_bench_champion_below_what_is_already_held():
    feature = make_feature()  # priority ["Lux", "Ziggs"]

    # Holding Lux (priority 1, the best); Ziggs (priority 2) alone on bench.
    resolved = feature.resolve_champion(_bench(115), current_champion_id=99)

    assert resolved is None


def test_no_current_champion_falls_back_to_a_pure_bench_search():
    feature = make_feature()

    assert feature.resolve_champion(_bench(115), current_champion_id=None) == "Ziggs"


def test_no_priority_champion_on_the_bench_resolves_to_none():
    feature = make_feature()

    assert feature.resolve_champion(_bench(86), current_champion_id=None) is None
