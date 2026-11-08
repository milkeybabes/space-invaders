"""Dependency-free, native-resolution 8-bit grayscale AVI recorder for 8080 VRAM.

Captures one lossless frame per *simulated* game tick (not per pygame render
or desktop screen refresh).  Uses standard uncompressed indexed AVI (DIB) and
writes a frame-indexed CSV alongside it for deterministic MAME comparison.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
from fractions import Fraction
from pathlib import Path
import struct
import zlib


# The game generates binary grayscale luma, so an indexed 8-bit AVI retains
# every pixel while occupying one-third as much space as RGB24 AVI.
_PALETTE = b'\x00\x00\x00\x00\xff\xff\xff\x00'
_LUMA_TO_INDEX = bytes(1 if n else 0 for n in range(256))

# The exact native video timebase read from MAME's original invaders AVI
# stream header. This tags AVI timestamps only; it does not change the
# simulated 60 Hz Python update interval or modify 8080 game timing.
MAME_AVI_RATE = Fraction(268435455, 4508339)  # 59.5419854... frames/s


def next_recording_path(folder: Path, label: str = 'SpaceInvaders') -> Path:
    """Return an unused recording name; never overwrite existing evidence."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = folder / f'{label}_{stamp}.avi'
    n = 1
    while base.exists() or base.with_suffix('.csv').exists():
        base = folder / f'{label}_{stamp}_{n:02d}.avi'
        n += 1
    return base


