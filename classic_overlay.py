"""Presentation-only Midway Space Invaders colour-cellophane overlay.

Native upright coordinates and exact MAME default.lay bounds.
Never writes to Rack memory, video RAM, or the source monochrome image.
"""
from __future__ import annotations

WIDTH, HEIGHT = 224, 256
WHITE = b"\xff\xff\xff"
RED = b"\xff\x00\x00"       # User-supplied overlay.png colour (#FF0000)
GREEN = b"\x63\xf6\x18"     # User-supplied overlay.png colour (#63F618)
BLACK = b"\x00\x00\x00"


def tint_luma(luma: bytes, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """RGB24, pixel-exact; preserve black and tint only lit pixels."""
    if len(luma) != width * height:
        raise ValueError("Source image dimensions disagree with luma length")
    out = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            i = y * width + x
            if not luma[i]:
                continue
            # MAME default.lay colour rectangles, in upright output pixels.
            if 33 <= y < 62:
                color = RED
            elif 184 <= y < 240 or (240 <= y < 260 and 16 <= x < 134):
                color = GREEN
            else:
                color = WHITE
            out[3*i:3*i+3] = color
    return bytes(out)
