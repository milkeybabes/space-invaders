"""Stage 13 incremental coin/start integration.

The ROM's full $0B89 splash/attract and alternating two-player round
machinery are NOT translated here. This explicitly bounded integration
keeps previous gameplay logic as an unchanged Rack instance per game.
"""
from rack import Rack
from score_display import ScoreDisplay

# Original letter and space glyph indices ($1E00 alphabet, $1F30 blank).
def glyph(ch):
    if ch == ' ': return 0x26
    if ch == '-': return 0x3F
    if 'A' <= ch <= 'Z': return ord(ch)-ord('A')
    if '0' <= ch <= '9': return 0x1A+int(ch)
    raise ValueError(ch)

class ArcadeFrontEnd:
    def __init__(self, starting_lives=3, bonus_life=1500, debug=False, attract_preview=False, experimental_ordered_shot=False, experimental_continuation=False, experimental_second_demo_phase=False, experimental_rom_ram_lifecycle=False, experimental_isr_player_order=False, experimental_death_handoff=False):
        self.starting_lives = starting_lives
        self.bonus_life = bonus_life
        self.debug = debug
        self.attract_preview = attract_preview
        # Debug display choice only; no effect on original execution/RAM.
        self.experimental_ordered_shot = experimental_ordered_shot
        self.experimental_continuation = experimental_continuation
        self.experimental_second_demo_phase = experimental_second_demo_phase
        self.experimental_rom_ram_lifecycle = experimental_rom_ram_lifecycle
        self.experimental_isr_player_order = experimental_isr_player_order
        self.experimental_death_handoff = experimental_death_handoff
        self.demo_video_phase = 'pre'
        self.attract_intro = None
        self.credits = 0
        self.mode = 'credits'
        self.events = []
        self.high_score = (0,0)
        self.rack = None
        self.prompt_ticks = 0
        self.two_player = None
        self._enter_credits()

    def _write(self, message, address):
        sd = self.rack.score_display
        for letter in message:
            address = sd.draw_char(glyph(letter), address)

    def _draw_credit_screen(self):
        """$0765-$078E WaitForStart's *waiting* screen, bounded port.

        $0771 clears the central playfield; the persistent score header and
        score digits are not removed. At $077F-$078B, exactly one credit
        selects ONLY 1PLAYER BUTTON; 2+ selects 1 OR 2PLAYERS BUTTON.
        Zero credits uses the existing interim insert-coin presentation until
        the $0AEA / $0B89 attract scheduler is translated.
        """
        m = self.rack.mem
        m[0x2400:0x4000] = bytes(0x1C00)
        # Reinitialize after each clear; the score-display descriptor remains.
        self.rack.score_display.initialised = False
        self.rack.score_display.initialise()
        if self.credits:
            # Original $0774 address and $0777 four-character ROM message.
            self._write('PUSH', 0x3013)
            # Original $0783 address, 20 characters ($1ACF or $1ABA).
            message = ('ONLY 1PLAYER BUTTON ' if self.credits == 1
                       else '1 OR 2PLAYERS BUTTON')
            self._write(message, 0x2810)
        else:
            # Not represented as the completed $0AEA animated attract loop.
            self._write('INSERT COIN', 0x2918)
        self._write('CREDIT', 0x3501)
        self._draw_credit_number()

    def _draw_credit_number(self):
        m = self.rack.mem
        m[0x2070] = self.credits
        m[0x20EB] = ((self.credits // 10) << 4) | self.credits % 10  # original BCD credit counter
        # Only the 2-digit credit numeral is updated after each coin.
        for i,ch in enumerate(f'{self.credits:02d}'):
            self.rack.score_display.draw_char(glyph(ch), 0x3C01 + i*0x100)

    def _enter_credits(self):
        self.rack = Rack()
        self.rack.mem[0x20EF] = 0
        # Cold-start ROM splashAnimate = 1: normal Y, no moving-Y
        # or CCOIN animation on the first attract pass.
        self.rack.mem[0x20EC] = getattr(self, '_next_splash_flag', 1)
        self.rack.mem[0x20F4], self.rack.mem[0x20F5] = self.high_score
        self.rack.score_display = ScoreDisplay(self.rack)
        self.mode = 'credits'
        self._draw_credit_screen()
        if self.attract_preview and self.credits == 0:
            from attract_intro import AttractIntro
            self.attract_intro = AttractIntro(self)
        self.events.append(('CREDIT_SCREEN',self.credits))

    def machine_reset(self):
        """F3 operator reset: fresh 8080-derived startup state; retain CLI DIP/debug."""
        self.credits = 0
        self.high_score = (0, 0)
        self.prompt_ticks = 0
        self.attract_intro = None
        self.two_player = None
        self.events.append(('MACHINE_RESET', 'F3'))
        self._enter_credits()

    def insert_coin(self):
        # One keydown = one coin; key-repeat filtered in run_window.
        self.credits = min(99, self.credits+1)
        self.events.append(('COIN', self.credits))
        if self.mode == 'credits':
            self.attract_intro = None
            self._draw_credit_screen()
        else:
            # The credit counter is persistent during a real game, too.
            # Do not clear the playfield or change the active player: redraw
            # only the two numeral glyphs at their original VRAM positions.
            self._draw_credit_number()

    def start(self, players):
        if players not in (1,2): raise ValueError('players must be 1 or 2')
        if self.mode != 'credits' or self.credits < players:
            self.events.append(('START_REJECTED',players))
            return False
        self.credits -= players
        self.rack = Rack()
        self.rack.mem[0x20F4], self.rack.mem[0x20F5] = self.high_score
        self.rack.enable_waves_demo(starting_lives=self.starting_lives,
                                    bonus_life=self.bonus_life)
        self.rack.lives.life_decrement = 0 if self.debug else 1
        if players == 2:
            from two_players import TwoPlayerController
            self.two_player = TwoPlayerController(self.rack, self.starting_lives)
            self.events.append(('START_TWO_PLAYERS', self.credits))
        else:
            self.two_player = None
        # $07F9 -> $088D PromptPlayer: display PLAY PLAYER<1> before
        # $07FC clears the playfield and $0814 resumes game tasks.
        self.mode = 'prompt_player'
        self.prompt_ticks = 0xB0
        self.rack.mem[0x20C0] = self.prompt_ticks
        self._show_player_prompt()
        self.events.append(('START_GAME', players, self.credits))
        return True

    def _show_player_prompt(self):
        # $088D-$0895: ROM string $1B70, length $0E, at $2B11.
        # The game-mode HUD survives; do not show the actual rack yet.
        m = self.rack.mem
        self.rack.lives.game_over_sequence.clear_playfield()
        self.rack.score_display.initialised = False
        self.rack.score_display.initialise()
        self._write('PLAY PLAYER', 0x2B11)
        # ROM's <1> markers are distinct glyphs ($24/$1B/$25).
        address = 0x3611
        for code in (0x24, 0x1B if m[0x2067] == 0x21 else 0x1C, 0x25):
            address = self.rack.score_display.draw_char(code, address)
        self._draw_credit_number()
        self._flash_score()

    def _flash_score(self):
        # $08A9-$08CE: bit 2 of $20C0 selects the cleared score.
        m = self.rack.mem
        if self.prompt_ticks & 4:
            address = 0x271C if m[0x2067] == 0x21 else 0x391C
            for i in range(32):
                dest = address + i*32
                if 0x2400 <= dest < 0x4000:
                    m[dest] = 0
        else:
            self.rack.score_display.draw_score(0x20F8 if m[0x2067] == 0x21 else 0x20FC)

    def _finish_player_prompt(self):
        # $07FC-$0817: clear prompt and start the rack previously initialized
        # by the Stage 11 translated gameplay setup.
        m = self.rack.mem
        self.rack.lives.game_over_sequence.clear_playfield()
        self.rack.score_display.initialised = False
        self.rack.score_display.initialise()
        self.rack.shields.transfer_shields(1 if m[0x2067] == 0x21 else 2)
        self.rack.shields.draw_bottom_line()
        if self.two_player is not None:
            self.rack.lives.draw_reserve_ships()
            self.rack.lives.draw_lives_number(min(6, self.rack.lives.stash + 1))
        self._draw_credit_number()
        self.mode = 'playing'
        self.events.append(('PROMPT_COMPLETED',self.credits))

    def step_frame(self):
        if self.mode == 'credits':
            if self.attract_intro is not None:
                self.attract_intro.step()
            return
        if self.mode == 'prompt_player':
            # Original $001D DEC ($20C0) once per end-of-screen interrupt.
            self.prompt_ticks -= 1
            self.rack.mem[0x20C0] = self.prompt_ticks
            if self.prompt_ticks == 0:
                self._finish_player_prompt()
            else:
                self._flash_score()
            return
        self.rack.step_frame()
        if self.two_player is not None and self.two_player.pending_switch:
            self.two_player.switch()
            self.mode = 'prompt_player'
            self.prompt_ticks = 0xB0
            self.rack.mem[0x20C0] = self.prompt_ticks
            self._show_player_prompt()
            return
        if (self.two_player is not None and
                self.rack.lives.game_over_sequence.phase == 'switch_ready'):
            self.two_player.note_player_game_over()
            self.two_player.switch()
            self.rack.lives.game_over = False
            self.rack.lives.game_over_sequence.phase = 'inactive'
            self.mode = 'prompt_player'
            self.prompt_ticks = 0xB0
            self.rack.mem[0x20C0] = self.prompt_ticks
            self._show_player_prompt()
            return
        if self.rack.lives.game_over_sequence.phase == 'attract_pending':
            m = self.rack.mem
            self.high_score = (m[0x20F4],m[0x20F5])
            self._enter_credits()
