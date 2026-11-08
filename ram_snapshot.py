"""Debugger-friendly Space Invaders RAM snapshot; no dependency on Pygame.

This is *not* a CPU breakpoint facility: the Python translation has no
8080 program counter. F9 gives deterministic RAM and simulated-tick values
for manually matching a paused MAME breakpoint/state.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import re

_SNAPSHOT = re.compile(r"^state_(\d{6})_tick\d+_frame\d+\.txt$")

WATCH = (
    (0x20EC, 'attract presentation selector'),
    (0x20ED, 'demo command pointer low'),
    (0x20EE, 'demo command pointer high'),
    (0x20EF, 'game mode'),
    (0x201D, 'demo command'),
    (0x2015, 'player state (FF alive)'),
    (0x2016, 'player death timer'),
    (0x2025, 'player shot status'),
    (0x2002, 'alien explosion flag'),
    (0x2003, 'alien explosion timer'),
    (0x2006, 'alien cursor'),
    (0x2007, 'movement delta Y'),
    (0x2008, 'movement delta X'),
    (0x2009, 'alien reference Y'),
    (0x200A, 'alien reference X'),
    (0x200D, 'alien direction'),
    (0x2082, 'remaining aliens'),
    (0x20EB, 'credits (BCD)'),
    (0x2067, 'current player RAM page'),
    (0x21FF, 'player 1 reserve ships'),
    (0x22FF, 'player 2 reserve ships'),
)


def snapshot_text(rack, tick, *, phase='unknown', mode='unknown'):
    m = rack.mem
    lines = [
        '# Space Invaders 1978 Python RAM snapshot',
        f'# tick={tick} rack_frame={rack.frames} phase={phase} mode={mode}',
        '# tick counts Python simulation steps, NOT MAME CPU cycles or instructions',
        '# RAM dump can be compared against MAME debugger: d 2000',
        f'# VRAM SHA256={hashlib.sha256(bytes(m[0x2400:0x4000])).hexdigest()}',
        '# IMPORTANT: input can be sampled at different halves of the original interrupts',
        '', '# Selected original 8080 addresses',
    ]
    lines += [f'{addr:04X} = {m[addr]:02X}  {meaning}' for addr, meaning in WATCH]
    lines += ['', '# Full 8080 RAM 2000-23FF (16 bytes per row)']
    for addr in range(0x2000, 0x2400, 16):
        lines.append(f'{addr:04X}: ' + ' '.join(f'{b:02X}' for b in m[addr:addr+16]))
    return '\n'.join(lines) + '\n'


class RamSnapshots:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.next_number = None

    def capture(self, rack, tick, *, phase='unknown', mode='unknown'):
        self.folder.mkdir(parents=True, exist_ok=True)
        if self.next_number is None:
            nums = (int(mt.group(1)) for p in self.folder.iterdir()
                    if p.is_file() and (mt := _SNAPSHOT.fullmatch(p.name)))
            self.next_number = max(nums, default=0) + 1
        while True:
            name = (f'state_{self.next_number:06d}_tick{tick:08d}'
                    f'_frame{rack.frames:08d}.txt')
            path = self.folder / name
            self.next_number += 1
            if not path.exists():
                break
        # Exclusive creation prevents accidental overwrites between runs.
        with path.open('x', encoding='ascii') as f:
            f.write(snapshot_text(rack, tick, phase=phase, mode=mode))
        return path
