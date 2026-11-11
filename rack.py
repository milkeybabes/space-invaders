"""First stage: source-level translation of the ORIGINAL 1978 alien rack.

Only aliens and directly supporting routines are ported so far. This is not
an 8080 emulator and it is NOT YET the complete arcade game.

Function names and 8080 ROM addresses are traced to:
https://computerarcheology.com/Arcade/SpaceInvaders/Code.html

RAM addresses and one-bit video RAM retain the original 8080 address layout.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from alien_data import ALIEN_IMAGES

ROM_ALIEN_IMAGES = 0x1C00
VRAM_START = 0x2400
VRAM_END = 0x4000
SCREEN_WIDTH = 224
SCREEN_HEIGHT = 256
BYTES_PER_RASTER = 32


@dataclass(frozen=True)
class AlienLocation:
    index: int
    row: int
    column: int
    x: int  # 8080 L: horizontal coordinate in UNROTATED hardware pixel space
    y: int  # 8080 C: screen scan position (cabinet horizontal after rotation)


class Rack:
    def __init__(self, surviving: int = 55):
        if not 1 <= surviving <= 55:
            raise ValueError('surviving must be between 1 and 55 (test fixture only)')
        self.mem = bytearray(0x4000)
        self.mem[ROM_ALIEN_IMAGES: ROM_ALIEN_IMAGES + len(ALIEN_IMAGES)] = ALIEN_IMAGES
        # First 16 bytes copied from the original ROM's init mirror at 1B00.
        # 2000 wait flag=1, 2007 dVertical=0, 2008 dHorizontal=+2,
        # 2009/200A reference coords=$78,$38, 200E drop delta=$F8 (-8).
        self.mem[0x2000:0x2010] = bytes.fromhex(
            '01 00 00 10 00 00 00 00 02 78 38 78 38 00 F8 00'
        )
        # Current player's data bank, alive status, count at named RAM spots.
        self.mem[0x2067] = 0x21
        self.mem[0x2068] = 0x01
        self.mem[0x2082] = surviving
        # ROM $01C0 InitAliens: flags 0..54 inclusive, 1=alive.
        for idx in range(surviving):
            self.mem[0x2100 + idx] = 1
        self.frames = 0
        self.rack_steps = 0
        self.last_drawn: int | None = None
        self.is_over = False
        # The legacy rack-only fixture intentionally does NOT load game
        # objects, so every Stage-2 regression frame remains unchanged.
        self.objects_enabled = False
        self.combat_enabled = False
        self.combat = None
        self.enemy_shots_enabled = False
        self.enemy_shots = None
        self.enemy_demo_halted = False
        self.shields_enabled = False
        self.shields = None
        self.lives_enabled = False
        self.lives = None
        self.saucer_enabled = False
        self.waves_enabled = False
        self.waves = None
        self.saucer = None
        self.port1 = 0  # keyboard diagnostic mapped to original IN(1) bits
        self.port2 = 0
        from game_objects import GameObjectDispatcher
        self.objects = GameObjectDispatcher(self)
        # $19D1 EnableGameTasks and $07?? game startup would normally set
        # these. Set them explicitly for this *rack-only gameplay fixture*.
        self.mem[0x20E9] = 1  # suspendPlay = game tasks enabled
        self.mem[0x20EF] = 1  # gameMode = active game
        from interrupts import InterruptScheduler
        self.scheduler = InterruptScheduler(self)

    @property
    def alive(self) -> int:
        return sum(bool(v) for v in self.mem[(self.mem[0x2067] << 8):((self.mem[0x2067] << 8) + 55)])

    @property
    def frame_number(self) -> int:
        return self.mem[0x2005]

    @property
    def reference(self) -> tuple[int, int]:
        return self.mem[0x2009], self.mem[0x200A]

    @property
    def current(self) -> int:
        return self.mem[0x2006]

    # Original $017A GetAlienCoords; source uses repeated subtraction of 11,
    # then repeated addition of 16. Valid index range is $00..$36.
    def get_alien_coords(self, index: int) -> AlienLocation:
        if not 0 <= index < 55:
            raise ValueError(index)
        row, column = divmod(index, 11)
        x = (self.mem[0x2009] + row * 16) & 0xFF
        y = (self.mem[0x200A] + column * 16) & 0xFF
        return AlienLocation(index, row, column, x, y)

    # Original $01A1 MoveRefAlien + $01D9 AddDelta.
    # Important: RAM $2007 is vertical/drop delta (added to 2009),
    # while $2008 is horizontal delta (added to 200A). Naming is deceptive!
    def move_ref_alien(self) -> None:
        self.mem[0x2006] = 0
        drop_delta = self.mem[0x2007]
        self.mem[0x2007] = 0
        self.mem[0x2009] = (self.mem[0x2009] + drop_delta) & 0xFF
        self.mem[0x200A] = (self.mem[0x200A] + self.mem[0x2008]) & 0xFF
        self.mem[0x2005] = (self.mem[0x2005] + 1) & 1
        self.rack_steps += 1

    # Original $0141 CursorNextAlien. Mid-screen ISR calls this once.
    # If there is no pending draw, locate next live alien; when index 55
    # is crossed, move reference and restart from index 0. 'waitOnDraw'
    # prevents the mid-screen interrupt from skipping undrawn aliens.
    def cursor_next_alien(self) -> None:
        if self.is_over or not self.mem[0x2068] or self.mem[0x2000]:
            return
        if not self.alive:
            self.is_over = True  # Stage 1: no level transition yet.
            return
        index = self.mem[0x2006]
        for _ in range(56):
            index += 1
            if index == 55:
                self.move_ref_alien()
                index = 0
            if self.mem[(self.mem[0x2067] << 8) + index] == 1:
                loc = self.get_alien_coords(index)
                self.mem[0x2006] = index
                self.mem[0x200B] = loc.x
                self.mem[0x200C] = loc.y
                # Original $016A comparison with $28. This isn't the
                # cabinet horizontal playfield edge test.
                if loc.x < 0x28:
                    # ROM $016A-$016D -> $1971 -> $16E6: invasion is a
                    # forced round end, NOT an ordinary life loss/respawn.
                    self.is_over = True
                    self.mem[0x206D] = 1  # original 'invaded' RAM byte
                    if self.lives_enabled and not self.lives.game_over:
                        # $16EA sets playerAlive=0; reuse the translated
                        # $0296-$02CF explosion before $166D game-over.
                        self.mem[0x2015] = 0
                        self.mem[0x2016] = 5
                        self.mem[0x2017] = 0x0C
                        self.mem[0x2010:0x2013] = b'\x00\x00\x00'
                        self.lives.emit('ALIENS_INVADED', loc.x)
                    return
                self.mem[0x2004] = loc.row
                self.mem[0x2000] = 1
                return
        raise AssertionError('Unreachable: alien flags/count inconsistent')

    # Original $1474 CnvtPixNumber + $1A47 ConvToScr.
    # Source HL is 0xYYXX. Pixel address 2000 | ((YYXX >> 3) & $1fff).
    @staticmethod
    def pixel_to_address(x: int, y: int) -> tuple[int, int]:
        location = (y << 8) | x
        return (0x2000 | (location >> 3)), (x & 7)

    # Original $15D3 DrawSprite. Two adjacent screen bytes are explicitly
    # OVERWRITTEN, not blended, for each of 16 columns. Calculating the
    # hardware shift-register output arithmetically is not CPU emulation.
    def draw_shifted_sprite(self, x: int, y: int, sprite_offset: int) -> None:
        address, shift = self.pixel_to_address(x, y)
        for n in range(16):
            source = self.mem[ROM_ALIEN_IMAGES + sprite_offset + n]
            first = (source << shift) & 0xFF
            second = (source >> (8 - shift)) & 0xFF if shift else 0
            target = address + n * BYTES_PER_RASTER
            if VRAM_START <= target < VRAM_END:
                self.mem[target] = first
            if VRAM_START <= target + 1 < VRAM_END:
                self.mem[target + 1] = second

    # Original $0100 DrawAlien / $013B: select one of six ROM graphics,
    # drawing one alien per *end-screen interrupt* and clearing $2000.
    def draw_alien(self) -> None:
        # Finish an explosion even when the last alien has been destroyed;
        # round transition remains unported, but the original $1538 timer must
        # not freeze when there are zero survivors.
        if self.mem[0x2002]:
            if self.combat_enabled:
                self.combat.alien_explode_time()
            return
        if self.is_over:
            return
        idx = self.mem[0x2006]
        if self.mem[(self.mem[0x2067] << 8) | idx]:
            row = self.mem[0x2004]
            sprite_offset = ((row & 0xFE) << 3) + (0x30 if self.mem[0x2005] else 0)
            self.draw_shifted_sprite(self.mem[0x200B], self.mem[0x200C], sprite_offset)
            self.last_drawn = idx
        self.mem[0x2000] = 0

    # $1597 RackBump / $15C5: inspect 23 *actual VRAM bytes* along the
    # two playfield margins and change signed deltas. Other game-loop
    # routines are missing, so this hook's frequency is provisional.
    def rack_bump(self) -> None:
        direction_left = bool(self.mem[0x200D])
        test_address = 0x2524 if direction_left else 0x3EA4
        if any(self.mem[test_address + n] for n in range(0x17)):
            if direction_left:
                new_delta = 3 if self.mem[0x2082] == 1 else 2  # $18F1
                self.mem[0x200D] = 0
            else:
                new_delta = 0xFE  # -2, 8-bit signed
                self.mem[0x200D] = 1
            self.mem[0x2008] = new_delta
            self.mem[0x2007] = self.mem[0x200E]  # -8 drop next step

    # Original $01E4 CopyRAMMirror subset, in Stage-3 opt-in diagnostics.
    def enable_game_objects(self, immediate_player: bool = True) -> None:
        from rom_objects import OBJECT_MIRROR, PLAYER_SPRITE
        self.mem[0x2010:0x2070] = OBJECT_MIRROR
        self.mem[0x1C60:0x1C70] = PLAYER_SPRITE
        self.objects_enabled = True
        if immediate_player:
            # Diagnostic shortcut ONLY: the ROM mirror sets the player
            # descriptor's two-byte timer to $0080 (128 calls before active).
            # Skip that startup wait for movement tests, without changing
            # the timer's implementation. For authentic timer testing use
            # immediate_player=False.
            self.mem[0x2010] = 0
            self.mem[0x2011] = 0

    def enable_combat_demo(self) -> None:
        """Enable Stage-4 shot routines only in the explicit combat diagnostic.

        Do not affect Stage 1/2/3 regression modes. These ROM image bytes
        are from the annotated original disassembly, not new art.
        """
        from combat import Combat, PLAYER_SHOT_AND_BLOWUP, ALIEN_EXPLOSION
        self.enable_game_objects(immediate_player=True)
        self.mem[0x1C90:0x1C99] = PLAYER_SHOT_AND_BLOWUP
        self.mem[0x1CC0:0x1CD0] = ALIEN_EXPLOSION
        self.mem[0x208D] = 0x54  # first score-pointer byte of original table
        self.mem[0x208E] = 0x1D
        self.combat_enabled = True
        self.combat = Combat(self)
        from score_display import ScoreDisplay
        self.score_display = ScoreDisplay(self)
        self.score_display.initialise()
        self.objects.handlers[0x03BB] = self.objects.player_shot

    def enable_enemy_shots_demo(self) -> None:
        """Opt-in enemy projectiles; no shields or player death sequence yet.

        This deliberately skips the original player-start wait and alien-fire
        grace period, just as earlier interactive player diagnostics did. The
        *shot algorithm* uses ROM RAM structures and source code paths.
        """
        from enemy_shots import EnemyShots, SHOT_IMAGES, COLUMN_TABLE
        self.enable_combat_demo()
        self.mem[0x1CD0:0x1CFA] = SHOT_IMAGES
        self.mem[0x1D00:0x1D15] = COLUMN_TABLE
        self.mem[0x207E] = 0xFC
        self.mem[0x20CF] = 0x30
        self.mem[0x2069] = 1  # test harness: bypass incomplete startup delay
        self.enemy_shots_enabled = True
        self.enemy_shots = EnemyShots(self)
        for kind, (handler, *_rest) in __import__('enemy_shots').CONFIG.items():
            self.objects.handlers[handler] = (
                lambda base, kind=kind: self.enemy_shots.handler(kind, base)
            )

    def enable_shields_demo(self) -> None:
        """Stage 6: opt-in original shield+baseline bytes atop Stage-5 combat.

        Keep the earlier rack/player/combat/enemy-shot test fixtures untouched.
        """
        from shields import Shields, SHIELD_IMAGE
        self.enable_enemy_shots_demo()
        self.mem[0x1D20:0x1D4C] = SHIELD_IMAGE
        self.shields = Shields(self)
        self.shields.init_playfield(player=1)
        self.shields_enabled = True

    def enable_lives_demo(self, *, starting_lives: int = 3, bonus_life: int = 1500) -> None:
        """Stage 7: opt-in original player explosion and reserve-ship system.

        Previous Stages 1-6 retain their previous (halt-on-hit) behaviour.
        """
        from lives import PlayerLives
        self.enable_shields_demo()
        self.lives_enabled = True
        self.lives = PlayerLives(self, starting_lives=starting_lives, bonus_life=bonus_life)

    def enable_saucer_demo(self, *, starting_lives: int = 3, bonus_life: int = 1500) -> None:
        """Stage 10: enable saucer using the original shared squiggly-shot task."""
        self.enable_lives_demo(starting_lives=starting_lives, bonus_life=bonus_life)
        from saucer import Saucer
        self.saucer = Saucer(self)
        self.saucer_enabled = True
        self.objects.handlers[0x0682] = self.saucer.handler
        # Retain the actual $2069/$206A countdown rather than the stage 5 shortcut.
        self.mem[0x2069] = 0
        self.mem[0x206A] = 0x30

    def enable_waves_demo(self, *, starting_lives: int = 3, bonus_life: int = 1500) -> None:
        """Stage 11: single-player full-rack transitions, on Stage 10 gameplay."""
        self.enable_saucer_demo(starting_lives=starting_lives, bonus_life=bonus_life)
        from waves import WaveTransitions
        self.waves = WaveTransitions(self)
        self.waves_enabled = True

    # Original $17C0 ReadInputs chooses IN(1) for player 1 and IN(2) for 2.
    def read_inputs(self) -> int:
        return self.port1 if (self.mem[0x2067] & 1) else self.port2

    def set_controls(self, *, left: bool = False, right: bool = False,
                     fire: bool = False) -> None:
        # Original INP1: bit 5 left, bit 6 right, bit 4 fire.
        # The fire bit is retained for later player-shot translation.
        value = (0x20 if left else 0) | (0x40 if right else 0) | (0x10 if fire else 0)
        if self.mem[0x2067] & 1:
            self.port1 = value
        else:
            self.port2 = value

    # Original $1439 DrawSimpSprite via $1A3B ReadDesc and $1A47 ConvToScr.
    # Unlike shifted alien graphics, this is a 1-byte simple sprite.
    def draw_simple_sprite(self, pixel_low: int, pixel_high: int,
                           source_address: int, size: int) -> None:
        if not 0 <= size <= 256:
            raise ValueError(size)
        start, _ = self.pixel_to_address(pixel_low, pixel_high)
        for n in range(size):
            destination = start + 32 * n
            if VRAM_START <= destination < VRAM_END:
                self.mem[destination] = self.mem[(source_address + n) & 0x3FFF]

    def step_frame(self) -> None:
        """Run the source-order partial ISR schedule (see interrupts.py).

        NOT cycle-exact: non-rack subroutines and continuous main-loop timing
        are pending. Its single main-loop edge pass preserves Stage 1 output.
        """
        self.scheduler.step_frame()

    def video_ram(self) -> memoryview:
        return memoryview(self.mem)[VRAM_START:VRAM_END]

    def framebuffer_digest(self) -> str:
        return sha256(self.video_ram()).hexdigest()

    def portrait_luma(self) -> bytes:
        """Return 224x256 grayscale pixels, arcade orientation, no scaling.

        Native RAM is a 256x224 1-bit monochrome display rotated 90 degrees.
        The first framebuffer byte is the bottom-left of the portrait screen.
        """
        # The zero-credit attract demo captures a display-frame snapshot
        # separately from the 8080-derived live RAM. The original beam can
        # display the previous video frame even after the CPU wrote VRAM.
        # This ONLY changes presented pixels, never RAM/collision timing.
        presented = getattr(self, '_presentation_luma_override', None)
        if presented is not None:
            return presented
        pixels = bytearray(SCREEN_WIDTH * SCREEN_HEIGHT)
        for portrait_x in range(SCREEN_WIDTH):
            offset = VRAM_START + portrait_x * BYTES_PER_RASTER
            for byte_x in range(BYTES_PER_RASTER):
                v = self.mem[offset + byte_x]
                if not v:
                    continue
                for bit in range(8):
                    if v & (1 << bit):
                        portrait_y = 255 - (byte_x * 8 + bit)
                        pixels[portrait_y * SCREEN_WIDTH + portrait_x] = 255
        return bytes(pixels)
