"""Generates the app icon: a simple monochrome shield/crest (no external
assets, no third-party trademarks) — black fill with a thin white outline
on a transparent background, so the icon itself is black but still reads
cleanly against dark taskbars. Produces icon.png (256x256) and a
multi-resolution icon.ico (16/32/48/64/128/256). No image library
dependency — pure Python, using supersampled point-in-polygon
rasterization for anti-aliased edges.
"""
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
ICO_SIZES = [16, 32, 48, 64, 128, 256]
SUPERSAMPLE = 4

# Shield/crest outline in unit-square coordinates (y grows downward).
# A slightly notched bottom point gives it a crest-like silhouette
# reminiscent of a Summoner's Rift team-emblem shield, without copying any
# specific logo.
SHIELD = [
    (0.50, 0.06),
    (0.86, 0.20),
    (0.86, 0.52),
    (0.50, 0.94),
    (0.50, 0.80),
    (0.14, 0.52),
    (0.14, 0.20),
]

OUTLINE_SCALE = 1.10  # black base is drawn slightly larger than the white fill


def scale_polygon(points, factor):
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in points]


def point_in_polygon(px, py, polygon):
    inside = False
    n = len(polygon)
    x1, y1 = polygon[-1]
    for x2, y2 in polygon:
        if (y1 > py) != (y2 > py):
            x_intersect = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def rasterize(size, margin=0.06):
    """Returns a size*size list of (r,g,b,a) tuples for the icon at `size` px."""
    outer = scale_polygon(SHIELD, OUTLINE_SCALE)
    ss = size * SUPERSAMPLE
    # Map unit-square shield coords into the pixel grid, leaving `margin`
    # of empty space on each side so the icon isn't edge-to-edge.
    span = 1 - 2 * margin

    def to_px(polygon):
        return [(margin + x * span, margin + y * span) for x, y in polygon]

    outer_px = to_px(outer)
    inner_px = to_px(SHIELD)

    hits_outer = [[False] * ss for _ in range(ss)]
    hits_inner = [[False] * ss for _ in range(ss)]
    for j in range(ss):
        py = (j + 0.5) / ss
        for i in range(ss):
            px = (i + 0.5) / ss
            if point_in_polygon(px, py, outer_px):
                hits_outer[j][i] = True
                if point_in_polygon(px, py, inner_px):
                    hits_inner[j][i] = True

    pixels = [[(0, 0, 0, 0)] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            outer_count = 0
            inner_count = 0
            for dy in range(SUPERSAMPLE):
                row_o = hits_outer[y * SUPERSAMPLE + dy]
                row_i = hits_inner[y * SUPERSAMPLE + dy]
                base = x * SUPERSAMPLE
                for dx in range(SUPERSAMPLE):
                    if row_o[base + dx]:
                        outer_count += 1
                    if row_i[base + dx]:
                        inner_count += 1
            total = SUPERSAMPLE * SUPERSAMPLE
            outer_alpha = round(255 * outer_count / total)
            inner_alpha = round(255 * inner_count / total)
            if inner_alpha > 0:
                # Black fill; alpha blends the anti-aliased inner edge.
                pixels[y][x] = (0, 0, 0, inner_alpha)
            elif outer_alpha > 0:
                # Thin white outline ring where we're inside the outer shape
                # but outside the inner (black) one — keeps the icon legible
                # on dark backgrounds even though the fill itself is black.
                pixels[y][x] = (255, 255, 255, outer_alpha)
    return pixels


def _chunk(tag, data):
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(pixels, size):
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return header + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def build_ico(entries):
    """entries: list of (size, png_bytes), largest last for readability only."""
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)
    directory = b""
    data = b""
    offset = 6 + 16 * count
    for size, png_bytes in entries:
        dim = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png_bytes), offset
        )
        data += png_bytes
        offset += len(png_bytes)
    return header + directory + data


def main():
    master = rasterize(256)
    master_png = encode_png(master, 256)
    (OUT_DIR / "icon.png").write_bytes(master_png)

    entries = []
    for size in ICO_SIZES:
        pixels = master if size == 256 else rasterize(size)
        entries.append((size, encode_png(pixels, size)))

    (OUT_DIR / "icon.ico").write_bytes(build_ico(entries))
    print("wrote", OUT_DIR / "icon.png", "and", OUT_DIR / "icon.ico", "sizes:", ICO_SIZES)


if __name__ == "__main__":
    main()
