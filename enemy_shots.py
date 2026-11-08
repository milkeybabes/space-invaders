"""Space Invaders (Midway 1978) source-level port of the *alien* missiles.

This is an unfinished system-level port, NOT an 8080 interpreter and not
proof of MAME frame equivalence. It retains the source byte locations,
three 16-byte object descriptors, $2073 shared scratch structure, 8080
8-bit wrapping, source animation frames, and software VRAM collision.

Assembly: $0476 GameObj2 rolling; $04B6 GameObj3 plunger; $050F/$0682
squiggly (saucer branch unported); $0550/055B/0563 common handling,
$061B/062F targeting, $0644 explosion, $08D8 speed, $170E reload rate.
https://computerarcheology.com/Arcade/SpaceInvaders/Code.html
"""
from __future__ import annotations

# Original ROM data at $1CD0-$1CF9 and $1D00-$1D14.
SHOT_IMAGES = bytes.fromhex('''
    44 AA 10 88 54 22 10 AA 44 22 54 88
    4A 15 BE 3F 5E 25
    04 FC 04 10 FC 10 20 FC 20 80 FC 80
    00 FE 00 24 FE 12 00 FE 00 48 FE 90
''')
COLUMN_TABLE = bytes.fromhex('01 07 01 01 01 04 0B 01 06 03 01 01 0B 09 02 08 02 0B 04 07 0A')
FIRING_MSBS = (0x02, 0x10, 0x20, 0x30)
FIRING_RELOADS = (0x30, 0x10, 0x0B, 0x08, 0x07)

# type -> (ROM handler, 16-byte object base, 11-byte status struct,
#           animation final pointer LSB, other shot step addresses)
CONFIG = {
    'rolling': (0x0476, 0x2030, 0x2035, 0xF9, (0x2046, 0x2056)),
    'plunger': (0x04B6, 0x2040, 0x2045, 0xED, (0x2036, 0x2056)),
    'squiggly': (0x0682, 0x2050, 0x2055, 0xDB, (0x2046, 0x2036)),
}


