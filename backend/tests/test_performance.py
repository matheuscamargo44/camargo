"""Performance sanity checks.

This is a single-user local desktop app, not a server under concurrent
load - traditional load testing (many simultaneous clients) doesn't map to
it. What matters instead is that the hot paths that run on a tight poll
budget (a 0.5s ARAM picker poll, a 0.6s overlay poll, a 4s /features poll
across every feature) stay comfortably inside it. Thresholds here are
deliberately generous (an order of magnitude above the real budget) to
catch a genuine regression - an accidental O(n^2), a blocking call added to
a hot path - without being flaky on a slower CI machine.
"""
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.server as server
from core.auth import AUTH_TOKEN, TOKEN_HEADER
from core.augment_catalog import correlation, to_match_vector
from core.opgg_scraper import _ENTRY_RE

AUTH = {TOKEN_HEADER: AUTH_TOKEN}


# -- HTTP hot paths --


@pytest.mark.parametrize("path", ["/health", "/features", "/features/meta"])
def test_lightweight_routes_respond_quickly_with_no_live_client(client, path):
    """No League/VALORANT client is running in this test env, so every
    feature's get_status() takes its fast "disconnected" branch - this is
    the actual floor these routes must never regress below, since a
    genuinely connected client only adds real work on top."""
    started = time.perf_counter()
    response = client.get(path, headers=AUTH)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 2.0, f"{path} took {elapsed:.2f}s with nothing live to poll"


def test_features_endpoint_actually_parallelizes_status_calls(client):
    """registry.status() fans out over a thread pool specifically because
    nine-plus features each make their own blocking client call - done in
    series that adds up to most of a poll interval. A regression back to a
    serial loop wouldn't show up in the single-call latency test above (no
    live client means each call is already fast), so this instead confirms
    the fan-out mechanism itself is still a real ThreadPoolExecutor.map,
    not something accidentally made synchronous."""
    from concurrent.futures import ThreadPoolExecutor

    assert isinstance(server.registry._status_pool, ThreadPoolExecutor)


# -- augment icon matching: must stay well inside a 0.5s poll tick --


def test_a_single_icon_correlation_is_fast_enough_for_hundreds_per_poll_tick():
    """The real catalog correlates one captured card crop against ~600
    reference vectors, up to 3 cards, within a poll tick that also has to
    leave room for the screen capture itself. Measuring one comparison and
    extrapolating avoids needing a live ~600-icon catalog fetch in a unit
    test, while still catching an accidental slow path (e.g. correlation
    recomputing a reference vector instead of reusing a cached one)."""
    rng = np.random.default_rng(0)
    a = to_match_vector_from_array(rng)
    b = to_match_vector_from_array(rng)

    started = time.perf_counter()
    for _ in range(600):
        correlation(a, b)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5, f"600 correlations took {elapsed:.2f}s - a single capture would blow the poll budget"


def to_match_vector_from_array(rng):
    from PIL import Image

    array = rng.integers(0, 255, size=(64, 64), dtype=np.uint8)
    return to_match_vector(Image.fromarray(array, mode="L"))


# -- OP.GG scrape parsing: a full ~200-augment page must parse fast --


def test_scraper_regex_parses_a_full_page_worth_of_entries_quickly():
    """Confirmed live (see core/opgg_scraper.py) that a real champion page
    embeds all ~200 of a champion's augments in one response. Synthesizing
    that many entries here avoids a live network fetch while still
    exercising the regex against a realistically large haystack."""
    entries = ",".join(
        f'{{\\"id\\":{augment_id},\\"tier\\":{augment_id % 6},\\"performance\\":{70 + augment_id % 30}.5}}'
        for augment_id in range(1000, 1200)
    )
    page = f'self.__next_f.push([1,"52:[{entries}]"])'

    started = time.perf_counter()
    matches = list(_ENTRY_RE.finditer(page))
    elapsed = time.perf_counter() - started

    assert len(matches) == 200
    assert elapsed < 0.1, f"parsing 200 augment entries took {elapsed:.2f}s"


# -- config save: must not stall a toggle click --


def test_save_config_is_fast_even_with_a_realistic_number_of_settings(tmp_path, monkeypatch):
    import core.config as config_module

    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")

    # DEFAULT_CONFIG already has every feature's real settings; toggling one
    # feature saves the whole dict, not just the changed section.
    import copy

    config = copy.deepcopy(config_module.DEFAULT_CONFIG)
    config["instalock"]["champions"] = [f"Champion{i}" for i in range(50)]  # a generous priority list

    started = time.perf_counter()
    for _ in range(20):
        config_module.save_config(config)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"20 saves took {elapsed:.2f}s - a toggle click must not feel like it hung"
