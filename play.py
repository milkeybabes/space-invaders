"""Space Invaders (1978) — Python v1.0 arcade launcher.

This entry point selects the fully tested Stage 17z arcade configuration.
The translated game code itself is preserved unchanged.

Examples:
    python play.py
    python play.py --record-avi
    python play.py --scale 4
"""
from __future__ import annotations

import sys
from main import main


if __name__ == "__main__":
    # The v1 release configuration previously selected in the Stage 17z
    # Windows launcher. Diagnostic alternatives remain available in main.py.
    sys.argv = [sys.argv[0], '--arcade', '--attract-preview',
                '--experimental-continuation',
                '--experimental-rom-ram-lifecycle',
                '--experimental-isr-player-order',
                '--experimental-death-handoff', *sys.argv[1:]]
    main()
