"""1978 Space Invaders: original player-death frames and reserve ships.

Source: https://computerarcheology.com/Arcade/SpaceInvaders/Code.html

Translated paths:
  $028E-$02CF  GameObj0 player hit and explosion sequencer
  $039B-$03AD  DrawPlayerDie (alternating original ROM images)
  $092E-$0934  Active player's ships-remaining byte
  $19E6-$1A05  DrawNumShips (icons, ROM bitmap, blank unused slots)
  $1A7F-$1A8A  RemoveShip (reserve decrement and repaint)
  $032C-$032F  one-player re-entry via RemoveShip, then $0817

This is a partial system port. The original single-digit lives numeral
is included; wider score typography, extra life at $0935, player-two/cocktail
branch $02ED, and the $0B89 attract screens are NOT ported. In this opt-in test mode,
we record a game-over state rather than inventing those missing operations.
The scheduler is still a provisional one-main-loop-pass-per-frame model.
"""
from __future__ import annotations

from rom_objects import OBJECT_MIRROR, PLAYER_SPRITE

# ROM sprites from $1C70 and $1C80, each 16 column bytes.
EXPLOSION_SPRITES = bytes.fromhex('''
00 04 01 13 03 07 B3 0F 2F 03 2F 49 04 03 00 01
40 08 05 A3 0A 03 5B 0F 27 27 0B 4B 40 84 11 48
''')
assert len(EXPLOSION_SPRITES) == 0x20

# $1ED0-$1F07, original character indices $1A..$20 (digits 0-6).
# They are 8-column 1-byte sprites, not a new Python/system font.
NUMBER_GLYPHS = bytes.fromhex('''
00 3E 45 49 51 3E 00 00
00 00 21 7F 01 00 00 00
00 23 45 49 49 31 00 00
00 42 41 49 59 66 00 00
00 0C 14 24 7F 04 00 00
00 72 51 51 51 4E 00 00
00 1E 29 49 49 46 00 00
''')
assert len(NUMBER_GLYPHS) == 56

# Ship reservation icons: source $19E6 initial HL=$2701; $1439 advances
# HL by 16 * 0x20 = 0x200 after each 16-column icon. $19FF stops when
# the high byte becomes $35, i.e. clears through $3301 inclusive.
HOLD_START = 0x2701
HOLD_PITCH = 0x200
HOLD_SLOTS = 7
SHIP_COUNT_PLAYER_1 = 0x21FF
SHIP_COUNT_PLAYER_2 = 0x22FF


