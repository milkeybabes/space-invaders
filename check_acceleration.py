"""Stage 1 verification: original $0141 / $01A1 alien cursor acceleration.

Runs directly from Command Prompt, using ONLY Python's standard library.
This is an *isolated routine test*, not an arcade/MAME comparison.

For isolated timing, the provisional Stage-1 per-frame RackBump call is
suppressed on each test instance. It is *not* changed in rack.py or in the
normal visual game. Alien-count fixtures are synthetic, not gameplay rules.
"""
from __future__ import annotations
import sys
from pathlib import Path as _ToolPath
sys.path.insert(0, str(_ToolPath(__file__).resolve().parents[2]))


import argparse
import csv
from pathlib import Path
import random
import sys

from rack import Rack

CASES = (55, 40, 20, 10, 5, 1)
CYCLES = 6


def survivor_indices(n: int, pattern: str) -> tuple[int, ...]:
    if not 1 <= n <= 55:
        raise ValueError(n)
    if pattern == 'consecutive':
        return tuple(range(n))
    if pattern == 'scattered':
        if n == 1:
            return (0,)
        # Keep index 0 live (the boot cursor is 0), then scatter survivors
        # all the way up to position 54 to prove that dead indices are skipped.
        middle = random.Random(1978 + n).sample(range(1, 54), n - 2)
        return tuple(sorted((0, 54, *middle)))
    raise ValueError(pattern)


def run_case(n: int, pattern: str, *, cycles: int = CYCLES) -> tuple[dict, list[dict]]:
    indices = survivor_indices(n, pattern)
    rack = Rack(surviving=n)
    rack.mem[0x2100:0x2137] = bytes(int(i in indices) for i in range(55))
    rack.mem[0x2082] = n

    # The original $1597 bump routine is implemented in Rack, but its
    # Stage 1 *calling frequency* isn't ported from the original main loop.
    # It must not influence this isolated movement-period test.
    rack.rack_bump = lambda: None

    events = []
    expected_step_frames = [1 + n * cycle for cycle in range(1, cycles + 1)]
    expected_draw_indices = tuple(sorted(indices))
    total_frames = expected_step_frames[-1]
    observed_step_frames = []
    for frame in range(1, total_frames + 1):
        before = rack.rack_steps
        rack.step_frame()
        assert rack.mem[0x2000] == 0, f'pending-draw flag stuck at frame {frame}'
        assert rack.alive == n, 'count/flag fixture changed unexpectedly'
        expected_index = expected_draw_indices[(frame - 1) % n]
        assert rack.last_drawn == expected_index, (
            f'{pattern} n={n} frame={frame}: drawn {rack.last_drawn}, '
            f'expected {expected_index}'
        )
        expected_steps = (frame - 1) // n
        assert rack.rack_steps == expected_steps, (
            f'{pattern} n={n} frame={frame}: steps {rack.rack_steps}, '
            f'expected {expected_steps}'
        )
        assert rack.frame_number == (expected_steps & 1)
        assert rack.reference == (0x78, (0x38 + 2 * expected_steps) & 0xff)
        if rack.rack_steps != before:
            observed_step_frames.append(frame)
            events.append({
                'survivors': n,
                'pattern': pattern,
                'step': rack.rack_steps,
                'frame': frame,
                'cursor': rack.current,
                'ref_x_hex': f'{rack.reference[0]:02X}',
                'ref_y_hex': f'{rack.reference[1]:02X}',
                'animation': rack.frame_number,
                'vram_sha256': rack.framebuffer_digest(),
            })
    assert observed_step_frames == expected_step_frames, (
        f'Event frames mismatch for n={n} {pattern}: '
        f'{observed_step_frames} != {expected_step_frames}'
    )
    return ({
        'survivors': n,
        'pattern': pattern,
        'frames_per_step': n,
        'first_step_frame': observed_step_frames[0],
        '6th_step_frame': observed_step_frames[-1],
        'steps_per_second_60hz': 60 / n,
        'result': 'PASS',
    }, events)


