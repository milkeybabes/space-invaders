"""Stage 8: $166D-$16E3 single-player game-over translation.

ROM glyphs $1E00-$1ECF and message $1AA6, original $08FF/$0A93
character drawing and $09D6 clear.  The diagnostic runs at one ISR pair
per frame; $0A93 waits 7 end-screen interrupts per printed letter.
$0B89 splash/credits and multiplayer branch $169F remain unported.
"""
from __future__ import annotations

ROM_FONT = bytes.fromhex("""
00 1F 24 44 24 1F 00 00
00 7F 49 49 49 36 00 00
00 3E 41 41 41 22 00 00
00 7F 41 41 41 3E 00 00
00 7F 49 49 49 41 00 00
00 7F 48 48 48 40 00 00
00 3E 41 41 45 47 00 00
00 7F 08 08 08 7F 00 00
00 00 41 7F 41 00 00 00
00 02 01 01 01 7E 00 00
00 7F 08 14 22 41 00 00
00 7F 01 01 01 01 00 00
00 7F 20 18 20 7F 00 00
00 7F 10 08 04 7F 00 00
00 3E 41 41 41 3E 00 00
00 7F 48 48 48 30 00 00
00 3E 41 45 42 3D 00 00
00 7F 48 4C 4A 31 00 00
00 32 49 49 49 26 00 00
00 40 40 7F 40 40 00 00
00 7E 01 01 01 7E 00 00
00 7C 02 01 02 7C 00 00
00 7F 02 0C 02 7F 00 00
00 63 14 08 14 63 00 00
00 60 10 0F 10 60 00 00
00 43 45 49 51 61 00 00
""")
assert len(ROM_FONT) == 26 * 8
# $1AA6: first ten byte codes of the actual ROM message including a trailing space.
GAME_OVER_MESSAGE = bytes.fromhex('06 00 0C 04 26 0E 15 04 11 26')
# Source $1AA6-$1AB9, 20-character two-player ending message.
MULTI_GAME_OVER_MESSAGE = bytes.fromhex('06 00 0C 04 26 0E 15 04 11 26 26 0F 0B 00 18 04 11 24 26 25')
SPACE_CODE = 0x26

class GameOver:
    def __init__(self, rack):
        self.rack = rack
        self.phase = 'inactive'
        self.index = 0
        self.delay = 0
        self.events = []
        rack.mem[0x1E00:0x1ED0] = ROM_FONT
        rack.mem[0x1AA6:0x1AB0] = GAME_OVER_MESSAGE
        # $1F30: space glyph, original all zero.
        rack.mem[0x1F30:0x1F38] = bytes(8)

    def emit(self, name):
        self.events.append((self.rack.frames + 1, name))

    def begin(self):
        m = self.rack.mem
        if self.phase != 'inactive':
            return
        m[0x20E7 if m[0x2067] == 0x21 else 0x20E8] = 0  # $1671 active player alive flag
        player_base = 0x20F8 if m[0x2067] & 1 else 0x20FC
        # $1676-$1695: compare high BCD byte, then low BCD byte;
        # equality does not overwrite high score.
        high = (m[0x20F5], m[0x20F4])
        score = (m[player_base + 1], m[player_base])
        if score > high:
            m[0x20F4] = m[player_base]
            m[0x20F5] = m[player_base + 1]
            if hasattr(self.rack, 'score_display'):
                self.rack.score_display.high_score_updated()
            self.emit('HIGH_SCORE_UPDATED')
            # $1950 redraw of high-score digits awaits HUD text port.
        self.phase = 'multi_message' if m[0x20CE] else 'message'
        self.index = 0
        self.delay = 0
        self.emit('GAME_OVER_BEGIN')

    def draw_character(self, code, address):
        """$08FF/$1439: overwrite 8 VRAM bytes at column stride $20."""
        m = self.rack.mem
        src = 0x1E00 + code * 8
        for i in range(8):
            dest = address + 32*i
            if 0x2400 <= dest < 0x4000:
                m[dest] = m[src+i]

    def clear_playfield(self):
        """$09D6: clear bytes with low five bits $02..$1B, per row."""
        m = self.rack.mem
        for address in range(0x2402, 0x4000):
            if 2 <= (address & 0x1F) < 0x1C:
                m[address] = 0

    def step_frame(self):
        if self.phase in ('inactive', 'attract_pending', 'switch_ready'):
            return
        if self.phase == 'multi_message':
            if self.delay:
                self.delay -= 1
                return
            code = MULTI_GAME_OVER_MESSAGE[self.index]
            if self.index == 18:
                code = 0x1B if self.rack.mem[0x2067] == 0x21 else 0x1C
            self.draw_character(code, 0x2803 + self.index * 0x100)
            self.index += 1
            self.delay = 6
            if self.index == len(MULTI_GAME_OVER_MESSAGE):
                self.phase = 'multi_letter_wait'
            return
        if self.phase == 'multi_letter_wait':
            if self.delay:
                self.delay -= 1
                return
            self.phase = 'multi_hold'
            self.delay = 64  # $16BB OneSecDelay
            return
        if self.phase == 'multi_hold':
            self.delay -= 1
            if self.delay == 0:
                m = self.rack.mem
                other_alive = bool(m[0x20E8 if m[0x2067] == 0x21 else 0x20E7])
                if other_alive:
                    self.phase = 'switch_ready'
                else:
                    self.phase = 'message'
                    self.delay = 0
                    self.index = 0
            return
        if self.phase == 'message':
            if self.delay:
                self.delay -= 1
                return
            code = GAME_OVER_MESSAGE[self.index]
            # Source $16C9 HL=$2D18; DrawSimpSprite advances H by 1
            # columns for each character, wrapping 16-bit HL as usual.
            address = (0x2D18 + self.index * 0x100) & 0xFFFF
            self.draw_character(code, address)
            self.index += 1
            self.delay = 6  # printed character + next 6 frames = 7 ISR counts
            if self.index == len(GAME_OVER_MESSAGE):
                self.phase = 'letter_wait'
            return
        if self.phase == 'letter_wait':
            if self.delay:
                self.delay -= 1
                return
            self.phase = 'hold'
            self.delay = 128  # $0AB6 2-second delay is 128 interrupts
            self.emit('GAME_OVER_MESSAGE_COMPLETE')
            return
        if self.phase == 'hold':
            self.delay -= 1
            if self.delay:
                return
            self.clear_playfield()
            m = self.rack.mem
            m[0x20EF] = 0  # $16DA demo mode
            m[0x2098] = 0  # software sound port hold, output $05 not emulated
            m[0x20E9] = 1  # $19D1 enable game tasks
            self.phase = 'attract_pending'
            self.emit('ATTRACT_ENTRY_UNPORTED')
