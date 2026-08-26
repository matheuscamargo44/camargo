"""picker_is_open(): detecting the augment picker from its gold card
borders, tolerant of one border being knocked out by League's own
hover-enlarge animation on the card the player is comparing.
"""
from PIL import Image, ImageDraw

from core.aram_augment_regions import CARD_BORDER_XS, CARD_BORDER_Y_RANGE
from core.augment_vision import picker_is_open

GOLD = (210, 180, 90)
DARK = (10, 10, 12)

_TOP = min(CARD_BORDER_Y_RANGE)
_BOTTOM = max(CARD_BORDER_Y_RANGE)
_WIDTH = max(CARD_BORDER_XS) + 50
_HEIGHT = _BOTTOM + 50


def _picker_frame(open_borders=(0, 1, 2)):
    """A synthetic frame with gold vertical borders at some subset of the 3
    known card border x-positions - `open_borders` selects which of
    CARD_BORDER_XS actually show gold, simulating a border knocked out of
    its fixed sample column (e.g. by the hover-enlarge animation)."""
    image = Image.new("RGB", (_WIDTH, _HEIGHT), DARK)
    draw = ImageDraw.Draw(image)
    for index in open_borders:
        x = CARD_BORDER_XS[index]
        draw.line([(x, _TOP), (x, _BOTTOM)], fill=GOLD, width=1)
    return image


def test_all_three_borders_present_is_open():
    assert picker_is_open(_picker_frame((0, 1, 2))) is True


def test_no_borders_present_is_closed():
    assert picker_is_open(_picker_frame(())) is False


def test_one_border_knocked_out_is_still_open():
    """League's own hover-enlarge animation on the card being compared
    shifts that card's border away from its fixed sample column. Confirmed
    live: with the old all-3-required check, a real session's log showed
    one continuous pick re-triggering 4 times in 6s, because comparing
    cards means hovering each one in turn."""
    assert picker_is_open(_picker_frame((0, 1))) is True
    assert picker_is_open(_picker_frame((0, 2))) is True
    assert picker_is_open(_picker_frame((1, 2))) is True


def test_two_borders_knocked_out_reads_as_closed():
    """The tolerance is for exactly one hovered card, not a genuinely
    closed picker - which must still read as closed, not stay stuck open."""
    assert picker_is_open(_picker_frame((0,))) is False
    assert picker_is_open(_picker_frame((1,))) is False
