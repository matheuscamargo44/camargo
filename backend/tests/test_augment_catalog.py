"""AugmentCatalog: turning a captured card crop back into augment ids.

Fixtures are real augment icons fetched from Community Dragon, so matching
is exercised against real art rather than synthetic noise.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from core.augment_catalog import (
    ICON_COMPOSITE_BACKGROUND,
    AugmentCatalog,
    _composite_on_dark_background,
    _icon_url,
    correlation,
    to_match_vector,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _catalog_with(icon_files):
    """Builds a catalog whose vectors come from the given fixture files,
    the same way _build_from_scratch would."""
    catalog = AugmentCatalog()
    catalog._augments = {
        augment_id: {"name": name, "icon_path": f"/lol-game-data/assets/{name}_small.png", "rarity": "kGold"}
        for augment_id, (name, _) in icon_files.items()
    }
    catalog._vectors = {
        augment_id: to_match_vector(_composite_on_dark_background(Image.open(FIXTURES / filename)))
        for augment_id, (_, filename) in icon_files.items()
    }
    catalog._loaded = True
    return catalog


FIXTURE_SET = {
    2132: ("Warlock Juicebox", "warlock_juicebox.png"),
    1141: ("All For You", "allforyou.png"),
}


def test_composite_removes_transparency():
    """Community Dragon's icons are grayscale-with-alpha - a raw, unlit
    shape mask, not the lit icon the game renders. Comparing the raw
    transparent image against an opaque screen capture measurably
    misaligns, so it must be flattened first."""
    original = Image.open(FIXTURES / "allforyou.png")
    assert original.mode in ("LA", "RGBA")

    composited = _composite_on_dark_background(original)

    assert composited.mode == "RGB"
    assert composited.getpixel((0, 0)) == ICON_COMPOSITE_BACKGROUND[:3]


def test_match_vector_is_brightness_invariant():
    """The in-game render is lit and far brighter than the flat reference
    art, so the comparison must not key on absolute brightness."""
    image = _composite_on_dark_background(Image.open(FIXTURES / "warlock_juicebox.png"))
    # Scaled down and lifted, so nothing clips at 255 and only the overall
    # brightness/contrast changes - not the structure.
    brightened = Image.eval(image, lambda value: int(value * 0.7) + 60)

    assert correlation(to_match_vector(image), to_match_vector(brightened)) > 0.98


def test_identify_matches_the_right_icon():
    catalog = _catalog_with(FIXTURE_SET)

    assert catalog.identify(Image.open(FIXTURES / "warlock_juicebox.png")) == [2132]
    assert catalog.identify(Image.open(FIXTURES / "allforyou.png")) == [1141]


def test_identify_returns_nothing_below_the_threshold():
    """A crop that looks like no known icon must come back empty, never a
    wrong guess - a miss is always preferable to a wrong badge."""
    catalog = _catalog_with(FIXTURE_SET)

    blank = Image.new("RGB", (64, 64), color="white")

    assert catalog.identify(blank) == []


def test_identify_returns_every_tied_candidate():
    """Some genuinely different augments ship byte-identical art. The
    matcher cannot separate those, so it must surface the whole tied set
    instead of silently picking one and being wrong."""
    shared = {
        10: ("Ok Boomerang", "warlock_juicebox.png"),
        20: ("Endless Decimation", "warlock_juicebox.png"),
        30: ("Something Else", "allforyou.png"),
    }
    catalog = _catalog_with(shared)

    result = catalog.identify(Image.open(FIXTURES / "warlock_juicebox.png"))

    assert sorted(result) == [10, 20]


def test_identify_with_no_vectors_returns_empty():
    catalog = AugmentCatalog()
    catalog._augments, catalog._vectors, catalog._loaded = {}, {}, True

    assert catalog.identify(Image.new("RGB", (64, 64))) == []


@pytest.mark.parametrize(
    "large,expected_suffix",
    [(False, "allforyou_small.png"), (True, "allforyou_large.png")],
)
def test_icon_url_strips_prefix_lowercases_and_selects_variant(large, expected_suffix):
    """The catalog only ever points at _small, but many different augments
    share one byte-identical _small placeholder; the _large variant beside
    it carries the real per-augment art."""
    url = _icon_url("/lol-game-data/assets/ASSETS/UX/Cherry/Augments/Icons/AllForYou_small.png", large=large)

    assert url == f"https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons/{expected_suffix}"


def test_rarity_returns_the_stored_value():
    """Static game data, unlike tier/performance - present for every
    augment regardless of whether OP.GG has enough samples to rate it."""
    catalog = _catalog_with(FIXTURE_SET)

    assert catalog.rarity(2132) == "kGold"


def test_rarity_of_an_unknown_augment_is_none():
    catalog = _catalog_with(FIXTURE_SET)

    assert catalog.rarity(999999) is None


def test_cache_round_trips(tmp_path, monkeypatch):
    import core.augment_catalog as augment_catalog_module

    monkeypatch.setattr(augment_catalog_module, "_cache_dir", lambda: tmp_path)

    original = _catalog_with(FIXTURE_SET)
    original._save_to_cache()

    reloaded = AugmentCatalog()
    assert reloaded._load_from_cache() is True
    assert reloaded._augments.keys() == original._augments.keys()
    for augment_id, vector in original._vectors.items():
        assert np.allclose(reloaded._vectors[augment_id], vector)


def test_load_from_cache_survives_a_corrupt_cache_file(tmp_path, monkeypatch):
    import core.augment_catalog as augment_catalog_module

    monkeypatch.setattr(augment_catalog_module, "_cache_dir", lambda: tmp_path)
    (tmp_path / "augments.json").write_text("not valid json{{{", encoding="utf-8")

    catalog = AugmentCatalog()

    # Must not raise: a corrupt cache falls through to a rebuild.
    assert catalog._load_from_cache() is False
