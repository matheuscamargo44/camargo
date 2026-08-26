"""Screen-capture mechanics only - kept separate from augment_catalog.py so
the matching logic stays testable with plain fixture images, with no `mss`
or display dependency in that test path.

Requires the game in borderless/windowed mode: an exclusive-fullscreen game
is not visible to a normal desktop grab. Every function here returns
None/False rather than raising, so that case degrades to "the picker is
never detected" instead of erroring in a feature loop.
"""
import logging
import statistics

import mss
from PIL import Image

from core.aram_augment_regions import (
    CARD_BORDER_MIN_HITS,
    CARD_BORDER_REQUIRED_COUNT,
    CARD_BORDER_XS,
    CARD_BORDER_Y_RANGE,
)

logger = logging.getLogger(__name__)


#: Augments come in 5 rarities (kSilver, kGold, kPrismatic, kBronze,
#: kEventChoice - checked the full Community Dragon catalog; ARAM Mayhem
#: may not offer all 5), and the card border is tinted per rarity, not one
#: fixed color. A first version of this only matched a warm gold tone and
#: missed a real Silver-rarity offer live (confirmed by sampling both:
#: Gold borders around (173,145,116), Silver around (137,138,137) - neither
#: close to the other in hue). A second version relaxed to any color within
#: a brightness band, which is still a hue assumption in disguise: it would
#: miss a border color saturated enough to have one dark channel (plausible
#: for Prismatic, which has never been seen live to confirm either way, and
#: was flagged as still-unhandled before this fix shipped).
#:
#: So this doesn't test individual pixels against any color range at all.
#: A painted border is one solid, consistent color for its whole length; the
#: two known false-positive sources (world lighting bleeding through the
#: dimmed background, spell VFX) vary from sample to sample even when
#: individually bright - confirmed live, one false-positive case swung from
#: (82,152,255) to (240,171,255) across two rows 20px apart. So each column
#: is tested for *self-consistency* - most of its 9 samples close to their
#: own median - which is true for any solid border color, whatever the hue,
#: and false for noise. Verified against every capture on hand: both real
#: rarities seen live pass, and all known-closed captures (including the
#: two noise cases above) still correctly read as closed.
_BORDER_COLOR_TOLERANCE = 22
_BORDER_MIN_BRIGHTNESS = 60


def _is_card_border_column(pixels):
    reds = [p[0] for p in pixels]
    greens = [p[1] for p in pixels]
    blues = [p[2] for p in pixels]
    median = (statistics.median(reds), statistics.median(greens), statistics.median(blues))
    if max(median) < _BORDER_MIN_BRIGHTNESS:
        return False  # too dark to be any border color - still background

    close = sum(
        1
        for red, green, blue in pixels
        if abs(red - median[0]) <= _BORDER_COLOR_TOLERANCE
        and abs(green - median[1]) <= _BORDER_COLOR_TOLERANCE
        and abs(blue - median[2]) <= _BORDER_COLOR_TOLERANCE
    )
    return close >= CARD_BORDER_MIN_HITS


def primary_monitor_resolution():
    """Returns (width, height) of the primary monitor, or None if it can't
    be determined (no display access, headless environment, etc.)."""
    try:
        with mss.MSS() as sct:
            monitor = sct.monitors[1]
            return monitor["width"], monitor["height"]
    except Exception:
        logger.debug("failed to read primary monitor resolution", exc_info=True)
        return None


def picker_is_open(image=None):
    """True when the 3-card augment picker is actually drawn on screen.

    Cheap enough to poll: samples 27 pixels down the three cards' borders.
    Pass `image` (a full-screen PIL.Image) to test a screenshot; otherwise
    it grabs the strip containing those borders itself.
    """
    if image is None:
        strip_top = min(CARD_BORDER_Y_RANGE)
        strip_bottom = max(CARD_BORDER_Y_RANGE) + 1
        image = capture_absolute(
            left=min(CARD_BORDER_XS),
            top=strip_top,
            width=max(CARD_BORDER_XS) - min(CARD_BORDER_XS) + 1,
            height=strip_bottom - strip_top,
        )
        if image is None:
            return False
        x_offset, y_offset = min(CARD_BORDER_XS), strip_top
    else:
        x_offset = y_offset = 0

    pixels = image.convert("RGB").load()
    passing = 0
    for border_x in CARD_BORDER_XS:
        column = [pixels[border_x - x_offset, border_y - y_offset] for border_y in CARD_BORDER_Y_RANGE]
        if _is_card_border_column(column):
            passing += 1
    return passing >= CARD_BORDER_REQUIRED_COUNT


def capture_absolute(left, top, width, height):
    """Captures an absolute pixel rectangle from the primary monitor."""
    try:
        with mss.MSS() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(
                {
                    "left": monitor["left"] + left,
                    "top": monitor["top"] + top,
                    "width": width,
                    "height": height,
                }
            )
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        logger.debug("failed to capture region %s", (left, top, width, height), exc_info=True)
        return None


def capture_region(fraction_box):
    """Captures `fraction_box = (x, y, w, h)`, given as 0-1 fractions of
    the primary monitor, and returns it as a PIL.Image - or None if capture
    fails for any reason (this must never raise into a feature loop).
    """
    x_frac, y_frac, w_frac, h_frac = fraction_box
    try:
        with mss.MSS() as sct:
            monitor = sct.monitors[1]
            region = {
                "left": monitor["left"] + round(monitor["width"] * x_frac),
                "top": monitor["top"] + round(monitor["height"] * y_frac),
                "width": round(monitor["width"] * w_frac),
                "height": round(monitor["height"] * h_frac),
            }
            shot = sct.grab(region)
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        logger.debug("failed to capture screen region %s", fraction_box, exc_info=True)
        return None
