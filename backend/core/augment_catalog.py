"""Reference icon set for every ARAM/Arena augment, and the matcher that
turns a screen-captured card crop back into augment ids.

There is no API for "which augments am I being offered" (confirmed
exhaustively - see `docs/smart-counter-pick-spec.md`, Part B), so the icons
have to be recognised visually.

Source is Community Dragon's public, unauthenticated data dump:
    https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json
Each entry's `augmentSmallIconPath` maps to a real image by stripping the
`/lol-game-data/assets/` prefix, lowercasing, and prepending
`https://raw.communitydragon.org/latest/game/`.

Two findings drive the design here, both established by testing against a
real captured picker screenshot:

1. The catalog only ever points at the `_small` icon, but many *different*
   augments share one byte-identical `_small` placeholder (612 files, only
   313 distinct images). Swapping `_small` for the `_large` variant that
   sits beside it recovers most of the real per-augment art.
2. Matching is done by normalised cross-correlation on the grayscale
   glyph, not a perceptual hash. phash's 8x8 DCT is far too coarse for
   small line-art glyphs: it ranked the correct answer 39th of ~600 on a
   real capture. With the crop geometry calibrated (see
   aram_augment_regions), correlation scores the right art ~0.97 while
   genuinely different art stays below 0.94.

Even with `_large`, a handful of distinct augments still share identical
art, so `identify()` deliberately returns *all* tied candidates rather than
inventing confidence it does not have. Callers decide what to do with an
ambiguous set - see AramAugmentAdvisor.
"""
import json
import logging
from io import BytesIO
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from core.paths import is_frozen, user_data_dir

logger = logging.getLogger(__name__)

CATALOG_URL = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json"
ICON_BASE_URL = "https://raw.communitydragon.org/latest/game/"
ICON_PATH_PREFIX = "/lol-game-data/assets/"
REQUEST_TIMEOUT_SECONDS = 10.0

#: Reference icons are grayscale-with-alpha shape masks - an unlit glyph on
#: nothing. The game draws that glyph lit, on a near-black card. Compositing
#: onto a dark background before comparing makes the two comparable; skipping
#: this step alone cost 6 points of Hamming distance in early testing.
ICON_COMPOSITE_BACKGROUND = (15, 15, 20, 255)

#: Comparison resolution. 64 keeps enough glyph detail to separate similar
#: icons while staying cheap enough to compare against ~600 references.
MATCH_SIZE = 64

#: Measured on a real capture: correct art scored 0.9696-0.9728 across all
#: three cards, while the best genuinely-different art scored at most
#: 0.938. 0.95 sits in that gap.
MATCH_THRESHOLD = 0.95

#: Candidates within this of the best score are treated as indistinguishable
#: (in practice they are pixel-identical art shared by several augments)
#: and all get returned.
TIE_EPSILON = 0.01


def _cache_dir():
    base = user_data_dir() if is_frozen() else Path(__file__).resolve().parent.parent
    return base / "augment_cache"


def _icon_url(icon_path, large=False):
    if icon_path.startswith(ICON_PATH_PREFIX):
        icon_path = icon_path[len(ICON_PATH_PREFIX):]
    url = ICON_BASE_URL + icon_path.lower()
    return url.replace("_small.png", "_large.png") if large else url


