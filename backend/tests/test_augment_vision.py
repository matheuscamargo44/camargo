"""picker_is_open(): detecting the augment picker from its card borders.

Tolerant of one border being knocked out by League's own hover-enlarge
animation on the card the player is comparing, and of the border being
tinted differently per augment rarity rather than a single fixed color.
"""
import pytest
from PIL import Image, ImageDraw

from core.aram_augment_regions import CARD_BORDER_XS, CARD_BORDER_Y_RANGE
from core.augment_vision import picker_is_open

#: Sampled live from real captures. Gold and Silver are the two rarities
#: actually seen in a real game so far - confirmed live 2026-08-25, a
#: Silver-rarity offer was completely undetected by a gold-only check.
#: Community Dragon's full catalog lists 5 rarity values in total
#: (kSilver, kGold, kPrismatic, kBronze, kEventChoice); Prismatic/Bronze/
#: EventChoice have not been captured live yet, so there is no sampled
#: color for them to test against - the brightness-range approach (not
#: hue-specific) is the hedge against that gap, not a specific color.
GOLD = (173, 145, 116)
SILVER = (137, 138, 137)

#: A real false-positive case: at these exact coordinates during a non-
#: picker moment, moderately-bright world lighting/spell VFX bled through
#: - sampled live from aram_calibration_shots/level_15_172445.png, which
#: broke an earlier version of this check that had no upper brightness
#: bound at all.
WORLD_LIGHTING_NOISE = (155, 149, 130)

DARK = (7, 19, 38)  # sampled from a real card's near-black interior

_TOP = min(CARD_BORDER_Y_RANGE)
_BOTTOM = max(CARD_BORDER_Y_RANGE)
_WIDTH = max(CARD_BORDER_XS) + 50
_HEIGHT = _BOTTOM + 50


def _picker_frame(open_borders=(0, 1, 2), color=GOLD, background=DARK):
    """A synthetic frame with borders at some subset of the 3 known card
    border x-positions - `open_borders` selects which of CARD_BORDER_XS
    actually show a border, simulating one knocked out of its fixed sample
    column (e.g. by the hover-enlarge animation)."""
    image = Image.new("RGB", (_WIDTH, _HEIGHT), background)
    draw = ImageDraw.Draw(image)
    for index in open_borders:
        x = CARD_BORDER_XS[index]
        draw.line([(x, _TOP), (x, _BOTTOM)], fill=color, width=1)
    return image


def _partial_column(image, x, color, sample_indices):
    """Colors only some of the 9 sampled rows of one column - a column
    that's noisy/bright in patches, not solidly lit top to bottom the way
    a real card border is."""
    draw = ImageDraw.Draw(image)
    y_values = list(CARD_BORDER_Y_RANGE)
    for i in sample_indices:
        draw.point((x, y_values[i]), fill=color)


@pytest.mark.parametrize("color", [GOLD, SILVER], ids=["gold-rarity", "silver-rarity"])
def test_all_three_borders_present_is_open_regardless_of_rarity_color(color):
    assert picker_is_open(_picker_frame((0, 1, 2), color=color)) is True


def test_no_borders_present_is_closed():
    assert picker_is_open(_picker_frame(())) is False


@pytest.mark.parametrize("color", [GOLD, SILVER], ids=["gold-rarity", "silver-rarity"])
def test_one_border_knocked_out_is_still_open(color):
    """League's own hover-enlarge animation on the card being compared
    shifts that card's border away from its fixed sample column. Confirmed
    live: with the old all-3-required check, a real session's log showed
    one continuous pick re-triggering 4 times in 6s, because comparing
    cards means hovering each one in turn."""
    assert picker_is_open(_picker_frame((0, 1), color=color)) is True
    assert picker_is_open(_picker_frame((0, 2), color=color)) is True
    assert picker_is_open(_picker_frame((1, 2), color=color)) is True


def test_two_borders_knocked_out_reads_as_closed():
    """The tolerance is for exactly one hovered card, not a genuinely
    closed picker - which must still read as closed, not stay stuck open."""
    assert picker_is_open(_picker_frame((0,))) is False
    assert picker_is_open(_picker_frame((1,))) is False


def test_one_fully_lit_column_from_world_noise_is_not_enough_alone():
    """The real false-positive this guards: at these exact coordinates
    during a non-picker moment, world lighting/VFX happened to light up
    one whole column (9/9 sample rows individually pass the brightness
    check) while the other two columns were only partially lit (5/9 and
    6/9, sampled live) - below CARD_BORDER_MIN_HITS. A per-pixel brightness
    check alone can't tell that column apart from a real border; what
    saves it is CARD_BORDER_REQUIRED_COUNT needing 2 columns to agree, not
    just the one.
    """
    image = _picker_frame(())  # dark background, no borders drawn yet
    _partial_column(image, CARD_BORDER_XS[0], WORLD_LIGHTING_NOISE, range(9))  # 9/9
    _partial_column(image, CARD_BORDER_XS[1], WORLD_LIGHTING_NOISE, range(5))  # 5/9
    _partial_column(image, CARD_BORDER_XS[2], WORLD_LIGHTING_NOISE, range(6))  # 6/9

    assert picker_is_open(image) is False
