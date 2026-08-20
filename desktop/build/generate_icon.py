"""Generates the app icon: a plain solid black square, no transparency.
Produces icon.png (256x256) and a multi-resolution icon.ico
(16/32/48/64/128/256). No image library dependency — pure Python.
"""
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
ICO_SIZES = [16, 32, 48, 64, 128, 256]
COLOR = (0, 0, 0, 255)


def _chunk(tag, data):
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(size, color):
    row = bytes([0]) + bytes(color) * size
    raw = row * size
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw, 9)
    return header + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def build_ico(entries):
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
    master_png = encode_png(256, COLOR)
    (OUT_DIR / "icon.png").write_bytes(master_png)

    entries = [(size, encode_png(size, COLOR)) for size in ICO_SIZES]
    (OUT_DIR / "icon.ico").write_bytes(build_ico(entries))
    print("wrote", OUT_DIR / "icon.png", "and", OUT_DIR / "icon.ico", "sizes:", ICO_SIZES)


if __name__ == "__main__":
    main()