def edge_checks() -> list[str]:
    """Force original `$1597` edge-VRAM bytes and inspect RAM results."""
    results: list[str] = []
    one = Rack(surviving=1)
    one.mem[0x3EA4 + 23] = 1  # outside the $17-byte test window
    one.rack_bump()
    assert one.mem[0x200D] == 0 and one.mem[0x2008] == 2
    results.append('Right margin: byte +23 ignored (scan covers exactly 23 bytes)')

    one.mem[0x3EA4 + 22] = 1  # last byte inside scanned line
    one.rack_bump()
    assert (one.mem[0x200D], one.mem[0x2008], one.mem[0x2007]) == (1, 0xFE, 0xF8)
    one.move_ref_alien()
    assert one.reference == (0x70, 0x36), one.reference
    assert one.mem[0x2007] == 0  # drop applied once only
    results.append('Right edge: reverse to -2, and arm one-shot -8 rack drop')

    one.mem[0x2524 + 22] = 1
    one.rack_bump()
    assert (one.mem[0x200D], one.mem[0x2008], one.mem[0x2007]) == (0, 3, 0xF8)
    one.move_ref_alien()
    assert one.reference == (0x68, 0x39), one.reference
    results.append('Left edge / 1 alien: reverse to +3, and apply -8 drop')

    two = Rack(surviving=2)
    two.mem[0x200D] = 1
    two.mem[0x2008] = 0xFE
    two.mem[0x2524] = 1
    two.rack_bump()
    assert (two.mem[0x200D], two.mem[0x2008], two.mem[0x2007]) == (0, 2, 0xF8)
    results.append('Left edge / 2 aliens: reverse to normal +2 (not +3)')
    return results


def run_checks() -> tuple[list[dict], list[dict], list[str]]:
    summary, events = [], []
    for n in CASES:
        for pattern in ('consecutive', 'scattered'):
            if n in (55, 1) and pattern == 'scattered':
                continue  # same mask as consecutive, no duplicate data
            row, case_events = run_case(n, pattern)
            summary.append(row)
            events.extend(case_events)
    edges = edge_checks()
    return summary, events, edges


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('test_results'),
                        help='where to save CSV files (default: test_results)')
    args = parser.parse_args()
    try:
        summary, events, edges = run_checks()
    except AssertionError as exc:
        print(f'FAILED: {exc}', file=sys.stderr)
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / 'acceleration_summary.csv', summary)
    write_csv(args.output / 'reference_step_events.csv', events)

    print('SPACE INVADERS 1978 — STAGE 1 ACCELERATION CHECK')
    print('Source: original ROM $0141 CursorNextAlien / $01A1 MoveRefAlien')
    print('Mode: isolated 60 Hz cursor test (provisional edge caller disabled)')
    print()
    print(' Live   Pattern       Frames/step   First step   Step 6   Result')
    print(' ----   -----------   -----------   ----------   ------   ------')
    for row in summary:
        print(f" {row['survivors']:>4}   {row['pattern']:<11}   "
              f"{row['frames_per_step']:>11}   "
              f"{row['first_step_frame']:>10}   "
              f"{row['6th_step_frame']:>6}   {row['result']}")
    print('\nEDGE LOGIC (forced boundary VRAM data):')
    for line in edges:
        print(f'  PASS — {line}')
    print(f'\nPASS: {len(summary)} cursor fixtures, {len(events)} step events, '
          f'{len(edges)} edge assertions.')
    print(f'Saved: {args.output / "acceleration_summary.csv"}')
    print(f'Saved: {args.output / "reference_step_events.csv"}')
    print('\nIMPORTANT: these prove the translated Stage 1 routines match the')
    print('specified assembly-derived expectations, NOT full MAME equivalence.')


if __name__ == '__main__':
    main()
