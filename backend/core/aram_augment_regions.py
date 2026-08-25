"""Where the 3 augment cards sit on screen, as 0-1 fractions of the primary
display, plus how to tell whether the picker is currently on screen at all.

Calibrated 2026-08-24 against real 1920x1080 screenshots captured live
during an ARAM: Mayhem match (not a bot lobby). Card icon boxes were
measured with a pixel scan for the cards' gold border, then each crop was
inspected visually. See "Fase 0" in the implementation plan.
"""

SUPPORTED_RESOLUTION = (1920, 1080)

#: Whether the picker is on screen is *detected*, never inferred from the
#: player's level. Levels 7/11/15 only pop a "you earned an Augment!"
#: notification - the player opens the picker whenever they feel like it,
#: which can be seconds or minutes later. Confirmed live: the level-7 and
#: level-15 calibration screenshots caught that notification with no cards
#: on screen at all, while the level-11 one caught the real picker.
#:
#: Each card is drawn with a thick warm-gold border. Sampling a column of
#: pixels down each card's left border separates the two states cleanly -
#: measured across all four calibration screenshots, the open picker scored
#: 9/9 gold on all three borders and every closed-picker shot scored 0-2.
CARD_BORDER_XS = (449, 817, 1185)
CARD_BORDER_Y_RANGE = range(370, 460, 10)

#: 9 samples per border; 7 sits comfortably above the observed closed-picker
#: noise floor (2) and below the observed open-picker score (9).
CARD_BORDER_MIN_HITS = 7

#: Tight to the icon glyph only - not the card's name, description or tier
#: badge - because AugmentCatalog matches this crop against reference icons
#: that are themselves just the glyph.
#:
#: These numbers are not eyeballed. Card 0 in the calibration screenshot is
#: known to be "Ethereal Weapon", so the crop centre and size were found by
#: searching for the box that maximises correlation against that known
#: reference icon: centre (598, 310), 160x160, correlating at 0.9704. The
#: 368px pitch between cards comes from the measured border positions. An
#: earlier hand-measured box was ~10px off in size and centre, which was
#: enough to collapse every candidate score into a band 0.0000 wide - hence
#: deriving it from ground truth instead.
#:
#: One layout covers both the game-start picker and the level-up reoffer.
#: Only the reoffer was ever captured live, but because the picker is
#: *detected* rather than assumed, a differently-positioned start picker
#: would simply fail the border check and produce nothing - never a wrong
#: recommendation.
_CARD_PITCH = 368
_ICON_SIZE = 160
_ICON_TOP = 230
_FIRST_ICON_LEFT = 518

AUGMENT_CARD_REGIONS = [
    {
        "slot": slot,
        "x": (_FIRST_ICON_LEFT + slot * _CARD_PITCH) / 1920,
        "y": _ICON_TOP / 1080,
        "w": _ICON_SIZE / 1920,
        "h": _ICON_SIZE / 1080,
    }
    for slot in range(3)
]
