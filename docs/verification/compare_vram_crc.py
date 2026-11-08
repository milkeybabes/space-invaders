"""Compare MAME frame-done VRAM to Python AVI-side VRAM hashes.

Usage (from repository root):
  python docs/verification/compare_vram_crc.py MAME_VRAM.csv PYTHON_RECORDING.csv

Both runs must start at their respective frame zero; do not trigger
recording via F8 after gameplay has already advanced. The Python CSV's
video_frame is the monotonic index; game_frame resets during attract mode.
"""
import argparse
import csv
from pathlib import Path
import zlib


def compare(mame_path: Path, python_path: Path, offset: int = 0) -> int:
    with mame_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not {"frame", "vram_2400_3fff_hex"}.issubset(reader.fieldnames or ()):
            raise ValueError("MAME CSV missing frame or vram_2400_3fff_hex column")
        mame = {}
        for row in reader:
            data = bytes.fromhex(row["vram_2400_3fff_hex"])
            if len(data) != 7168:
                raise ValueError(f"MAME frame {row['frame']}: expected 7168 VRAM bytes")
            mame[int(row["frame"])] = f"{zlib.crc32(data):08X}"

    checked = 0
    errors = 0
    with python_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not {"video_frame", "vram_crc32"}.issubset(reader.fieldnames or ()):
            raise ValueError("Python CSV needs video_frame and vram_crc32; record with v1.0 --record-avi")
        for row in reader:
            video_frame = int(row["video_frame"])
            mame_frame = video_frame + offset
            if mame_frame not in mame:
                continue
            checked += 1
            expected = mame[mame_frame]
            actual = row["vram_crc32"].upper().zfill(8)
            if actual != expected:
                errors += 1
                if errors <= 20:
                    print(f"MISMATCH: MAME {mame_frame} vs AVI {video_frame}: {expected} != {actual}")
    print(f"VRAM CRC matches: {checked - errors}/{checked} across overlapping frames (offset={offset})")
    if checked == 0:
        print("No overlapping frames; check your frame range, recording start and offset.")
        return 2
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mame_vram_csv", type=Path)
    parser.add_argument("python_recording_csv", type=Path)
    parser.add_argument("--offset", type=int, default=0,
                        help="MAME frame number minus Python AVI video_frame (default 0)")
    args = parser.parse_args()
    raise SystemExit(compare(args.mame_vram_csv, args.python_recording_csv, args.offset))


if __name__ == "__main__":
    main()