class PlayerLives:
    def __init__(self, rack, *, starting_lives: int = 3, bonus_life: int = 1500):
        if not 3 <= starting_lives <= 6:
            raise ValueError('original DIP switch supplies 3..6 ships')
        if bonus_life not in (1000, 1500):
            raise ValueError('original bonus DIP offers 1000 or 1500')
        self.bonus_life = bonus_life
        self.rack = rack
        self.events: list[tuple[int, str, int]] = []
        self.game_over = False
        from game_over import GameOver
        self.game_over_sequence = GameOver(rack)
        self.deaths = 0
        self.respawns = 0
        self.initial_lives = starting_lives
        self.life_decrement = 1  # Stage 13 --debug sets 0; never bypass collision
        m = rack.mem
        m[0x1C70:0x1C90] = EXPLOSION_SPRITES
        m[0x1ED0:0x1F08] = NUMBER_GLYPHS
        m[SHIP_COUNT_PLAYER_1] = starting_lives  # $07D4
        # Only player 1 is active in this diagnostic.
        m[0x20E7] = 1             # $07C2 initial player-one-alive flag
        m[0x20E5] = 1             # original extra-ship eligibility
        self.remove_ship()         # $07F6 initial reserve decrement
        self.emit('INITIAL_SHIP_PLACED', self.stash)

    def emit(self, event: str, value: int = 0) -> None:
        self.events.append((self.rack.frames + 1, event, value))

    @property
    def stash_address(self) -> int:
        return SHIP_COUNT_PLAYER_1 if self.rack.mem[0x2067] & 1 else SHIP_COUNT_PLAYER_2

    @property
    def stash(self) -> int:
        """Number of *reserve* ships, not total ships including the active one."""
        return self.rack.mem[self.stash_address]

    def draw_reserve_ships(self) -> None:
        """$19E6-$1A05: the original simple sprite, not an icon substitute.

        The original $1A8B numerical lives glyph is drawn separately by
        draw_lives_number() using the ROM character set.
        """
        m = self.rack.mem
        for slot in range(HOLD_SLOTS):
            start = HOLD_START + slot * HOLD_PITCH
            for col in range(16):
                m[start + col * 0x20] = (PLAYER_SPRITE[col] if slot < self.stash else 0)

    def draw_lives_number(self, value: int) -> None:
        """$1A8B->$09C5->$08FF: original 8-column numeral at VRAM $2501."""
        if not 0 <= value <= 6:
            raise ValueError('DIP ships can be at most six')
        m = self.rack.mem
        src = 0x1ED0 + value * 8
        for i in range(8):
            m[0x2501 + i * 0x20] = m[src + i]

    def remove_ship(self) -> bool:
        """$1A7F: decrement reserve on starting/respawning, never below zero."""
        if self.stash == 0:
            return False
        before = self.stash
        self.rack.mem[self.stash_address] = before - 1
        self.draw_reserve_ships()
        self.draw_lives_number(before)  # $1A8A uses pre-decrement A
        self.emit('REMOVE_SHIP_FROM_STASH', self.stash)
        return True

    def award_extra_ship(self) -> bool:
        """ROM $0935-$0979: award a single bonus ship using BCD MSB.

        The original checks the upper BCD score byte against $10/$15,
        increases the active player's stash and clears the one-time flag.
        The separate original bonus sound sequence is not yet implemented.
        """
        m = self.rack.mem
        bonus_flag = 0x20E5 if m[0x2067] == 0x21 else 0x20E6
        if not m[bonus_flag] or self.game_over:
            return False
        score_base = 0x20F8 if (m[0x2067] & 1) else 0x20FC
        threshold = 0x10 if self.bonus_life == 1000 else 0x15
        if m[score_base + 1] < threshold:
            return False
        m[self.stash_address] = (m[self.stash_address] + 1) & 255
        m[bonus_flag] = 0
        m[0x2099] = 0xFF  # $0972 sound hold timer; audio pending
        self.draw_reserve_ships()
        self.draw_lives_number(min(6, self.stash + 1))
        self.emit('EXTRA_SHIP_AWARDED', self.stash)
        return True

    def _draw_player_explosion(self, former_state: int) -> None:
        """$039B-$03AD; alternate 0/1 exactly via (state+1)&1."""
        m = self.rack.mem
        new_state = (former_state + 1) & 1
        m[0x2015] = new_state
        source = 0x1C70 + 16 * new_state
        m[0x2018] = source & 255
        m[0x2019] = source >> 8
        self.rack.draw_simple_sprite(m[0x201A], m[0x201B], source, m[0x201C])
        self.emit('DEATH_SPRITE', new_state)

    def _erase_player(self) -> None:
        """$02AE->$1424 EraseSimpleSprite: 16 columns, one VRAM byte each."""
        m = self.rack.mem
        start, _ = self.rack.pixel_to_address(m[0x201A], m[0x201B])
        for col in range(16):
            m[start + 0x20 * col] = 0

    def player_death_tick(self, base: int) -> str:
        """$0296-$02CF GameObj0 death branch, invoked via original dispatcher.

        Original $2016 counts down from 5; $2017 counts image changes
        (0x0C). The first visual change occurs after five calls, the later
        images after another five calls each. It does not stop the fleet or
        missiles with a fabricated global pause.
        """
        if base != 0x2010:
            raise ValueError('player death handler must use game object 0')
        m = self.rack.mem
        current = m[0x2015]
        if current == 0xFF:
            raise ValueError('death routine entered while player alive')
        m[0x2016] = (m[0x2016] - 1) & 0xFF
        if m[0x2016] != 0:
            return 'PLAYER_DIE_WAIT'
        # $0299..$02A7: stop firing; maintain 48-tick alien fire grace.
        m[0x2068] = 0
        m[0x2069] = 0
        m[0x206A] = 0x30
        m[0x2016] = 5
        m[0x2017] = (m[0x2017] - 1) & 0xFF
        if m[0x2017] != 0:
            self._draw_player_explosion(current)
            return 'PLAYER_DIE_SPRITE'
        # $02AE..$02C0: erase last image, restore entire player descriptor.
        self._erase_player()
        m[0x2010:0x2020] = OBJECT_MIRROR[0:16]
        self.deaths += 1
        self.emit('PLAYER_EXPLOSION_FINISHED', self.stash)
        # Source $02D7 checks whether the stash has any ships *before*
        # removing a replacement. $02DB->$166D if no ships remain.
        if self.stash == 0 and self.life_decrement:
            self.game_over = True
            m[0x20E7 if m[0x2067] == 0x21 else 0x20E8] = 0
            # Original $166D draws zero; Stage 8 continues the game-over path.
            self.draw_lives_number(0)
            self.game_over_sequence.begin()
            self.emit('GAME_OVER_SEQUENCE', self.deaths)
            return 'GAME_OVER_SEQUENCE'
        # $02DE-$0335: in a two-player game, the surviving player
        # takes the next turn; defer actual RAM swap until ISR unwinds.
        if getattr(self.rack, 'two_player_controller', None) is not None:
            other_alive = m[0x20E8 if m[0x2067] == 0x21 else 0x20E7]
            if other_alive:
                self.rack.two_player_controller.pending_switch = True
                self.emit('PLAYER_CHANGE_PENDING', self.stash)
                return 'PLAYER_CHANGE_PENDING'
        # Source $032C RemoveShip; $032F -> $0817. No reset of rack/shields.
        if self.life_decrement:
            self.remove_ship()
        self.respawns += 1
        self.emit('PLAYER_RESPAWN_PENDING', self.stash)
        return 'PLAYER_RESPAWN_PENDING'