class NativeAVIRecorder:
    """Write silent native-frame AVI with selectable rational fps + CSV.

    AVI's legacy RIFF offsets are 32-bit.  For safety, recordings stop before
    the 4 GiB limit; close() always writes the index and fixes the headers.
    """

    def __init__(self, path: Path, width: int = 224, height: int = 256,
                 fps: int | Fraction = 60) -> None:
        self.path = Path(path)
        if self.path.suffix.lower() != '.avi':
            raise ValueError('AVI path must end in .avi')
        fps = Fraction(fps)
        if (width <= 0 or height <= 0 or width > 32767 or height > 32767
                or fps <= 0 or fps.numerator >= 2**32 or fps.denominator >= 2**32):
            raise ValueError('Invalid AVI dimensions or frame rate')
        if self.path.exists() or self.path.with_suffix('.csv').exists():
            raise FileExistsError(f'Recording already exists: {self.path}')
        self.width, self.height, self.fps = width, height, float(fps)
        self.fps_rate, self.fps_scale = fps.numerator, fps.denominator
        self.row_bytes = (width + 3) & ~3
        self.image_bytes = self.row_bytes * height
        self._pad = b'\x00' * (self.row_bytes - width)
        self.frames = 0
        self.closed = False
        self._idx = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('xb')
        self.csv_path = self.path.with_suffix('.csv')
        try:
            self.csv_file = self.csv_path.open('x', encoding='utf-8', newline='')
        except BaseException:
            self.file.close()
            self.path.unlink(missing_ok=True)
            raise
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['video_frame', 'simulation_tick', 'game_frame',
                                  'mode', 'phase', 'player_x_201B', 'demo_command_201D',
                                  'shot_status_2025', 'missile_status_2073',
                                  'native_luma_sha256', 'vram_crc32', 'vram_sha256', 'vram_bytes', 'sampling_point'])
        try:
            self._start_headers()
        except BaseException:
            self.file.close()
            self.csv_file.close()
            self.path.unlink(missing_ok=True)
            self.csv_path.unlink(missing_ok=True)
            raise

    def _chunk(self, fourcc: bytes, data: bytes) -> None:
        self.file.write(fourcc)
        self.file.write(struct.pack('<I', len(data)))
        self.file.write(data)
        if len(data) & 1:
            self.file.write(b'\x00')

    def _start_headers(self) -> None:
        f = self.file
        f.write(b'RIFF\0\0\0\0AVI ')
        hdrl_start = f.tell()
        f.write(b'LIST\0\0\0\0hdrl')
        self.avih_pos = f.tell() + 8
        self._chunk(b'avih', struct.pack(
            '<IIIIIIIIII4I', round(1_000_000 * self.fps_scale / self.fps_rate),
            round((self.image_bytes + 8) * self.fps), 0, 0x10,
            0, 0, 1, self.image_bytes, self.width, self.height, 0, 0, 0, 0))
        strl_start = f.tell()
        f.write(b'LIST\0\0\0\0strl')
        self.strh_pos = f.tell() + 8
        self._chunk(b'strh', struct.pack(
            '<4s4sIHHIIIIIIIIhhhh', b'vids', b'DIB ', 0, 0, 0,
            0, self.fps_scale, self.fps_rate, 0, 0, self.image_bytes, 0xFFFFFFFF,
            0, 0, 0, self.width, self.height))
        self._chunk(b'strf', struct.pack('<IiiHHIIiiII',
            40, self.width, self.height, 1, 8, 0,
            self.image_bytes, 0, 0, 2, 2) + _PALETTE)
        strl_end = f.tell()
        f.seek(strl_start + 4)
        f.write(struct.pack('<I', strl_end - strl_start - 8))
        f.seek(strl_end)
        hdrl_end = f.tell()
        f.seek(hdrl_start + 4)
        f.write(struct.pack('<I', hdrl_end - hdrl_start - 8))
        f.seek(hdrl_end)
        self.movi_start = f.tell()
        f.write(b'LIST\0\0\0\0movi')
        self.movi_data_start = f.tell()

    def write_frame(self, luma: bytes, tick: int, game_frame: int,
                    mode: str = '', phase: str = '', rack=None) -> None:
        if self.closed:
            raise RuntimeError('AVI recorder is closed')
        if len(luma) != self.width * self.height:
            raise ValueError(f'Expected {self.width * self.height} luma bytes, got {len(luma)}')
        # Refuse before the AVI index or RIFF size could overflow 32 bits.
        if self.file.tell() + self.image_bytes + 32 + (self.frames + 1) * 16 >= 0xF0000000:
            raise OverflowError('AVI is near the 4 GB format limit; stop and start a new recording')
        f = self.file
        position = f.tell()
        f.write(b'00db')  # uncompressed video frame
        f.write(struct.pack('<I', self.image_bytes))
        indexed = luma.translate(_LUMA_TO_INDEX)
        # AVI DIB rows are stored bottom-up, while portrait_luma() is top-down.
        for y in range(self.height - 1, -1, -1):
            f.write(indexed[y*self.width:(y+1)*self.width])
            if self._pad:
                f.write(self._pad)
        self._idx.append((position - self.movi_data_start + 4, self.image_bytes))
        m = rack.mem if rack is not None else None
        vram = bytes(m[0x2400:0x4000]) if m is not None else None
        self.csv_writer.writerow([
            self.frames, tick, game_frame, mode, phase,
            f'{m[0x201B]:02X}' if m is not None else '',
            f'{m[0x201D]:02X}' if m is not None else '',
            f'{m[0x2025]:02X}' if m is not None else '',
            f'{m[0x2073]:02X}' if m is not None else '',
            hashlib.sha256(luma).hexdigest(),
            f'{zlib.crc32(vram):08X}' if vram is not None else '',
            hashlib.sha256(vram).hexdigest() if vram is not None else '',
            len(vram) if vram is not None else '',
            'simulation_tick_before_pygame_display',
        ])
        self.frames += 1
        if self.frames % 60 == 0:
            self.csv_file.flush()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        f = self.file
        try:
            movi_end = f.tell()
            if movi_end & 1:
                f.write(b'\x00')
            idx_data = b''.join(struct.pack('<4sIII', b'00db', 0x10, offset, size)
                                for offset, size in self._idx)
            self._chunk(b'idx1', idx_data)
            end = f.tell()
            f.seek(self.movi_start + 4)
            f.write(struct.pack('<I', movi_end - self.movi_start - 8))
            f.seek(self.avih_pos + 16)  # avih.dwTotalFrames
            f.write(struct.pack('<I', self.frames))
            f.seek(self.strh_pos + 32)  # strh.dwLength
            f.write(struct.pack('<I', self.frames))
            f.seek(4)
            f.write(struct.pack('<I', end - 8))
            f.flush()
        finally:
            f.close()
            self.csv_file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
