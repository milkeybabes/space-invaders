"""Source-level translation of the original 1978 shield/ground routines.

See https://computerarcheology.com/Arcade/SpaceInvaders/Code.html

$01EF/$01F5 DrawShieldPl1/2; $021A/$0213 RestoreShields1/2;
$0209/$020E RememberShields1/2; $021E CopyShields;
$1A69 RestoreShields (OR); $147C RememberShields (copy);
$01CF DrawBottomLine / $14CC original fixed-byte drawing loop.

Shield damage is NOT a separate health/damage system: the bullets' original
$1491/$1400/$1452 framebuffer bit operations make the actual holes.
"""
from __future__ import annotations

# Entire 44-byte original sprite data at ROM $1D20..$1D4B.
SHIELD_IMAGE = bytes.fromhex('''
    FF 0F FF 1F FF 3F FF 7F FF FF FC FF F8 FF F0 FF F0 FF F0 FF F0 FF
    F0 FF F0 FF F0 FF F8 FF FC FF FF FF FF FF FF 7F FF 3F FF 1F FF 0F
''')
assert len(SHIELD_IMAGE) == 44

SHIELD_START = 0x2806  # $0224, first shield's first VRAM byte
SHIELD_ROWS = 0x16  # 22 screen-RAM rows (portrait horizontal extent)
SHIELD_COLS = 2  # each 16 vertical pixels
SHIELD_GAP = 0x17  # 23 32-byte VRAM rows *after* each complete shield
SHIELD_PITCH = SHIELD_ROWS + SHIELD_GAP  # 45 portrait pixels
SHIELD_COUNT = 4
PLAYER1_BUFFER = 0x2142
PLAYER2_BUFFER = 0x2242
GROUND_START = 0x2402
GROUND_ROWS = 0xE0  # 224 portrait pixels


class Shields:
    def __init__(self, rack):
        self.rack = rack

    @staticmethod
    def buffer_for_player(player: int) -> int:
        if player == 1:
            return PLAYER1_BUFFER
        if player == 2:
            return PLAYER2_BUFFER
        raise ValueError('player must be 1 or 2')

    def init_shields(self, player: int = 1) -> None:
        """$01EF/$01F5: replicate 44 ROM bytes 4 times in player RAM.

        The assembly initialises *buffer memory*, not the framebuffer.
        """
        m = self.rack.mem
        base = self.buffer_for_player(player)
        for n in range(SHIELD_COUNT):
            pos = base + n * len(SHIELD_IMAGE)
            m[pos:pos + len(SHIELD_IMAGE)] = SHIELD_IMAGE

    def transfer_shields(self, player: int = 1, *, remember: bool = False) -> None:
        """$021E CopyShields and its called $1A69 OR / $147C copy.

        Remember: VRAM -> player buffer (store damage for two-player game).
        Restore: player buffer OR VRAM (do NOT reset damaged shield).
        The $023A addition of $02E0 occurs AFTER processing 22 VRAM rows.
        """
        m = self.rack.mem
        base = self.buffer_for_player(player)
        vram = SHIELD_START
        for shield in range(SHIELD_COUNT):
            buffer = base + shield * len(SHIELD_IMAGE)
            for row in range(SHIELD_ROWS):
                for col in range(SHIELD_COLS):
                    address = vram + row * 32 + col
                    value = m[address]
                    if remember:
                        m[buffer + row * 2 + col] = value
                    else:
                        m[address] = value | m[buffer + row * 2 + col]
            vram += SHIELD_PITCH * 32

    def remove_barriers_for_diagnostic(self) -> None:
        """TEST ONLY: remove four shield images while retaining the floor.

        Clear only the shield pixels and their RAM backing buffers; do not
        touch the baseline, missile algorithms, explosion masks or timers.
        This is not a translation of an original game routine.
        """
        m = self.rack.mem
        for player in (1, 2):
            base = self.buffer_for_player(player)
            m[base:base + SHIELD_COUNT * len(SHIELD_IMAGE)] = bytes(SHIELD_COUNT * len(SHIELD_IMAGE))
        for shield in range(SHIELD_COUNT):
            first = SHIELD_START + shield * SHIELD_PITCH * 32
            for row in range(SHIELD_ROWS):
                m[first + row * 32:first + row * 32 + SHIELD_COLS] = bytes(SHIELD_COLS)

    def draw_bottom_line(self) -> None:
        """$01CF DrawBottomLine -> $14CC, NOT a dotted-line asset.

        A=$01; HL=$2402; B=$E0; LD(HL),A; HL += $20 repeated 224 times.
        Unlike a redraw every frame, it is a one-time startup operation.
        Subsequent shots may erase some of these same VRAM bits.
        """
        m = self.rack.mem
        for col in range(GROUND_ROWS):
            m[GROUND_START + 32 * col] = 1

    def init_playfield(self, player: int = 1) -> None:
        """Explicit diagnostic setup: create shields, restore them, draw line.

        Real ROM startup also has playfield clearing, score/lives drawing,
        and start logic; these are NOT claimed to be translated here.
        """
        self.init_shields(player)
        self.transfer_shields(player)
        self.draw_bottom_line()
