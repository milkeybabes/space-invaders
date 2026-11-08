"""Native Space Invaders VRAM captures, independent of pygame and game logic."""
from __future__ import annotations

from pathlib import Path
import re

from main import save_native_png

_CAPTURE_NAME = re.compile(r'^(\d{6})_tick\d+_frame\d+\.png$')


class ScreenCaptures:
    """Keep a run-independent numbered sequence in a dedicated capture folder."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.next_number: int | None = None

    def capture(self, rack, tick: int) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        # Scan only on first capture in a run; later names are monotonically increasing.
        if self.next_number is None:
            indices = (int(m.group(1)) for p in self.folder.iterdir()
                       if p.is_file() and (m := _CAPTURE_NAME.fullmatch(p.name)))
            self.next_number = max(indices, default=0) + 1
        # Do not replace earlier pictures, including pictures from another process.
        while True:
            name = f'{self.next_number:06d}_tick{tick:08d}_frame{rack.frames:08d}.png'
            target = self.folder / name
            self.next_number += 1
            if not target.exists():
                break
        save_native_png(target, rack)
        return target