class EnemyShots:
    def __init__(self, rack):
        self.rack = rack
        self.events = []
        self.counts = {kind: 0 for kind in CONFIG}
        self.player_hit_frame = None

    def emit(self, name, kind, value=0):
        self.events.append((self.rack.frames + 1, name, kind, value))

    def set_reload_rate(self):
        """Original $170E table lookup from player's packed BCD score MSB."""
        m = self.rack.mem
        score_base = 0x20F8 if m[0x2067] & 1 else 0x20FC
        msb = m[score_base + 1]
        idx = next((i for i, threshold in enumerate(FIRING_MSBS) if msb <= threshold), 4)
        m[0x20CF] = FIRING_RELOADS[idx]

    def speed_shots(self):
        """$08D8: accelerate at 8 or fewer aliens; don't restore on >8."""
        if self.rack.mem[0x2082] < 9:
            self.rack.mem[0x207E] = 0xFB  # -5, otherwise -4 ($FC)

    def handler(self, kind: str, base: int) -> str:
        m = self.rack.mem
        _, expected, data_base, sprite_end, other = CONFIG[kind]
        if base != expected:
            raise ValueError('incorrect original object base')
        if kind == 'rolling':
            # $0477: task-extra timer restored from ROM $1B32 on each call.
            m[0x2032] = 2
            # Original $047D: first invocation skips shot by decrementing
            # a 16-bit zero pointer to $FFFF. This is not a Python timer.
            if m[0x2038] == 0 and m[0x2039] == 0:
                m[0x2038] = m[0x2039] = 0xFF
                return 'ROLLING_FIRST_SKIP'
        elif kind == 'plunger':
            if m[0x206E]:          # $04B7: last-alien suppression
                return 'PLUNGER_SKIPPED_ONE_ALIEN'
            if m[0x2080] != 1:    # $04BC: shared 3-way synchronization
                return 'PLUNGER_WAIT_SYNC'
        else:
            # $0682 GameObj4 shares its task with the UFO. We have only
            # translated the squiggly path ($050F); no fake saucer handler.
            if m[0x2080] != 2:
                return 'SQUIGGLY_WAIT_SYNC'
            if m[0x2083] and not m[0x2056]:
                return 'SAUCER_NOT_PORTED'

        # $0550 ToShotStruct, 11 bytes from original object+5.
        m[0x2073:0x207E] = m[data_base:data_base + 11]
        m[0x207F] = sprite_end
        m[0x2070], m[0x2071] = m[other[0]], m[other[1]]
        action = self._handle_shared(kind)

        # Carry out original table reset + inactive/active decision *before*
        # writing shared $2073 back. These are distinct from movement code.
        if kind == 'plunger' and m[0x2076] >= 0x10:
            m[0x2076] = 0x00
            m[0x2077] = 0x1D
        elif kind == 'squiggly' and m[0x2076] >= 0x15:
            m[0x2076] = 0x06
            m[0x2077] = 0x1D

        if m[0x2078]:  # shot active or explosion running
            m[data_base:data_base + 11] = m[0x2073:0x207E]
        else:
            # $04AB/$04F1/$053E: restore original 16-byte ROM mirror.
            from rom_objects import OBJECT_MIRROR
            src = base - 0x2010
            m[base:base + 16] = OBJECT_MIRROR[src:src + 16]
            if kind == 'plunger':
                if m[0x2082] == 1:
                    m[0x206E] = 1
                m[0x2048:0x204A] = m[0x2076:0x2078]
            elif kind == 'squiggly':
                m[0x2058:0x205A] = m[0x2076:0x2078]
            self.emit('SHOT_RESET', kind)
        return action

    def handle_splash_c(self):
        """$050E/$050F and $056F special splash shot toward the extra C.

        Shared movement/collision/explosion must remain the same as the
        alien squiggly missile; the splash task only bypasses initial column
        selection, using the ROM's preloaded coordinates.
        """
        m = self.rack.mem
        base = 0x2055
        m[0x2073:0x207E] = m[base:base+11]
        m[0x207F] = 0xDB
        if not (m[0x2073] & 0x80):
            # $056F/$05B7: task 4 activates the prepositioned shot.
            m[0x2073] |= 0x80
            m[0x2074] = (m[0x2074] + 1) & 255
            action = 'SPLASH_C_SHOT_ACTIVE'
        else:
            action = self._handle_shared('squiggly')
        m[base:base+11] = m[0x2073:0x207E]
        if m[0x2078] == 0 and (m[0x2073] & 1):
            # $053E: after last explosion tick, reset status/descriptor.
            m[0x2055] = 0
            action = 'SPLASH_C_EXPLOSION_COMPLETE'
        return action

    def _find_in_column(self, column):
        """$062F scans lowest surviving alien to highest, by +11 indices."""
        m = self.rack.mem
        if not 1 <= column <= 11:
            return None
        idx = column - 1
        for _ in range(5):
            if m[(m[0x2067] << 8) | idx]:
                return idx
            idx += 11
        return None

    def _shot_draw(self, operation):
        """$066C/$0675 via $1491; same original VRAM bit paths as player shot."""
        m = self.rack.mem
        image = m[0x2079] | (m[0x207A] << 8)
        collision = self.rack.combat._sprite_shift(m[0x207B], m[0x207C],
                                                    image, m[0x207D], operation)
        return collision

    def _handle_shared(self, kind):
        """$0563 and its source branches; shot status is in $2073."""
        m = self.rack.mem
        if m[0x2073] & 0x80:
            # $05C1: only move missile in the correct ISR half-screen.
            if (m[0x207C] & 0x80) != m[0x2072]:
                return 'ENEMY_WRONG_BEAM'
            if m[0x2073] & 1:
                return self._blowing_up(kind)
            m[0x2074] = (m[0x2074] + 1) & 0xFF
            self._shot_draw('erase')
            next_picture = (m[0x2079] + 3) & 0xFF
            if next_picture >= m[0x207F]:
                next_picture = (next_picture - 12) & 0xFF
            m[0x2079] = next_picture
            m[0x207B] = (m[0x207B] + m[0x207E]) & 0xFF
            collided = self._shot_draw('collision')
            x = m[0x207B]
            if x < 0x15 or collided:
                if collided and 0x1E <= x < 0x27:
                    m[0x2015] = 0
                    if self.player_hit_frame is None:
                        self.player_hit_frame = self.rack.frames + 1
                    self.emit('PLAYER_STRUCK', kind, x)
                m[0x2073] |= 1
                self.emit('SHOT_IMPACT', kind, x)
            else:
                self.emit('SHOT_MOVE', kind, x)
            return 'ENEMY_SHOT_MOVING'

        # Original $056C-$05B7: create a new shot, if firing is allowed.
        if m[0x20C1] == 4:  # splash mode not part of the demo
            return 'SPLASH_UNPORTED'
        if not m[0x2069]:
            return 'ALIEN_FIRE_DISABLED'
        m[0x2074] = 0
        reload_rate = m[0x20CF]
        for other in (m[0x2070], m[0x2071]):
            if other and reload_rate >= other:
                return 'ALIEN_RELOAD_WAIT'
        if m[0x2075] == 0:      # rolling targets player column
            # $061B/$156F: FindColumn uses 8-bit arithmetic + original
            # 16-pixel rack-column divisions; test the adjacent columns.
            player_pos = (m[0x201B] + 8) & 0xFF
            # $061B CALL FindColumn($156F), which in turn calls Cnt16s
            # and the original WrapRef ($1590). Use the existing exact
            # arithmetic port, including its counterintuitive wrap path.
            col_count, _coordinate = self.rack.combat._count16s(
                m[0x200A], player_pos
            )
            column = min(col_count, 11)
        else:
            ptr = m[0x2076] | (m[0x2077] << 8)
            column = m[ptr] if 0 <= ptr < len(m) else 0
            ptr = (ptr + 1) & 0xFFFF
            m[0x2076], m[0x2077] = ptr & 255, ptr >> 8
        index = self._find_in_column(column)
        if index is None:
            return 'NO_LIVE_ALIEN_IN_COLUMN'
        loc = self.rack.get_alien_coords(index)
        m[0x207B] = (loc.x - 10) & 0xFF
        m[0x207C] = (loc.y + 7) & 0xFF
        m[0x2073] |= 0x80
        m[0x2074] = (m[0x2074] + 1) & 0xFF
        self.counts[kind] += 1
        self.emit('ENEMY_SHOT_STARTED', kind, index)
        return 'ENEMY_SHOT_STARTED'

    def _blowing_up(self, kind):
        """$0644-$0669: original 4-tick blowup -> graphic -> erase."""
        m = self.rack.mem
        m[0x2078] = (m[0x2078] - 1) & 0xFF
        if m[0x2078] == 3:
            self._shot_draw('erase')
            m[0x2079], m[0x207A] = 0xDC, 0x1C
            m[0x207C] = (m[0x207C] - 2) & 0xFF
            m[0x207B] = (m[0x207B] - 2) & 0xFF
            m[0x207D] = 6
            self._shot_draw('collision')
            self.emit('ENEMY_SHOT_SPLAT', kind)
        elif m[0x2078] == 0:
            self._shot_draw('erase')
            self.emit('ENEMY_SHOT_SPLAT_END', kind)
        return 'ENEMY_SHOT_EXPLODING'
