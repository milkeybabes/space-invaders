"""Space Invaders 1978 -- Stage 4 source translations: player shot and scoring.

The *source-of-truth* for every routine listed is the annotated Midway
8080 disassembly: https://computerarcheology.com/Arcade/SpaceInvaders/Code.html

Original ROM routine mapping:
  $1618 PlrFireOrDemo (game mode, debounced fire)
  $03BB GameObj1; $03FA InitPlyShot; $040A MovePlyShot
  $0430 ReadPlyShot; $0436 EndOfBlowup
  $1400 DrawShiftedSprite; $1452 EraseShifted; $1491 DrawSprCollision
  $14D8 PlayerShotHit; $1504 CodeBug1; $1554 Cnt16s
  $1562 FindRow; $156F FindColumn; $1581 GetAlienStatPtr
  $0A5F ScoreForAlien; $097C AlienScoreValue; $0988 AdjustScore
  $1538 AExplodeTime.

No bounding-box substitute: collision is bitwise AND of the shifted shot
and the existing frame-buffer bits, then OR of the shot sprite onto video RAM.
The alien explosion uses $15D3 DrawSprite, which OVERWRITES the previous
alien pixels rather than ORing the explosion with them.
The original incorrect row/column wrap calculation is intentionally kept.

LIMITATIONS:
  This uses Stage 2's one-main-pass-per-frame *diagnostic* scheduler, not
  CPU-cycle exact continuous main-loop execution. Scores are kept as BCD in
  original RAM, but original character drawing is NOT implemented yet.
  Shields, enemy shots, saucer, multi-player, death, new waves and SFX remain
  unported. This is a combat test, not yet full arcade equivalence.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rack import Rack


# Byte-perfect ROM graphics used by the Stage-4 port (sprite data, not redesigns).
PLAYER_SHOT_AND_BLOWUP = bytes.fromhex('0F 99 3C 7E 3D BC 3E 7C 99')
ALIEN_EXPLOSION = bytes.fromhex('00 08 49 22 14 81 42 00 42 81 14 22 49 08 00 00')


def bcd_to_decimal(low: int, high: int) -> int:
    return 1000 * (high >> 4) + 100 * (high & 15) + 10 * (low >> 4) + (low & 15)


def add_bcd_byte(lhs: int, rhs: int, carry: int = 0) -> tuple[int, int]:
    """8080 ADD/ADC + DAA for the original two valid packed BCD bytes."""
    raw = lhs + rhs + carry
    low_fix = ((lhs & 15) + (rhs & 15) + carry > 9)
    adjust = 0x06 if low_fix else 0
    if raw > 0x99 or raw > 0xFF or (raw + adjust) > 0x99:
        adjust += 0x60
    result = raw + adjust
    return result & 0xFF, int(result > 0xFF)


class Combat:
    def __init__(self, rack: 'Rack'):
        self.rack = rack
        self.events: list[tuple[int, str, int]] = []
        self.hits: list[int] = []
        self.shots_fired = 0
        # Native per-frame scheduling guard for a just-initialized shot.
        # The 8080's two IRQ handlers run at distinct beam times; this
        # translation groups their work into one Python frame.
        self._demo_shot_start_frame = -1

    @property
    def score(self) -> int:
        m = self.rack.mem
        base = 0x20F8 if m[0x2067] & 1 else 0x20FC
        return bcd_to_decimal(m[base], m[base+1])

    def record(self, event: str, value: int = 0) -> None:
        self.events.append((self.rack.frames + 1, event, value))

    def fire_from_controls(self) -> None:
        """$1618/$1632 PlrFireOrDemo (active game, player 1/2)."""
        m = self.rack.mem
        if m[0x2015] != 0xFF:   # $1618 player alive
            return
        if m[0x2010] or m[0x2011]:  # $161E player timer
            return
        if m[0x2025]:         # $1626 one active player missile
            return
        if not m[0x20EF]:
            return           # Demo handler $1652 not yet ported
        fire = bool(self.rack.read_inputs() & 0x10)
        if m[0x202D]:        # $1648 button bounce/held flag
            if not fire:
                m[0x202D] = 0
            return
        if fire:
            m[0x2025] = 1
            m[0x202D] = 1
            self.shots_fired += 1
            self.record('FIRE_REQUEST', m[0x201B])

    def _shot_desc(self) -> tuple[int, int, int, int]:
        m = self.rack.mem
        image = m[0x2027] | (m[0x2028] << 8)
        return m[0x2029], m[0x202A], image, m[0x202B]

    def _sprite_shift(self, x: int, y: int, image: int, rows: int,
                      operation: str) -> bool:
        """Original pixel-byte shifts and *OR/AND-NOT* VRAM operations.

        $1400 draw / $1452 erase / $1491 draw+collision. The original
        writes the second shifted byte even when that byte is zero.
        """
        m = self.rack.mem
        addr, shift = self.rack.pixel_to_address(x, y)
        overlap = False
        for row in range(rows):
            source = m[(image + row) & 0x3FFF]
            parts = ((source << shift) & 255,
                     (source >> (8 - shift)) if shift else 0)
            for col, part in enumerate(parts):
                dest = addr + row * 32 + col
                if 0x2400 <= dest < 0x4000:
                    old = m[dest]
                    if operation == 'collision' and (old & part):
                        overlap = True
                    if operation == 'erase':
                        m[dest] = old & (~part & 255)
                    else:
                        m[dest] = old | part
        if operation == 'collision':
            m[0x2061] = int(overlap)
        return overlap

    def draw_shot(self, operation: str = 'draw') -> bool:
        return self._sprite_shift(*self._shot_desc(), operation)

    def player_shot(self, base: int) -> str:
        """$03BB GameObj1, including status machine and beam phase gate."""
        if base != 0x2020:
            raise ValueError('shot object must use the original $2020 structure')
        m = self.rack.mem
        # $1A06 CompYToBeam: object screen-position MSB must match $2072.
        if (m[0x202A] & 0x80) != m[0x2072]:
            return 'SHOT_WRONG_BEAM'
        status = m[0x2025]
        if status == 0:
            return 'SHOT_INACTIVE'
        # MAME trace: shot #5 starts on frame 884 at Y=$28 and moves on
        # frame 885, even when its newly assigned X crosses $80. Without
        # this guard our grouped MID/END schedule initializes in MID,
        # re-qualifies the new X in END, and advances the same shot $04
        # immediately. That moves the hit from frame 904 to 903, altering
        # every later attract demo command and player death.
        # Do not impose this change on normal gameplay or stand-alone
        # combat fixtures; it is a phase correction for attract scheduling.
        if (status == 2 and m[0x20EF] == 0 and m[0x20C1] == 1
                and self._demo_shot_start_frame == self.rack.frames):
            return 'SHOT_INIT_ALREADY_THIS_FRAME'
        if status == 1:          # $03FA
            m[0x2025] = 2
            if m[0x20EF] == 0 and m[0x20C1] == 1:
                self._demo_shot_start_frame = self.rack.frames
            m[0x202A] = (m[0x201B] + 8) & 255
            self.draw_shot('draw')
            self.record('SHOT_START', m[0x202A])
            return 'SHOT_START'
        if status == 2:          # $040A
            self.draw_shot('erase')
            m[0x2029] = (m[0x2029] + m[0x202C]) & 255
            collision = self.draw_shot('collision')
            if collision:
                m[0x2002] = 1  # $0426, main loop $14D8 recognises it
                self.record('PIXEL_COLLISION', m[0x2029])
            return 'SHOT_COLLISION' if collision else 'SHOT_MOVE'
        if status == 5:          # $042A
            return 'SHOT_ALIEN_EXPLODING'
        if status == 3:          # $03D7
            m[0x2026] = (m[0x2026] - 1) & 255
            if m[0x2026] == 0:
                return self.end_of_blowup()
            if m[0x2026] != 0x0F:
                return 'SHOT_MISS_EXPLOSION_WAIT'
            self.draw_shot('erase')
            m[0x2027] = (m[0x2027] + 1) & 255
            m[0x2029] = (m[0x2029] - 2) & 255
            m[0x202A] = (m[0x202A] - 3) & 255
            m[0x202B] = 8
            self.draw_shot('draw')
            return 'SHOT_MISS_EXPLOSION_DRAW'
        return self.end_of_blowup()  # $042D status 4 and other non-5 states

    def end_of_blowup(self) -> str:
        """$0436-$0475: restore the $2025-$202B object from ROM mirror."""
        m = self.rack.mem
        self.draw_shot('erase')
        # Same 7 bytes as original $1B25..1B2B, not a fabricated reset.
        m[0x2025:0x202C] = bytes.fromhex('00 10 90 1C 28 30 01')
        # Saucer score pointer increments only LOW byte with 15-value wrap.
        saucer_ptr = m[0x208D]
        saucer_ptr = (saucer_ptr + 1) & 255
        m[0x208D] = 0x54 if saucer_ptr >= 0x63 else saucer_ptr
        m[0x208F] = (m[0x208F] + 1) & 255
        if not m[0x2084]:
            odd = m[0x208F] & 1
            m[0x208A] = 0x29 if odd else 0xE0
            m[0x208C] = 0x02 if odd else 0xFE
        self.record('SHOT_RESET')
        return 'SHOT_RESET'

    @staticmethod
    def _count16s(reference: int, target: int) -> tuple[int, int]:
        """$1554 Cnt16s and buggy $1590 WrapRef as 8-bit arithmetic."""
        a = reference & 255
        c = 0
        if a >= target:
            # $1590 adds at least 16, then *keeps going while signed bit set*.
            for _ in range(17):
                c = (c + 1) & 255
                a = (a + 0x10) & 255
                if not (a & 0x80):
                    break
            else:
                raise AssertionError('WrapRef did not terminate')
        for _ in range(17):
            if a >= target:
                return c, a
            a = (a + 0x10) & 255
            c = (c + 1) & 255
        raise AssertionError('Cnt16s did not terminate')

    def player_shot_hit(self) -> None:
        """$14D8: distinguish collision, screen top, enemy, and saucer.

        Player-shot collision ONLY comes from overlapping framebuffer bits.
        The original off-by-column bug is deliberately retained in lookup.
        """
        m = self.rack.mem
        if m[0x2025] != 2:     # $14D8 status 2 only
            return
        shot_vertical = m[0x2029]
        if shot_vertical >= 0xD8:
            self._non_alien_hit()
            return
        if not m[0x2002]:
            return
        if shot_vertical >= 0xCE:
            m[0x2085] = 1     # $1579 saucer hit; saucer is not active yet
            m[0x2025] = 4
            m[0x2002] = 0
            return
        target = (shot_vertical + 6) & 255
        reference = m[0x2009]
        if reference < 0x90 and reference >= target:
            self._non_alien_hit()
            return
        count_row, ref_end_row = self._count16s(reference, target)
        row = (count_row - 1) & 255
        x = (ref_end_row - 16) & 255
        col_count, ref_end_col = self._count16s(m[0x200A], m[0x202A])
        y = (ref_end_col - 16) & 255
        m[0x2064], m[0x2065] = x, y
        m[0x2025] = 5
        # $1581 computes 11*row + (column[1-based] - 1), wraps to 8 bits.
        index = ((row * 11) + col_count - 1) & 255
        ptr = (m[0x2067] << 8) | index
        if not m[ptr]:
            self._non_alien_hit()
            return
        m[ptr] = 0
        self.hits.append(index)
        self.record('ALIEN_HIT', index)
        self.score_for_alien(row)
        # $1524/$1527: ReadDesc then DrawSprite ($15D3). Unlike the
        # projectile's OR-to-VRAM routine ($1491), DrawSprite REPLACES both
        # framebuffer bytes on each of its 16 rows. Using _sprite_shift(...,
        # 'draw') here incorrectly ORed the explosion over the old alien,
        # producing a combined alien/splat image for the explosion period.
        # Preserve the original overwrite, including clearing zero bits.
        self.rack.draw_shifted_sprite(x, y, 0xC0)  # ROM source $1CC0
        m[0x2003] = 0x10

    def _non_alien_hit(self) -> None:
        m = self.rack.mem
        m[0x2025] = 3
        m[0x2002] = 0
        self.record('SHOT_NON_ALIEN_HIT', m[0x2029])

    def score_for_alien(self, row: int) -> None:
        """$0A5F-$0A7F: set BCD score delta, do NOT add immediately."""
        m = self.rack.mem
        if not m[0x20EF]:
            return
        m[0x20F3] = 0
        m[0x20F2] = (0x10 if row < 2 else 0x20 if row < 4 else 0x30)
        m[0x20F1] = 1

    def adjust_score(self) -> None:
        """$0988 packed BCD + DAA; upper carry is intentionally discarded."""
        m = self.rack.mem
        if not m[0x20F1]:
            return
        m[0x20F1] = 0
        base = 0x20F8 if (m[0x2067] & 1) else 0x20FC
        m[base], carry = add_bcd_byte(m[base], m[0x20F2])
        m[base+1], _ = add_bcd_byte(m[base+1], m[0x20F3], carry)
        if hasattr(self.rack, 'score_display'):
            self.rack.score_display.score_adjusted(base)
        self.record('SCORE_BCD', self.score)
        if self.rack.lives_enabled:
            self.rack.lives.award_extra_ship()

    def alien_explode_time(self) -> None:
        """$1538 AExplodeTime is serviced via $0100 DrawAlien on END ISR."""
        m = self.rack.mem
        m[0x2003] = (m[0x2003] - 1) & 255
        if m[0x2003]:
            return
        x, y = m[0x2064], m[0x2065]
        # $1424 EraseSimpleSprite clears *both* adjacent bytes, 16 rows.
        addr, _ = self.rack.pixel_to_address(x, y)
        for row in range(16):
            for col in (0, 1):
                dest = addr + row * 32 + col
                if 0x2400 <= dest < 0x4000:
                    m[dest] = 0
        m[0x2025] = 4
        m[0x2002] = 0
        self.record('EXPLOSION_DONE')