def _composite_on_dark_background(image):
    """Flattens a transparent reference icon onto a dark background
    approximating the real in-game card, so its vector is comparable to one
    taken from an opaque screen capture."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, ICON_COMPOSITE_BACKGROUND)
    return Image.alpha_composite(background, rgba).convert("RGB")


def to_match_vector(image):
    """Grayscale, resized, zero-mean/unit-variance - so correlation is
    unaffected by the overall brightness difference between the flat
    reference art and the lit in-game render.

    Transparent input is flattened first: converting an RGBA/LA image
    straight to "L" silently discards alpha and yields a vector that will
    not correlate with the same art composited, so both paths must go
    through the same flattening.
    """
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        image = _composite_on_dark_background(image)

    array = np.asarray(
        image.convert("L").resize((MATCH_SIZE, MATCH_SIZE), Image.LANCZOS),
        dtype=np.float32,
    )
    array = array - array.mean()
    deviation = array.std()
    return array / deviation if deviation > 0 else array


def correlation(a, b):
    return float((a * b).sum() / a.size)


class AugmentCatalog:
    """Fetches and caches the augment catalog plus a match vector per icon.

    Any failure (network down, corrupt cache) degrades to "identify()
    returns nothing" rather than raising - callers never have to guard
    against the catalog being unavailable.
    """

    def __init__(self):
        self._augments = {}
        self._vectors = {}
        self._loaded = False

    # -- loading / caching --

    def _ensure_loaded(self):
        if self._loaded:
            return
        if not self._load_from_cache():
            self._build_from_scratch()
        self._loaded = True

    def _cache_files(self):
        cache_dir = _cache_dir()
        return cache_dir / "augments.json", cache_dir / "vectors.npz"

    def _load_from_cache(self):
        meta_file, vectors_file = self._cache_files()
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            self._augments = {int(k): v for k, v in data["augments"].items()}
            with np.load(vectors_file) as stored:
                self._vectors = {int(k): stored[k] for k in stored.files}
            return bool(self._augments and self._vectors)
        except Exception:
            self._augments, self._vectors = {}, {}
            return False

    def _save_to_cache(self):
        meta_file, vectors_file = self._cache_files()
        try:
            meta_file.parent.mkdir(parents=True, exist_ok=True)
            meta_file.write_text(json.dumps({"augments": self._augments}), encoding="utf-8")
            np.savez_compressed(vectors_file, **{str(k): v for k, v in self._vectors.items()})
        except Exception:
            logger.exception("failed to save augment cache")

    def _build_from_scratch(self):
        try:
            response = requests.get(CATALOG_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            entries = response.json()
        except Exception:
            logger.exception("failed to fetch augment catalog")
            return

        augments, vectors = {}, {}
        session = requests.Session()
        for entry in entries:
            augment_id, icon_path = entry.get("id"), entry.get("augmentSmallIconPath")
            if augment_id is None or not icon_path:
                continue
            augments[augment_id] = {
                "name": entry.get("nameTRA"),
                "icon_path": icon_path,
                "rarity": entry.get("rarity"),
            }
            vector = self._icon_vector(icon_path, session)
            if vector is not None:
                vectors[augment_id] = vector

        if not augments:
            return

        self._augments, self._vectors = augments, vectors
        self._save_to_cache()

    def _icon_vector(self, icon_path, session=None):
        """Prefers the higher-detail `_large` art, falling back to the
        `_small` the catalog actually points at when no large variant
        exists (~68 of ~640 augments)."""
        getter = (session or requests).get
        for large in (True, False):
            try:
                response = getter(_icon_url(icon_path, large=large), timeout=REQUEST_TIMEOUT_SECONDS)
                if response.status_code != 200:
                    continue
                return to_match_vector(Image.open(BytesIO(response.content)))
            except Exception:
                logger.debug("failed to build vector for %s (large=%s)", icon_path, large, exc_info=True)
        return None

    # -- matching --

    def identify(self, image, threshold=MATCH_THRESHOLD):
        """Returns every augment id whose reference art matches `image` (a
        PIL crop of one card's icon), best first.

        Usually one id, or several ids that are all the same augment. It can
        also be several genuinely different augments that ship identical
        art, which no image comparison could ever separate - returning the
        whole tied set lets the caller decide, instead of silently picking
        one and being wrong. Empty when nothing clears the threshold: a
        missed identification is always preferable to a wrong one.
        """
        self._ensure_loaded()
        if not self._vectors:
            return []

        try:
            target = to_match_vector(image)
        except Exception:
            return []

        scored = sorted(
            ((correlation(target, vector), augment_id) for augment_id, vector in self._vectors.items()),
            reverse=True,
        )
        if not scored or scored[0][0] < threshold:
            return []

        best = scored[0][0]
        return [augment_id for score, augment_id in scored if score >= best - TIE_EPSILON]

    # -- accessors --

    def name(self, augment_id):
        self._ensure_loaded()
        entry = self._augments.get(augment_id)
        return entry["name"] if entry else None

    def icon_url(self, augment_id):
        self._ensure_loaded()
        entry = self._augments.get(augment_id)
        return _icon_url(entry["icon_path"], large=True) if entry else None

    def rarity(self, augment_id):
        """Raw Community Dragon rarity string (e.g. "kGold"), or None.

        Unlike tier/performance, this is static game data - present for
        every augment regardless of whether OP.GG has enough match samples
        to rate it. Useful as a fallback signal when there is no rating:
        see RARITY_LABELS in features/aram_augment_advisor.py.
        """
        self._ensure_loaded()
        entry = self._augments.get(augment_id)
        return entry["rarity"] if entry else None


#: Shared across every consumer - one catalog, built once.
augment_catalog = AugmentCatalog()
